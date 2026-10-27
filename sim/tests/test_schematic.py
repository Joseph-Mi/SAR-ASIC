"""The sheet is the netlist, held to it by netlisting it back.

A schematic nothing checks is a drawing of what the circuit used to be. This
netlists the committed sheet with the editor itself and compares every element
against what `strongarm.subckt` builds for the benches -- model, terminals in
order, and geometry -- so the sheet cannot drift from the circuit that was
measured, and a sizing changed without regenerating it fails here.

Terminals in order matters more than it looks. The two device flavours are
drawn opposite ways round, a PMOS source upwards where an NMOS keeps its
drain, so a sheet built from one flavour's pin positions swaps the other's
drain and source: a circuit that is wrong and draws right. That is what
happened the first time this sheet was generated, which is the reason the
comparison is ordered and the reason it is mutation-checked below.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest

import schematic
import sky130
import strongarm
from devices import Sky130, pdk_library

needs_xschem = pytest.mark.skipif(shutil.which("xschem") is None, reason="xschem not on PATH")
needs_pdk = pytest.mark.skipif(not pdk_library().exists(), reason="sky130 model library not found")

#: The editor writes its netlist beside the sheet, which is what `xschemrc`
#: sets it to do so that there is one copy of it and not two.
NETLIST_DIR = "simulation"

#: A continued line in a SPICE netlist. The editor wraps at a width of its
#: own choosing, so a parse that reads lines has to undo that first.
CONTINUED = re.compile(r"\n\+\s*")

#: A subcircuit instance: the PDK's device wrapper, its four terminals, the
#: model, and the geometry as `k=v`.
INSTANCE = re.compile(
    r"^X(?P<name>\S+)\s+(?P<terminals>\S+\s+\S+\s+\S+\s+\S+)\s+"
    r"(?P<model>sky130\S+)\s+(?P<params>.+)$"
)

#: A capacitance: two plates and a value, no model.
CAPACITOR = re.compile(r"^C(?P<name>\S+)\s+(?P<terminals>\S+\s+\S+)\s+(?P<value>[\d.eE+-]+)")

#: Terminals in a symbol file, read the same way the interface freeze reads
#: them, so the two checks cannot disagree about what a declaration is.
TERMINAL = re.compile(r"^B\s+(?:\S+\s+){5}\{name=(?P<name>\S+)\s+dir=(?P<dir>\w+)\}", re.M)

#: Significant figures the netlister writes a geometry to. Numbers are
#: compared at that precision rather than exactly: the netlister formats to
#: six figures and the editor evaluates the symbol's own expressions, so the
#: two agree on every value and need not agree on how it is spelled. Finer
#: than the netlist itself is written would be comparing the formatting.
FIGURES = 6


#: What a device multiplier means when the netlist does not state one. The
#: editor writes a non-unit multiplier and suppresses a unit one, because one
#: copy is what an instance means on its own; the netlister always states it.
#: So the two are read against the same default, and a wide device built out
#: of several copies still has to say so on both sides.
COPIES = "m"
ONE = "1"


def _number(text: str) -> float:
    """One value, at the precision the netlist carries it to."""
    return float(f"{float(text):.{FIGURES}g}")


def elements(netlist: str) -> dict[str, tuple]:
    """Every element of a subcircuit, keyed by its name.

    A device becomes its model, its terminals in the order they are written,
    and its geometry as numbers, so that what is compared is the circuit and
    not the two tools' formatting.
    """
    found: dict[str, tuple] = {}
    for line in CONTINUED.sub(" ", netlist).splitlines():
        if (device := INSTANCE.match(line)) is not None:
            geometry = dict(pair.split("=", 1) for pair in device["params"].split())
            geometry.setdefault(COPIES, ONE)
            found[device["name"]] = (
                device["model"],
                tuple(device["terminals"].split()),
                {key: _number(value) for key, value in geometry.items()},
            )
        elif (cap := CAPACITOR.match(line)) is not None:
            found[cap["name"]] = (tuple(cap["terminals"].split()), _number(cap["value"]))
    return found


@pytest.fixture(scope="module")
def drawn(tmp_path_factory) -> dict[str, tuple]:
    """What the editor makes of the committed sheet.

    Netlisted from a copy, so a test run never rewrites what is committed and
    two runs at once cannot land on the same output file.
    """
    if not schematic.SHEET.exists():
        pytest.skip(f"{schematic.SHEET.name} not generated yet")
    workdir = tmp_path_factory.mktemp("sheet")
    for name in (schematic.SHEET.name, schematic.SYMBOL.name, "xschemrc"):
        shutil.copy(schematic.SHEET_DIR / name, workdir / name)
    subprocess.run(
        ["xschem", "-b", "-n", "-q", "--rcfile", "./xschemrc", schematic.SHEET.name],
        cwd=workdir,
        check=True,
        capture_output=True,
        text=True,
    )
    produced = workdir / NETLIST_DIR / f"{schematic.SHEET.stem}.spice"
    assert produced.exists(), "the editor netlisted the sheet somewhere else"
    return elements(produced.read_text())


@pytest.fixture(scope="module")
def built() -> dict[str, tuple]:
    """What the benches build, which is the thing the sheet has to be."""
    return elements(strongarm.subckt(strongarm.DESIGNED, Sky130()))


@needs_xschem
@needs_pdk
def test_the_sheet_holds_exactly_the_elements_the_benches_build(drawn, built):
    """A device on one side and not the other, by name."""
    assert set(drawn) == set(built)


@needs_xschem
@needs_pdk
def test_every_element_is_the_same_device_on_the_same_nets(drawn, built):
    """Model, terminals in order, and geometry, element by element.

    Named one at a time rather than as two dictionaries, because a failure
    here should say which device is wrong and not print the whole latch.
    """
    for name in sorted(built):
        assert drawn[name] == built[name], f"{name} differs"


@needs_xschem
@needs_pdk
def test_regenerating_the_sheet_changes_nothing(drawn):
    """The committed sheet is the generator's current output.

    What this catches that the comparison above does not is the generator
    changing while the sheet it wrote stays behind: the old sheet still
    netlists to the same circuit, and the two files have quietly stopped
    being one artifact.
    """
    assert schematic.SHEET.read_text() == schematic.sheet()
    assert schematic.SYMBOL.read_text() == schematic.symbol()


def test_the_symbol_declares_exactly_the_subcircuit():
    """The boundary, as the editor sees it, against the one the netlist uses.

    Needs no tools: the symbol is text and the subcircuit's terminals are a
    constant, which is the whole reason the interface freeze is cheap to hold.
    """
    if not schematic.SYMBOL.exists():
        pytest.skip(f"{schematic.SYMBOL.name} not generated yet")
    declared = {m["name"]: m["dir"] for m in TERMINAL.finditer(schematic.SYMBOL.read_text())}
    assert declared == strongarm.DIRECTIONS
    assert set(declared) == set(strongarm.TERMINALS)


def test_a_swapped_drain_and_source_is_caught():
    """The comparison is ordered, checked by breaking it.

    This is the defect the first generated sheet actually had, and a test that
    compared terminals as a set would have passed it.
    """
    netlist = strongarm.subckt(strongarm.DESIGNED, Sky130())
    honest = elements(netlist)
    swapped = elements(
        netlist.replace(
            f"Xtail {strongarm.TAIL} {strongarm.TAIL_GATE} vdd vdd",
            f"Xtail vdd {strongarm.TAIL_GATE} {strongarm.TAIL} vdd",
        )
    )
    assert set(swapped) == set(honest), "the mutation was supposed to keep every device"
    assert swapped["tail"] != honest["tail"]


def test_the_generator_reads_its_pin_positions_from_the_symbols():
    """The two flavours disagree, and the generator is not allowed to assume.

    If this ever reads the same positions for both, the table it is avoiding
    has come back and the drain-and-source swap is available again.
    """
    if shutil.which("xschem") is None or not pdk_library().exists():
        pytest.skip("symbol libraries not available")
    nmos = schematic.pins(schematic.symbol_for(sky130.NFET))
    pmos = schematic.pins(schematic.symbol_for(sky130.PFET))
    assert nmos["D"] == pmos["S"]
    assert nmos["S"] == pmos["D"]
    assert nmos["G"] == pmos["G"]


def test_the_sheet_and_its_symbol_are_committed():
    """Generated or not, both are tracked: the sheet is the review."""
    tracked = subprocess.run(
        ["git", "ls-files", "xschem"],
        cwd=pathlib.Path(schematic.REPO),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    for path in (schematic.SHEET, schematic.SYMBOL):
        assert str(path.relative_to(schematic.REPO)) in tracked, f"{path.name} is not tracked"
