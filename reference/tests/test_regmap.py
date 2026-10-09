"""The generated renderings of the register map, enforced.

A committed file that nothing checks agrees with the layout on the day it is
written. These tests regenerate it and compare, so moving a field either comes
with regenerated outputs or fails here -- and the failure names the command that
fixes it.

The header is also handed to a compiler, because a generated file that does not
compile is found by whoever vendors it rather than by us.
"""

from __future__ import annotations

import copy
import json
import pathlib
import shutil
import subprocess

import pytest

import regmap
from registers import COUNT, FIELDS, RW

REPO = next(p for p in pathlib.Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
OUTPUT = REPO / regmap.OUTPUT_DIR

#: Compilers to try, most standard name first.
COMPILERS = ("cc", "gcc", "clang")

#: What the compiler is asked to do: parse, and prove the assertions hold.
#: No object file, so nothing to clean up and no linker to satisfy.
COMPILE_FLAGS = ("-std=c11", "-Wall", "-Werror", "-fsyntax-only", "-x", "c", "-")

#: A field in the map, to hand the header's own accessors as a worked example.
#: One wider than a register, so the multi-register path is the one compiled.
WIDE_FIELD = "dac"


@pytest.fixture(scope="module")
def generated() -> dict[str, str]:
    return regmap.rendered()


@pytest.mark.parametrize("name", sorted(regmap.RENDERINGS))
def test_the_committed_rendering_is_what_the_layout_generates(name, generated):
    """The one test that makes every other claim about these files worth making."""
    path = OUTPUT / name
    assert path.exists(), f"{name} has never been generated: run `{regmap.REGENERATE}`"
    assert path.read_text(encoding=regmap.ENCODING) == generated[name], (
        f"{name} is not what the layout says: run `{regmap.REGENERATE}`"
    )


def test_the_hash_moves_when_a_field_moves():
    """The whole point of the hash. A map that differs in anything a host could
    act on has to hash differently, or the check it exists for passes while the
    two ends disagree."""
    described = regmap.canonical()
    moved = copy.deepcopy(described)
    moved["fields"][0]["shift"] += 1
    assert regmap.hash_of(moved) != regmap.hash_of(described)


def test_the_hash_ignores_the_order_fields_are_described_in():
    """Two descriptions of the same map hash the same, so a reordering of the
    declaration does not read as a map change to every host in the field."""
    described = regmap.canonical()
    shuffled = copy.deepcopy(described)
    shuffled["fields"].reverse()
    assert regmap.hash_of(shuffled) == regmap.hash_of(described)


def test_every_field_reaches_both_renderings(generated):
    """A field the generator skips is one firmware cannot address, and nothing
    else would notice it had gone."""
    header = generated["sar_regs.h"]
    data = json.loads(generated["sar_regs.json"])
    named = {field["name"] for field in data["fields"]}
    for field in FIELDS:
        assert field.name in named
        assert f"{regmap.PREFIX}_{field.name.upper()}_ADDR" in header


def test_every_address_in_the_map_is_described(generated):
    """Including the second register of a field wider than one: a host handed a
    width and no addresses cannot tell where the rest of it went."""
    data = json.loads(generated["sar_regs.json"])
    assert [entry["address"] for entry in data["registers"]] == list(range(COUNT))


def test_a_wide_field_says_which_of_its_bits_each_address_holds(generated):
    """The pieces have to tile the field exactly -- no gap, no overlap, no bit
    claimed twice -- or a value written through them is not the value asked
    for."""
    data = json.loads(generated["sar_regs.json"])
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
    header = generated["sar_regs.h"]
    for field in FIELDS:
        want = 1 if field.access == RW else 0
        assert f"#define {regmap.PREFIX}_{field.name.upper()}_WRITABLE {want}" in header


def compiler() -> str | None:
    return next((name for name in COMPILERS if shutil.which(name)), None)


def test_the_header_compiles(generated, tmp_path):
    """And the hash check it carries holds when handed the hash it generated."""
    found = compiler()
    if not found:
        pytest.skip("no C compiler")
    (tmp_path / "sar_regs.h").write_text(generated["sar_regs.h"], encoding=regmap.ENCODING)
    source = _probe(regmap.map_hash())
    done = subprocess.run(
        [found, *COMPILE_FLAGS, f"-I{tmp_path}"], input=source, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr


def test_the_header_refuses_a_hash_that_is_not_its_own(generated, tmp_path):
    """Mutation of the check itself: firmware pinned to another map must fail to
    compile, or the macro is decoration."""
    found = compiler()
    if not found:
        pytest.skip("no C compiler")
    (tmp_path / "sar_regs.h").write_text(generated["sar_regs.h"], encoding=regmap.ENCODING)
    source = _probe(regmap.map_hash() ^ 1)
    done = subprocess.run(
        [found, *COMPILE_FLAGS, f"-I{tmp_path}"], input=source, capture_output=True, text=True
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
