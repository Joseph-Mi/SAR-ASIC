"""The generated renderings of the register map, enforced.

A committed file that nothing checks agrees with the layout on the day it is
written. These tests regenerate it and compare, so moving a field either comes
with regenerated outputs or fails here -- and the failure names the command that
fixes it.

Each rendering is also handed to the tool that reads it -- the header to a C
compiler, the Verilog to the simulator's front end -- because a generated file
that does not compile is otherwise found by whoever picks it up rather than by
us.
"""

from __future__ import annotations

import json
import math
import pathlib
import re
import shutil
import subprocess

import pytest

import regmap
from interface import N_BITS
from registers import (
    COUNT,
    FIELDS,
    IDENTITY,
    IDENTITY_VALUE,
    MAP_HASH,
    REGISTER_WIDTH,
    RW,
    VIEWS,
    Registers,
    bits_for,
    fields_at,
    placement,
)

REPO = next(p for p in pathlib.Path(__file__).resolve().parents if (p / "pyproject.toml").exists())

C_HEADER = "firmware/sar_regs.h"
DATA = "firmware/sar_regs.json"
VERILOG = "hdl/rtl/sar_regs.vh"

#: Compilers to try, most standard name first.
COMPILERS = ("cc", "gcc", "clang")

#: What the compiler is asked to do: parse, and prove the assertions hold.
#: No object file, so nothing to clean up and no linker to satisfy.
COMPILE_FLAGS = ("-std=c11", "-Wall", "-Werror", "-fsyntax-only", "-x", "c", "-")

#: A field in the map, to hand the header's own accessors as a worked example.
#: One wider than a register, so the multi-register path is the one compiled.
WIDE_FIELD = "dac"

#: A value with every bit of a register set, so a write that may not land shows
#: up wherever it does.
FULL = (1 << REGISTER_WIDTH) - 1

#: The front end the Verilog rendering is handed, and what it is asked to do.
#: The project's own waivers come with it, so what is checked is the rendering
#: under the configuration the RTL is built with.
VERILATOR = "verilator"
VERILATOR_FLAGS = ("--lint-only", "-Wall", "--timescale", "1ns/1ps")
WAIVERS = "hdl/lint/waivers.vlt"

#: The module written to read every constant the rendering declares.
PROBE = "regmap_probe"

#: The RTL, and a parameter default in it. Synthesis reads these defaults, not
#: what a bench passes in, so a stale one ships even when every test is green.
#: A width the include cannot supply is one of these, because a port list cannot
#: use a constant the body has not declared yet.
RTL_DIR = ("hdl", "rtl")
RTL_DEFAULT = r"^\s*parameter\s+(?:integer\s+)?{name}\s*=\s*(\d+)"

#: Where a rendering is put for the tool that reads it. Not a temporary
#: directory: a tool is handed this path on its command line, and the one pytest
#: makes is named after the user, whose name here contains a newline -- which
#: Verilator's wrapper re-splits its arguments on, so the path arrives in
#: pieces. Under the build tree the path is ours and what failed stays to look
#: at.
WORKSPACE = ("build", "regmap")


@pytest.fixture(scope="module")
def generated() -> dict[str, str]:
    return regmap.rendered()


@pytest.fixture
def workspace() -> pathlib.Path:
    out = REPO.joinpath(*WORKSPACE)
    out.mkdir(parents=True, exist_ok=True)
    return out


@pytest.mark.parametrize("name", sorted(regmap.RENDERINGS))
def test_the_committed_rendering_is_what_the_layout_generates(name, generated):
    """The one test that makes every other claim about these files worth making."""
    path = REPO / name
    assert path.exists(), f"{name} has never been generated: run `{regmap.REGENERATE}`"
    assert path.read_text(encoding=regmap.ENCODING) == generated[name], (
        f"{name} is not what the layout says: run `{regmap.REGENERATE}`"
    )


def test_every_rendering_is_committed_where_the_tool_that_reads_it_looks():
    """The Verilog goes with the RTL because that is where an include resolves
    from, and the rest where a firmware repository can take them."""
    assert set(regmap.RENDERINGS) == {C_HEADER, DATA, VERILOG}


def test_every_field_reaches_every_rendering(generated):
    """A field the generator skips is one firmware cannot address, and nothing
    else would notice it had gone."""
    header = generated[C_HEADER]
    data = json.loads(generated[DATA])
    named = {field["name"] for field in data["fields"]}
    verilog = generated[VERILOG]
    for field in FIELDS:
        assert field.name in named
        assert f"{regmap.PREFIX}_{field.name.upper()}_ADDR" in header
        assert f"{regmap.PREFIX}_{field.name.upper()}_ADDR =" in verilog


def test_every_address_in_the_map_is_described(generated):
    """Including the second register of a field wider than one: a host handed a
    width and no addresses cannot tell where the rest of it went."""
    data = json.loads(generated[DATA])
    assert [entry["address"] for entry in data["registers"]] == list(range(COUNT))


def test_a_wide_field_says_which_of_its_bits_each_address_holds(generated):
    """The pieces have to tile the field exactly -- no gap, no overlap, no bit
    claimed twice -- or a value written through them is not the value asked
    for."""
    data = json.loads(generated[DATA])
    wide = next(f for f in data["fields"] if f["name"] == WIDE_FIELD)
    pieces = [
        part
        for entry in data["registers"]
        for part in entry["parts"]
        if part["field"] == WIDE_FIELD
    ]
    covered = sorted((p["field_bit"], p["width"]) for p in pieces)
    assert covered == [(i * data["register_width"], w) for i, w in enumerate(_tiles(wide, data))]


def _tiles(field: dict, data: dict) -> list[int]:
    """How many bits each of a field's registers carries."""
    width, step = field["width"], data["register_width"]
    return [min(step, width - start) for start in range(0, width, step)]


def test_read_only_fields_are_marked_unwritable(generated):
    """A host that writes one gets no error back, so the only place it can learn
    the register is not its to write is here."""
    header = generated[C_HEADER]
    for field in FIELDS:
        want = 1 if field.access == RW else 0
        assert f"#define {regmap.PREFIX}_{field.name.upper()}_WRITABLE {want}" in header


def compiler() -> str | None:
    return next((name for name in COMPILERS if shutil.which(name)), None)


def test_the_header_compiles(generated, workspace):
    """And the hash check it carries holds when handed the hash it generated."""
    found = compiler()
    if not found:
        pytest.skip("no C compiler")
    (workspace / "sar_regs.h").write_text(generated[C_HEADER], encoding=regmap.ENCODING)
    source = _probe(MAP_HASH)
    done = subprocess.run(
        [found, *COMPILE_FLAGS, f"-I{workspace}"], input=source, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr


def test_the_header_refuses_a_hash_that_is_not_its_own(generated, workspace):
    """Mutation of the check itself: firmware pinned to another map must fail to
    compile, or the macro is decoration."""
    found = compiler()
    if not found:
        pytest.skip("no C compiler")
    (workspace / "sar_regs.h").write_text(generated[C_HEADER], encoding=regmap.ENCODING)
    source = _probe(MAP_HASH ^ 1)
    done = subprocess.run(
        [found, *COMPILE_FLAGS, f"-I{workspace}"], input=source, capture_output=True, text=True
    )
    assert done.returncode != 0


def _probe(pinned: int) -> str:
    """A firmware source file, as thin as one can be and still use the header:
    it pins the map it was written against, places a field that spans registers,
    and forms the frame that writes it."""
    upper = WIDE_FIELD.upper()
    return f"""
#include "sar_regs.h"

{regmap.PREFIX}_REQUIRE_MAP({pinned:#x}u);

unsigned probe({regmap.WIDE_TYPE} value, {regmap.BYTE_TYPE} *out)
{{
  unsigned n = 0;
  out[n++] = {regmap.PREFIX.lower()}_command({regmap.PREFIX}_{upper}_ADDR, 1);
  for (unsigned i = 0; i < {regmap.PREFIX}_{upper}_REGISTERS; i++)
    out[n++] = {regmap.PREFIX.lower()}_field_byte(value & {regmap.PREFIX}_{upper}_MASK, i);
  return n;
}}
"""


#: One packed word in the Verilog, and the sized literals it concatenates. The
#: literal and what it should parse to are one fact, so the pattern is kept next
#: to the test that reads it rather than shared with the generator.
PACKED = r"localparam\s*\[[^\]]*\]\s*{name}\s*=\s*\{{(?P<body>[^}}]*)\}}"
LITERAL = re.compile(r"(\d+)'h([0-9a-fA-F]+)")


def packed_word(verilog: str, name: str) -> list[int]:
    """One packed constant, in address order: the generator writes the highest
    address first, because that is the end a concatenation starts from."""
    found = re.search(PACKED.format(name=f"{regmap.PREFIX}_{name}"), verilog)
    assert found, f"{name} is not declared"
    bytes_ = [int(digits, 16) for _, digits in LITERAL.findall(found["body"])]
    assert len(bytes_) == COUNT, f"{name} covers {len(bytes_)} registers, not {COUNT}"
    return list(reversed(bytes_))


def writable_by_behaviour(address: int) -> int:
    """Which bits of a register the model lets the host write, found by writing
    them all and reading back what stuck."""
    reg = Registers()
    reg.write(address, FULL)
    return reg.read(address) & ~read_only_bits(address)


def read_only_bits(address: int) -> int:
    """Bits a register reports rather than stores, which a write cannot move."""
    return sum(
        ((1 << width) - 1) << shift
        for field, (_, width, shift) in ((f, placement(f, address)) for f in fields_at(address))
        if field.access != RW
    )


def held_by_behaviour(address: int) -> int:
    """Which bits wait for a conversion to end, found by writing the complement
    of what the register holds while one is running, and seeing which bits have
    not reached the half that acts on them. The complement rather than all ones,
    because writing a register what it already holds moves nothing and would
    read as a bit that never waits."""
    reg = Registers()
    reg.converting(True)
    reg.write(address, reg.read(address) ^ FULL)
    waiting = 0
    for field in fields_at(address):
        if field.access != RW or reg[field.name] == reg.written(field.name):
            continue
        _, width, shift = placement(field, address)
        waiting |= ((1 << width) - 1) << shift
    return waiting


@pytest.mark.parametrize("address", range(COUNT))
def test_the_verilog_says_which_bits_the_host_may_write(address, generated):
    """Measured against the model rather than recomputed the generator's way, so
    the two agree about behaviour and not merely about arithmetic."""
    assert packed_word(generated[VERILOG], "WRITABLE")[address] == writable_by_behaviour(address)


@pytest.mark.parametrize("address", range(COUNT))
def test_the_verilog_says_which_bits_wait_for_a_conversion(address, generated):
    assert packed_word(generated[VERILOG], "HELD")[address] == held_by_behaviour(address)


@pytest.mark.parametrize("address", range(COUNT))
def test_the_verilog_says_what_each_register_comes_up_as(address, generated):
    """Only the bits a register stores: what it reports is not its to reset."""
    want = Registers().read(address) & ~read_only_bits(address)
    assert packed_word(generated[VERILOG], "RESET")[address] == want


def test_the_verilog_carries_the_identity_the_map_derives(generated):
    want = f"{regmap.PREFIX}_{IDENTITY.upper()}_VALUE = {REGISTER_WIDTH}'h{IDENTITY_VALUE:02x};"
    assert want in generated[VERILOG]


def test_the_verilog_elaborates(generated, workspace):
    """A generated include that does not compile is found by whoever includes it
    rather than here. The probe uses the packed words, so a malformed
    concatenation fails rather than being skipped over."""
    if not shutil.which(VERILATOR):
        pytest.skip(f"no {VERILATOR}")
    (workspace / "sar_regs.vh").write_text(generated[VERILOG], encoding=regmap.ENCODING)
    probe = workspace / f"{PROBE}.v"
    probe.write_text(_probe_module(), encoding=regmap.ENCODING)
    done = subprocess.run(
        [
            VERILATOR,
            *VERILATOR_FLAGS,
            str(REPO / WAIVERS),
            f"-I{workspace}",
            "--top-module",
            PROBE,
            str(probe),
        ],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr


def _probe_module() -> str:
    """The thinnest module that reads what the regfile will.

    The port's width is written out by the model, because a port list cannot use
    a constant the body has not declared yet -- the include sits inside the
    module, which is what scopes the declarations to it. The address comes from
    a port rather than a constant, so the part-selects survive to elaboration.
    """
    prefix = regmap.PREFIX
    byte = f"[{prefix}_REGISTER_WIDTH-1:0]"
    select = f"addr_i*{prefix}_REGISTER_WIDTH+:{prefix}_REGISTER_WIDTH"
    identity = f"{prefix}_{IDENTITY.upper()}"
    return f"""
module {PROBE} (
    input  wire [{REGISTER_WIDTH - 1}:0] addr_i,
    output wire                          data_o
);
`include "sar_regs.vh"
  wire {byte} writable = {prefix}_WRITABLE[{select}];
  wire {byte} held = {prefix}_HELD[{select}];
  wire {byte} reset = {prefix}_RESET[{select}];
  assign data_o = ^(writable ^ held ^ reset)
      ^ (addr_i == {identity}_ADDR)
      ^ ^{identity}_VALUE;
endmodule
"""


def rtl_defaults(name: str) -> list[tuple[str, int]]:
    """Every declared default for a parameter of this name, with its file."""
    pattern = re.compile(RTL_DEFAULT.format(name=name), re.M)
    return [
        (path.name, int(found[1]))
        for path in sorted(REPO.joinpath(*RTL_DIR).glob("*.v"))
        for found in pattern.finditer(path.read_text())
    ]


@pytest.mark.parametrize(
    ("name", "want"),
    [("REGISTER_WIDTH", REGISTER_WIDTH), ("VIEW_WIDTH", bits_for(len(VIEWS)))],
)
def test_the_rtl_defaults_to_the_width_the_map_declares(name, want):
    found = rtl_defaults(name)
    assert found, f"no RTL declares {name}"
    for where, value in found:
        assert value == want, f"{where} defaults {name} to {value}, the map says {want}"


@pytest.mark.parametrize("count", [N_BITS, len(VIEWS)])
def test_the_width_the_rtl_computes_is_the_width_the_map_means(count):
    """A port cannot be sized from the include, so the RTL sizes the reported
    fields with $clog2 -- which is ceil(log2(n)), the same as the map's own
    count of bits except at one, where a field still needs a bit to itself."""
    assert bits_for(count) == math.ceil(math.log2(count))
