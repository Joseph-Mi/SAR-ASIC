"""The phase generator's sheet, against the netlist its benches are built on.

`xschem/phase_gen.sch` is the three switch phases as a drawing, held to
`sim/analog.py` the way the other two sheets are: the editor netlists it back
and every device is compared -- model, terminals in order, geometry.

That comparison is not a formality on this sheet, and there is a measurement
to say so. The first version drew each gate's input name on a stub reaching
out to its gate pin, which is what a person draws; between the parallel legs
of a NOR a stub one leg-pitch long put one gate's label on top of its
neighbour's body tie, and the two nets merged. The page looked right. What it
netlisted was a NOR whose second input was the ground rail -- a gate that can
never go high, so the phase it guards would have been free to move whatever
the line it is supposed to wait for was doing, which is the one property this
circuit exists to have. Hence `test_no_gate_is_held_at_a_rail` below, which is
the general form of that defect: in this circuit nothing is tied off, so a
gate on a rail is always a mistake.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest

import analog
import phase_gen
import sheet
from devices import pdk_library

needs_xschem = pytest.mark.skipif(shutil.which("xschem") is None, reason="xschem not on PATH")
needs_pdk = pytest.mark.skipif(not pdk_library().exists(), reason="sky130 model library not found")

#: One terminal record in a symbol file, in the order the records appear --
#: which is the order an instance of the symbol wires its pins.
TERMINAL = re.compile(r"^B\s+\S+(?:\s+\S+){4}\s+\{name=(?P<name>\S+)\s+dir=(?P<dir>\w+)", re.M)

#: Where each kind of terminal sits in a device line, once it is parsed.
GATE = 1

#: How the stage this sheet is at may be spelled.
STAGES = ("generated", "drawn")


@pytest.fixture(scope="module")
def netlisted(tmp_path_factory) -> str:
    """The committed sheet as the editor netlists it."""
    if not phase_gen.SHEET.exists():
        pytest.skip(f"{phase_gen.SHEET.name} not drawn yet")
    return sheet.netlist(phase_gen.SHEET.name, tmp_path_factory.mktemp("phases"))


@pytest.fixture(scope="module")
def drawn(netlisted) -> dict[str, tuple]:
    return sheet.compared(netlisted)


@pytest.fixture(scope="module")
def built() -> dict[str, tuple]:
    return sheet.compared("\n".join(analog.generator_devices(phase_gen.DRAWN_WITH)))


@needs_xschem
@needs_pdk
def test_the_sheet_holds_exactly_the_devices_the_benches_build(drawn, built):
    """A device on one side and not the other, by name."""
    assert set(drawn) == set(built)


@needs_xschem
@needs_pdk
def test_every_device_is_the_same_device_on_the_same_nets(drawn, built):
    """Model, terminals in order, and geometry, device by device.

    In order rather than as a set, for the reason the comparator's sheet is:
    the two FET symbols are drawn opposite ways round, so a sheet built from
    one flavour's pin positions swaps the other's drain and source.
    """
    for name in sorted(built):
        assert drawn[name] == built[name], f"{name} differs"


@needs_xschem
@needs_pdk
def test_no_gate_is_held_at_a_rail(drawn):
    """Every transistor's gate reads a signal, which in this circuit they all
    do: nothing here is tied off, so a gate on a rail is a short that drew
    correctly. This is the defect the first version of the drawing had."""
    for name, (_, terminals, _) in sorted(drawn.items()):
        assert terminals[GATE] not in phase_gen.RAILS, f"{name}'s gate sits on {terminals[GATE]}"


@needs_xschem
@needs_pdk
def test_nothing_on_the_sheet_floats(netlisted, built):
    """Every net reaches at least two terminals, or is one of the block's own.

    The editor runs a check of its own and exits 10 when something floats,
    but that is a flag and not a name. This says which net, and it is what
    found the merged label above -- the shorted gate left `top_on` reaching
    one terminal where it should reach two.
    """
    counted: dict[str, int] = {}
    for _, terminals, _ in built.values():
        for net in terminals:
            counted[net] = counted.get(net, 0) + 1
    drawn = sheet.compared(netlisted)
    reached: dict[str, int] = {}
    for _, terminals, _ in drawn.values():
        for net in terminals:
            reached[net] = reached.get(net, 0) + 1
    once = {net for net, count in reached.items() if count == 1}
    assert once <= set(analog.generator_terminals()), f"{sorted(once)} reach one terminal"
    assert reached == counted, "the sheet's nets do not reach what the netlist's do"


@needs_xschem
def test_the_sheet_declares_exactly_the_blocks_terminals(netlisted):
    """The boundary, in the order an instance of the symbol would wire it."""
    header = re.search(r"^\*\*\.subckt\s+(?P<name>\S+)\s+(?P<ports>.+)$", netlisted, re.M)
    assert header is not None, "the editor wrote no subcircuit header"
    assert header["name"] == analog.GENERATOR_NAME
    assert header["ports"].split() == analog.generator_terminals()


def test_the_symbol_declares_exactly_the_blocks_terminals_in_order():
    """A symbol's port order is the order of its pin records, and a SPICE
    instance wires by position, so this is electrical and not cosmetic: a
    symbol ordered otherwise hands the input switches the conversion phase."""
    if not phase_gen.SYMBOL.exists():
        pytest.skip(f"{phase_gen.SYMBOL.name} not generated yet")
    records = [
        (found["name"], found["dir"]) for found in TERMINAL.finditer(phase_gen.SYMBOL.read_text())
    ]
    assert records == [(name, phase_gen.DIRECTIONS[name]) for name in analog.generator_terminals()]


def test_the_symbol_is_the_generators_current_output():
    """It carries the interface and no arrangement, so it is generated in
    every stage and the committed file is held to the generator."""
    if not phase_gen.SYMBOL.exists():
        pytest.skip(f"{phase_gen.SYMBOL.name} not generated yet")
    assert phase_gen.SYMBOL.read_text() == phase_gen.symbol()


@needs_pdk
def test_every_gate_the_netlist_builds_is_placed_once():
    """The drawing says where each gate goes and never what is in one, so the
    two can only disagree about which gates exist -- and that is refused
    rather than drawn around."""
    placed = [name for _, row in phase_gen.ROWS for name in row]
    assert sorted(placed) == sorted(phase_gen.cells(phase_gen.DRAWN_WITH))
    assert len(placed) == len(set(placed)), "a gate is placed twice"


@needs_pdk
def test_a_gate_the_generator_does_not_build_is_refused(monkeypatch):
    """Checked by breaking it, in both directions: a drawing that places a
    gate the circuit lost, and a circuit that grew one the drawing has not
    been told about."""
    monkeypatch.setattr(phase_gen, "ROWS", (*phase_gen.ROWS, ("invented", ("nor_invented",))))
    with pytest.raises(ValueError, match="does not have"):
        phase_gen._columns(phase_gen.DRAWN_WITH)


@needs_pdk
def test_a_gate_the_drawing_does_not_place_is_refused(monkeypatch):
    rows = tuple((caption, row[1:]) for caption, row in phase_gen.ROWS)
    monkeypatch.setattr(phase_gen, "ROWS", rows)
    with pytest.raises(ValueError, match="does not place"):
        phase_gen._columns(phase_gen.DRAWN_WITH)


@needs_pdk
def test_the_stage_the_sheet_is_at_holds_its_own_contract():
    """While the generator owns the arrangement, the committed sheet is its
    output byte for byte; once a person owns it, the netlist comparison above
    is what holds it instead."""
    assert phase_gen.ARRANGEMENT in STAGES, f"unknown stage, not one of {STAGES}"
    if phase_gen.ARRANGEMENT == "generated":
        assert phase_gen.SHEET.read_text() == phase_gen.sheet()


@needs_pdk
def test_regenerating_leaves_a_hand_drawn_sheet_alone(tmp_path, monkeypatch):
    """Once the arrangement is a person's, `make schematic` does not throw it
    away; what it would have written goes under build/ to be read."""
    drawing = tmp_path / phase_gen.SHEET.name
    symbol = tmp_path / phase_gen.SYMBOL.name
    drawing.write_text("drawn by hand\n")
    monkeypatch.setattr(phase_gen, "SHEET", drawing)
    monkeypatch.setattr(phase_gen, "SYMBOL", symbol)
    monkeypatch.setattr(phase_gen, "PROPOSED", tmp_path / "build" / phase_gen.SHEET.name)
    monkeypatch.setattr(phase_gen, "ARRANGEMENT", "drawn")

    assert phase_gen.main([]) == 0
    assert drawing.read_text() == "drawn by hand\n"
    assert (tmp_path / "build" / phase_gen.SHEET.name).read_text() == phase_gen.sheet()
    assert symbol.read_text() == phase_gen.symbol(), "the symbol is generated in every stage"

    assert phase_gen.main(["--force"]) == 0
    assert drawing.read_text() == phase_gen.sheet(), "--force did not regenerate"


def test_the_sheet_and_its_symbol_are_committed():
    """A drawing nobody committed is a drawing the next checkout does not have."""
    tracked = subprocess.run(
        ["git", "ls-files", "xschem"],
        cwd=pathlib.Path(sheet.REPO),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    for path in (phase_gen.SHEET, phase_gen.SYMBOL):
        assert str(path.relative_to(sheet.REPO)) in tracked, f"{path.name} is not tracked"
