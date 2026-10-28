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
from unittest import mock

import pytest

import schematic
import sheet
import sky130
import strongarm
from devices import Sky130, pdk_library

needs_xschem = pytest.mark.skipif(shutil.which("xschem") is None, reason="xschem not on PATH")
needs_pdk = pytest.mark.skipif(not pdk_library().exists(), reason="sky130 model library not found")

#: Terminals in a symbol file, read the same way the interface freeze reads
#: them, so the two checks cannot disagree about what a declaration is.
TERMINAL = re.compile(r"^B\s+(?:\S+\s+){5}\{name=(?P<name>\S+)\s+dir=(?P<dir>\w+)\}", re.M)


@pytest.fixture(scope="module")
def netlisted(tmp_path_factory) -> str:
    """The committed sheet as the editor netlists it."""
    if not schematic.SHEET.exists():
        pytest.skip(f"{schematic.SHEET.name} not generated yet")
    return sheet.netlist(schematic.SHEET.name, tmp_path_factory.mktemp("sheet"))


@pytest.fixture(scope="module")
def drawn(netlisted) -> dict[str, tuple]:
    """The sheet's elements, which is what the circuit comparison is about."""
    return sheet.compared(netlisted)


@pytest.fixture(scope="module")
def built() -> dict[str, tuple]:
    """What the benches build, which is the thing the sheet has to be."""
    return sheet.compared(strongarm.subckt(strongarm.DESIGNED, Sky130()))


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
def test_the_sheet_declares_exactly_the_subcircuits_ports(netlisted):
    """The sheet's own boundary, in order and by direction.

    The element comparison cannot see this. A port symbol deleted from the
    sheet leaves every device still on a net of the right name, because the
    name is carried by the wire it was drawn on -- so the circuit compares
    equal while the subcircuit it netlists to has lost a terminal, and what
    instantiates it silently connects the rest one place over. Checked here
    because the arrangement is edited by hand, where a port is as easy to
    catch with a rubber band as anything else on the sheet.
    """
    header = next(line for line in netlisted.splitlines() if line.startswith("**.subckt"))
    assert tuple(header.split()[2:]) == strongarm.TERMINALS

    kinds = {"ipin": "in", "opin": "out", "iopin": "inout"}
    declared = {
        m["name"]: kinds[m["kind"]]
        for m in re.finditer(r"^\*\.(?P<kind>i?[io]pin)\s+(?P<name>\S+)$", netlisted, re.M)
    }
    assert declared == strongarm.DIRECTIONS


def test_the_symbol_is_the_generators_current_output():
    """The symbol is generated in every stage, so it is held to the generator.

    It carries the interface and no arrangement: where its pins sit is a table
    in the generator, so there is nothing a person would reach for the editor
    to do to it, and holding it exactly costs nothing. The sheet is the file
    that gets drawn on, and `ARRANGEMENT` says whether it is still ours.
    """
    if not schematic.SYMBOL.exists():
        pytest.skip(f"{schematic.SYMBOL.name} not generated yet")
    assert schematic.SYMBOL.read_text() == schematic.symbol()


#: The stages the generator knows how to be in, so that a typo in the one it
#: declares cannot quietly turn the check below into nothing.
STAGES = ("generated", "drawn")


def test_the_stage_the_sheet_is_at_holds_its_own_contract():
    """While the generator owns the arrangement, the committed sheet is it.

    What byte-equality catches that the element comparison does not is the
    generator changing while the sheet it wrote stays behind: the old sheet
    still netlists to the same circuit, and the two files have quietly
    stopped being one artifact. It lapses once the sheet is drawn by hand,
    where the text is nobody's output -- and the element comparison, which
    until then compared the generator with itself, becomes the real test.

    Branching rather than skipping, because `SAR_REQUIRE_TOOLS` turns a skip
    into a failure and a stage is not a missing tool. The stage is asserted
    against the known set first, so misspelling it fails here instead of
    disabling the only thing holding the sheet to the generator.
    """
    assert schematic.ARRANGEMENT in STAGES, f"unknown arrangement stage, not one of {STAGES}"
    if schematic.ARRANGEMENT == "generated":
        assert schematic.SHEET.read_text() == schematic.sheet()


def test_regenerating_leaves_a_hand_drawn_sheet_alone(tmp_path, monkeypatch):
    """The drawn stage does not let `make schematic` throw a drawing away.

    The hazard this exists for is quiet: the generator still runs, still
    reports success, and the arrangement is gone. So the refusal is asserted
    rather than documented, and so is the override, because a refusal with no
    way past it would be a reason to edit the generator instead.

    What the drawing is stands in for itself, because what is under test is
    the decision and not the generator: drawing the real sheet needs the PDK
    and the editor's symbol libraries, which would confine a check against
    losing a person's work to the one job that has them. It belongs in the
    cheapest.
    """
    sheet, symbol = tmp_path / "strongarm.sch", tmp_path / "strongarm.sym"
    drawing = "v {hand drawn}\n"
    sheet.write_text(drawing)
    monkeypatch.setattr(schematic, "SHEET", sheet)
    monkeypatch.setattr(schematic, "SYMBOL", symbol)
    monkeypatch.setattr(schematic, "PROPOSED", tmp_path / "build" / "strongarm.sch")
    monkeypatch.setattr(schematic, "ARRANGEMENT", "drawn")
    monkeypatch.setattr(schematic, "sheet", lambda *a, **k: "v {generated}\n")

    assert schematic.main([]) == 0
    assert sheet.read_text() == drawing, "a regeneration overwrote the drawing"
    assert (tmp_path / "build" / "strongarm.sch").read_text() == schematic.sheet(), (
        "it did not say what it would have written"
    )
    assert symbol.read_text() == schematic.symbol(), "the symbol is generated in every stage"

    assert schematic.main(["--force"]) == 0
    assert sheet.read_text() == schematic.sheet(), "--force did not regenerate"


def test_a_missing_sheet_is_generated_even_once_the_stage_is_drawn(tmp_path, monkeypatch):
    """There is nothing to protect when the file is not there.

    The bootstrap has to keep working after the stage has moved on, or a
    fresh checkout of a sheet that someone forgot to commit has no way back.
    """
    sheet = tmp_path / "strongarm.sch"
    monkeypatch.setattr(schematic, "SHEET", sheet)
    monkeypatch.setattr(schematic, "SYMBOL", tmp_path / "strongarm.sym")
    monkeypatch.setattr(schematic, "ARRANGEMENT", "drawn")
    monkeypatch.setattr(schematic, "sheet", lambda *a, **k: "v {generated}\n")

    assert schematic.main([]) == 0
    assert sheet.read_text() == schematic.sheet()


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


def test_the_symbol_declares_its_pins_in_the_subcircuit_order():
    """The order the records sit in is the symbol's port list.

    An instance of this symbol netlists its pins in the order they are
    declared here, so a parent sheet wires them against that order while the
    netlist every bench measures declares `TERMINALS`. The two orders being
    the same is what makes the sheet's symbol usable above the sheet; when
    they were not, an instance reached `vref` where the subcircuit wanted
    `vdd` and nothing about either file looked wrong.
    """
    if not schematic.SYMBOL.exists():
        pytest.skip(f"{schematic.SYMBOL.name} not generated yet")
    declared = [m["name"] for m in TERMINAL.finditer(schematic.SYMBOL.read_text())]
    assert tuple(declared) == strongarm.TERMINALS


def test_which_side_a_pin_is_drawn_on_does_not_change_the_port_order():
    """Moving a terminal to another edge is a drawing change and nothing more.

    The guarantee the sides table is written for, asserted rather than
    commented: the order above came out of the sides the first time, so a
    reader rearranging the symbol silently repinned it.
    """
    moved = dict.fromkeys(schematic.SIDES, "top")
    moved["vdd"], moved["vss"] = "left", "bottom"
    with mock.patch.object(schematic, "SIDES", moved):
        rearranged = schematic.symbol()
    assert [m["name"] for m in TERMINAL.finditer(rearranged)] == list(strongarm.TERMINALS)
    assert rearranged != schematic.symbol()


def test_a_swapped_drain_and_source_is_caught():
    """The comparison is ordered, checked by breaking it.

    This is the defect the first generated sheet actually had, and a test that
    compared terminals as a set would have passed it.
    """
    netlist = strongarm.subckt(strongarm.DESIGNED, Sky130())
    honest = sheet.compared(netlist)
    swapped = sheet.compared(
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
    nmos = sheet.pins(sheet.symbol_for(sky130.NFET))
    pmos = sheet.pins(sheet.symbol_for(sky130.PFET))
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
