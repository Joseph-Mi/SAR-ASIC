"""The array's sheet, against the netlist its benches are built on.

`xschem/cap_array.sch` is the binary-weighted array as a drawing, and what
holds it to the design is what holds the comparator's sheet: the editor
netlists it back, and every element is compared against `sim/analog.py` --
model, plates in order, and the geometry each branch is built with.

Two things are worth more attention here than on a transistor sheet.

The first is the weighting, which is the whole circuit. Ten elements whose
multipliers are not powers of two are a converter with no monotonic range, and
nothing downstream would say so: the sheet would netlist, simulate and lay
out. So the weights are asserted against the arithmetic as well as against the
netlist, and a swapped pair is mutation-checked below.

The second is the multiplier itself. The PDK's own symbol cannot state the one
the model reads -- its format emits `MF=`, and the model takes `mult` -- so the
instances carry a format of their own, and that is asserted from both ends:
that the sheet netlists `mult`, and that the PDK's symbol still does not.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest

import analog
import cap_array
import sheet
from devices import pdk_library

needs_xschem = pytest.mark.skipif(shutil.which("xschem") is None, reason="xschem not on PATH")
needs_pdk = pytest.mark.skipif(not pdk_library().exists(), reason="sky130 model library not found")

#: One terminal record in a symbol file, in the order the records appear --
#: which is the order an instance of the symbol wires its pins.
TERMINAL = re.compile(r"^B\s+\S+(?:\s+\S+){4}\s+\{name=(?P<name>\S+)\s+dir=(?P<dir>\w+)", re.M)

#: How the stage this sheet is at may be spelled.
STAGES = ("generated", "drawn")


@pytest.fixture(scope="module")
def netlisted(tmp_path_factory) -> str:
    """The committed sheet as the editor netlists it."""
    if not cap_array.SHEET.exists():
        pytest.skip(f"{cap_array.SHEET.name} not drawn yet")
    return sheet.netlist(cap_array.SHEET.name, tmp_path_factory.mktemp("array"))


@pytest.fixture(scope="module")
def drawn(netlisted) -> dict[str, tuple[str, tuple[str, ...], dict[str, float]]]:
    return sheet.compared(netlisted)


@pytest.fixture(scope="module")
def built() -> dict[str, tuple[str, tuple[str, ...], dict[str, float]]]:
    return sheet.compared("\n".join(analog.array_capacitors(unit=analog.Mim())))


@needs_xschem
def test_the_sheet_holds_exactly_the_branches_the_benches_build(drawn, built):
    """One element per branch, no more and no fewer."""
    assert set(drawn) == set(built)


@needs_xschem
def test_every_branch_is_the_same_device_on_the_same_plates(drawn, built):
    """Model, plates in order, and size, for each of them.

    In order, not as a set: the plates of a MiM are not interchangeable. `c0`
    is the plate above, which is where the array's floating node belongs
    (DD-13), and a sheet with the two the other way round draws identically
    and puts the converter's most sensitive node under the met3 plate instead
    of over it.
    """
    for name in sorted(built):
        assert drawn[name] == built[name], name


@needs_xschem
def test_every_branch_states_the_multiplier_its_model_reads(drawn):
    """`mult` as well as `m`, equal, on every branch.

    This is what the instances' own format exists for. Without it the sheet
    netlists `MF=`, which the device's model does not read, and a branch of
    1024 units reports the matching of one unit -- measured, 0.19 % against
    the 0.055 % sixteen drawn units give. It netlists, simulates and reads
    like a finished array while saying the array matches twenty times worse
    than it does.
    """
    for name, (_, _, size) in sorted(drawn.items()):
        assert size["mult"] == size["m"], f"{name} is {size['m']} copies of {size['mult']} units"


@needs_xschem
def test_the_weights_on_the_sheet_are_binary_with_one_dummy(drawn):
    """Against the arithmetic, not only against the netlist.

    The netlist comparison above would pass a weighting that is wrong in both
    places. This is the one assertion here that does not read `analog.py`.
    """
    weights = {name: size["mult"] for name, (_, _, size) in drawn.items()}
    assert weights.pop(f"u{analog.branch_tags()[-1]}") == 1, "the dummy is one unit"
    assert sorted(weights.values()) == [2.0**k for k in range(analog.N_BITS)]


@needs_xschem
def test_a_swapped_pair_of_weights_is_caught(built):
    """The comparison is by branch, checked by breaking it.

    A sheet drawn with two branches' multipliers exchanged is a converter
    whose code is a permutation of the right one, and a test comparing the
    multipliers as a set would pass it.
    """
    lines = analog.array_capacitors(unit=analog.Mim())
    for one, other in [(-3, -2)]:
        head, _, size = lines[one].partition(" mult=")
        lines[one] = f"{head} mult={lines[other].partition(' mult=')[2]}"
        lines[other] = f"{lines[other].partition(' mult=')[0]} mult={size}"
    swapped = sheet.compared("\n".join(lines))
    assert set(swapped) == set(built), "the mutation was supposed to keep every branch"
    assert swapped != built
    assert sorted(size["mult"] for _, _, size in swapped.values()) == sorted(
        size["mult"] for _, _, size in built.values()
    ), "a comparison by set of multipliers would have passed this"


@needs_xschem
def test_the_sheet_declares_exactly_the_blocks_terminals(netlisted):
    """The boundary, in the order an instance of the symbol would wire it."""
    header = re.search(r"^\*\*\.subckt\s+(?P<name>\S+)\s+(?P<ports>.+)$", netlisted, re.M)
    assert header is not None, "the editor wrote no subcircuit header"
    assert header["name"] == analog.ARRAY_NAME
    assert header["ports"].split() == analog.array_terminals()


@needs_xschem
def test_nothing_on_the_sheet_floats(netlisted):
    """Every plate reaches a terminal of the block.

    The array is whole -- unlike the tile's sheet it waits for nothing -- so
    this is an assertion that can be made outright: a plate wired to nothing
    would net to a name of the editor's own invention, and a plate wired to
    the wrong terminal would be caught above.
    """
    carried = {net for _, nets, _ in sheet.compared(netlisted).values() for net in nets}
    assert carried == set(analog.array_terminals())


def test_the_symbol_declares_exactly_the_blocks_terminals_in_order():
    """A symbol's port order is the order of its pin records, and a SPICE
    instance wires by position, so this is electrical and not cosmetic."""
    if not cap_array.SYMBOL.exists():
        pytest.skip(f"{cap_array.SYMBOL.name} not generated yet")
    declared = TERMINAL.finditer(cap_array.SYMBOL.read_text())
    records = [(found["name"], found["dir"]) for found in declared]
    assert records == [(t, "inout") for t in analog.array_terminals()]


def test_the_symbol_is_the_generators_current_output():
    """The symbol carries the interface and no arrangement, so it is generated
    in every stage and the committed file is held to the generator."""
    if not cap_array.SYMBOL.exists():
        pytest.skip(f"{cap_array.SYMBOL.name} not generated yet")
    assert cap_array.SYMBOL.read_text() == cap_array.symbol()


def test_which_side_a_plate_is_drawn_on_does_not_change_the_port_order():
    """The lesson that cost this project a miswired symbol twice."""
    moved = dict.fromkeys(analog.array_terminals(), "left")
    rearranged = cap_array.symbol()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cap_array, "sides", lambda n_bits=analog.N_BITS: moved)
        assert cap_array.symbol() != rearranged
        order = [found["name"] for found in TERMINAL.finditer(cap_array.symbol())]
    assert order == analog.array_terminals()


def test_the_stage_the_sheet_is_at_holds_its_own_contract():
    """While the generator owns the arrangement, the committed sheet is its
    output byte for byte; once a person owns it, it is held by the netlist
    comparison above instead."""
    assert cap_array.ARRANGEMENT in STAGES, f"unknown stage, not one of {STAGES}"
    if cap_array.ARRANGEMENT == "generated":
        assert cap_array.SHEET.read_text() == cap_array.sheet()


def test_regenerating_leaves_a_hand_drawn_sheet_alone(tmp_path, monkeypatch):
    """Once the arrangement is a person's, `make schematic` does not throw it
    away; what it would have written goes under build/ to be read."""
    drawing = tmp_path / cap_array.SHEET.name
    symbol = tmp_path / cap_array.SYMBOL.name
    drawing.write_text("drawn by hand\n")
    monkeypatch.setattr(cap_array, "SHEET", drawing)
    monkeypatch.setattr(cap_array, "SYMBOL", symbol)
    monkeypatch.setattr(cap_array, "PROPOSED", tmp_path / "build" / cap_array.SHEET.name)
    monkeypatch.setattr(cap_array, "ARRANGEMENT", "drawn")

    assert cap_array.main([]) == 0
    assert drawing.read_text() == "drawn by hand\n"
    assert (tmp_path / "build" / cap_array.SHEET.name).read_text() == cap_array.sheet()
    assert symbol.read_text() == cap_array.symbol(), "the symbol is generated in every stage"

    assert cap_array.main(["--force"]) == 0
    assert drawing.read_text() == cap_array.sheet(), "--force did not regenerate"


@needs_pdk
def test_the_pdks_own_symbol_still_cannot_state_the_multiplier():
    """Why the instances carry a format of their own, read from the PDK.

    The capacitor's symbol emits `MF=`; its model takes `mult` and divides its
    mismatch term by the square root of the area times it. The transistor
    symbols beside it in the same library emit `mult=`, which is how this was
    found. If a PDK bump fixes the capacitor's, this fails and the override
    can go.
    """
    library = pdk_library().parent.parent / "xschem" / cap_array.CAPACITOR
    declared = re.search(r'^format="(?P<format>[^"]*)"', library.read_text(), re.M)
    assert declared, f"{library.name} declares no format"
    assert "MF=@MF" in declared["format"], "the symbol's format changed; re-read it"
    assert "mult" not in declared["format"], "the symbol states mult now, so drop the override"

    models = (pdk_library().parent / "continuous" / "models_capacitors.spice").read_text()
    subckt = re.search(
        rf"^\.subckt\s+{re.escape(analog.sky130.MIM)}\b.*?^\.ends", models, re.M | re.S
    )
    assert subckt, "the MiM's own subcircuit is not where this reads it"
    assert "mult=1" in subckt.group(0), "the model no longer takes mult"
    assert "sqrt(wc*lc*mult)" in subckt.group(0).replace(" ", ""), "its mismatch term moved"


def test_the_sheet_and_its_symbol_are_committed():
    """A drawing nobody committed is a drawing the next checkout does not have."""
    tracked = subprocess.run(
        ["git", "ls-files", "xschem"],
        cwd=pathlib.Path(sheet.REPO),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    for path in (cap_array.SHEET, cap_array.SYMBOL):
        assert str(path.relative_to(sheet.REPO)) in tracked, f"{path.name} is not tracked"
