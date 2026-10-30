"""The capacitor's drawing rules, against the decks that enforce them.

Every absolute capacitance in the project is checked against the PDK, by
`sim/tests/test_mim.py`, because the unit's value is what the budget hangs
from. Its *size* was not checked against anything, and the array's footprint
hangs from that: a thousand units at the wrong pitch is a floorplan that is
wrong by tens of micrometres, found when the strip is drawn.

So these read the rules out of the process, the way that one reads the model
parameters. Which file to read is most of the work: the tree ships three decks,
they disagree, and the one nothing runs is the one whose capacitor rules are
each checking the metal below the right one -- so a recipe that greps the
obvious file finds plausible numbers attached to the wrong layers. Each rule
here is read from the deck that is its authority, which is a running deck for
all of them but `capm.6`, a rule only the unused deck states at all.

No simulator, only text. The half that reads the tree skips without one; the
half that is arithmetic on what this module declares runs anywhere, and is the
half a machine with no process installed can still hold to.
"""

from __future__ import annotations

import re

import pytest

import sky130

#: Only half of this module reads the process. The other half is arithmetic on
#: the numbers it declares, and that half is the one worth running on a
#: machine with no PDK at all: a pitch formula edited wrong is caught by the
#: cheap job rather than waiting for the one that mounts a process tree.
needs_pdk = pytest.mark.skipif(
    not sky130.pdk().is_dir(), reason=f"no process tree at {sky130.pdk()}"
)

#: A rule as the KLayout deck states it: the identifier it reports and the
#: distance in the message beside it. The message rather than the call,
#: because the call is a chain of layer operations whose argument order varies
#: between rules and whose text is not the rule.
KLAYOUT_RULE = re.compile(
    r'"(?P<name>capm\.[\w]+)"\s*,?\s*\n?\s*"capm\.[\w]+\s*:[^"]*?(?P<um>[\d.]+)\s*um"'
)

#: A rule as the Magic deck states it: a keyword at the start of a line, the
#: layers, the distance in nanometres, and the message naming which rule it
#: is. The message sits on a continued line for most of them, so nothing here
#: may stop at a newline; and the distance is required to be a token of its
#: own, because the layers it sits between are spelled `via3/m3` and the first
#: digits on the line are part of a layer's name.
MAGIC_RULE = re.compile(
    r"^\s*(?:width|spacing|surround)\s"
    r'[^"]*?\s(?P<nm>\d+)\s'
    r'[^"]*?"[^"]*?\((?P<name>capm\.\w+)',
    re.M,
)

#: Nanometres per micrometre: Magic's deck keeps its distances in the smaller
#: unit and KLayout's in the larger.
PER_MICRON = 1000.0

#: Which declared constant each rule of the running KLayout deck is, and the
#: rules deliberately left out. `capm.2b_a` is `capm.11` stated a second way,
#: from the bottom plate rather than from the plate, and it is how the
#: strictest reading of that rule is corroborated -- so it is checked on its
#: own below rather than mapped to a constant here.
KLAYOUT_DECLARED = {
    "capm.1": sky130.MIM_WIDTH_MIN,
    "capm.2a": sky130.MIM_SPACING,
    "capm.2b": sky130.MIM_PLATE_SPACING,
    "capm.3": sky130.MIM_PLATE_ENCLOSURE,
}

#: And of Magic's. It states the enclosure and the width the same way, and
#: the keep-away at its strictest.
#:
#: Neither table carries the via rules, `capm.4` and `capm.5`. Nothing about
#: the array's pitch rests on them -- a contact sits inside a plate, not
#: between two -- and the decks state them from different edges rather than
#: differently: Magic's 0.08 is the running deck's 0.14 less the via's own
#: enclosure, which its message says in as many words. Declaring a number
#: nothing computes from, to pin a disagreement that is not one, is two ways
#: of being wrong at once.
MAGIC_DECLARED = {
    "capm.1": sky130.MIM_WIDTH_MIN,
    "capm.2a": sky130.MIM_SPACING,
    "capm.3": sky130.MIM_PLATE_ENCLOSURE,
    "capm.11": sky130.MIM_METAL_SPACING,
}

#: The deck nothing runs, and the layer its capacitor rules name instead of
#: the one the device's plate is on. Checked so that the day the PDK fixes it,
#: this says so rather than going on warning about it.
UNRUN = "{pdk}.lydrc"

#: The largest a plate may be drawn, as that deck states it -- the one rule
#: for which it is the only source in the tree.
SIDE_MAX = re.compile(r'"capm\.6\s*:[^"]*?([\d.]+)\s*um"')
WRONG_LAYER = re.compile(r"^(?!#).*\bm2\b.*capm|^(?!#).*capm.*\bvia2\b", re.M)

#: A side a MiM may not be drawn at, micrometres: under the minimum width and
#: over the longest side the rules allow.
TOO_SMALL, TOO_BIG = 0.5, 25.0


def klayout_rules() -> dict[str, float]:
    text = sky130.drc_klayout().read_text()
    return {m["name"]: float(m["um"]) for m in KLAYOUT_RULE.finditer(text)}


def magic_rules() -> dict[str, float]:
    text = sky130.drc_magic().read_text()
    return {m["name"]: int(m["nm"]) / PER_MICRON for m in MAGIC_RULE.finditer(text)}


@needs_pdk
def test_both_decks_the_flow_runs_are_there():
    """Named so a missing one is this, and not every rule disagreeing at once."""
    assert sky130.drc_magic().is_file(), f"{sky130.drc_magic()} is not a file"
    assert sky130.drc_klayout().is_file(), f"{sky130.drc_klayout()} is not a file"


@needs_pdk
@pytest.mark.parametrize("rule,declared", sorted(KLAYOUT_DECLARED.items()))
def test_the_declared_rule_is_the_klayout_decks(rule, declared):
    found = klayout_rules()
    assert rule in found, f"{sky130.drc_klayout().name} states no {rule}"
    assert found[rule] == pytest.approx(declared)


@needs_pdk
@pytest.mark.parametrize("rule,declared", sorted(MAGIC_DECLARED.items()))
def test_the_declared_rule_is_the_magic_decks(rule, declared):
    found = magic_rules()
    assert rule in found, f"{sky130.drc_magic().name} states no {rule}"
    assert found[rule] == pytest.approx(declared)


@needs_pdk
def test_the_keep_away_is_the_one_both_decks_agree_on():
    """The rule the tree states three ways, settled by the two that agree.

    Magic keeps unrelated metal 1.34 um from the plate. The KLayout deck says
    0.5 in its own `capm.11` and 1.2 from the bottom plate in `capm.2b_a`, and
    the bottom plate runs the enclosure past the plate -- so that second
    statement is Magic's number and the first is not. Two expressions against
    one, and the strictest is the corroborated one, which is the only
    direction in which being wrong is safe.
    """
    klayout, magic = klayout_rules(), magic_rules()
    for deck, found, wanted in (
        (sky130.drc_klayout(), klayout, ("capm.2b_a", "capm.11")),
        (sky130.drc_magic(), magic, ("capm.11",)),
    ):
        for rule in wanted:
            assert rule in found, f"{deck.name} states no {rule}"
    from_plate = klayout["capm.2b_a"] + sky130.MIM_PLATE_ENCLOSURE
    assert from_plate == pytest.approx(magic["capm.11"])
    assert sky130.MIM_METAL_SPACING == pytest.approx(from_plate)
    assert klayout["capm.11"] < sky130.MIM_METAL_SPACING


@needs_pdk
def test_the_largest_plate_is_a_rule_our_own_drc_would_not_catch():
    """`capm.6` exists and neither running deck codes it, which is why the
    bound is declared and checked in arithmetic instead. Read from the deck
    nothing runs, because that is the only deck it is in -- the one place in
    this module where that file is the authority, and it is the authority for
    a rule rather than for a layer."""
    # Not `pytest.skip` when the deck is gone, however much that reads like
    # the right way to say "nothing to check here": the job this runs in sets
    # SAR_REQUIRE_TOOLS, and the root conftest turns every skip into a
    # failure. A skip on the path a PDK bump is expected to take would fail
    # the analog job for doing what was hoped for.
    unrun = sky130.pdk() / "libs.tech/klayout/drc" / UNRUN.format(pdk=sky130.pdk().name)
    stated = SIDE_MAX.search(unrun.read_text()) if unrun.is_file() else None
    assert not unrun.is_file() or stated, (
        f"{unrun.name} no longer states capm.6: find where the bound moved to, "
        "because MIM_SIDE_MAX is read from nowhere else"
    )
    if stated:
        assert sky130.MIM_SIDE_MAX == pytest.approx(float(stated.group(1)))
    # These hold whether that deck is shipped or not, and they are the half of
    # this worth knowing: the rule exists and our own DRC does not check it.
    assert "capm.6" not in sky130.drc_klayout().read_text()
    assert "capm.6" not in sky130.drc_magic().read_text()


@needs_pdk
def test_the_deck_nothing_runs_still_names_the_wrong_metal():
    """Why the constants above are not read from the file a search finds first.

    It is the deck named after the process and its numbers are mostly the same
    numbers, so nothing about reading it looks like a mistake. Its capacitor
    rules name the metal one layer below the device's plate throughout. When
    the PDK fixes that, this fails, and the warning written beside the
    constants can come out.
    """
    # Gone is the fix, and so is fixed, so both pass -- and for the reason
    # above, neither may be spelled as a skip.
    unrun = sky130.pdk() / "libs.tech/klayout/drc" / UNRUN.format(pdk=sky130.pdk().name)
    assert not unrun.is_file() or WRONG_LAYER.search(unrun.read_text()), (
        f"{unrun.name} no longer names m2/via2 in its capm rules: "
        "re-read it, and drop the warning in tech/sky130.py if it is now right"
    )


def test_the_unit_the_project_draws_is_one_the_process_draws():
    """The check the declared area never had. It is the project's own floor
    and not the process's, so what holds it is the rule and not itself."""
    side = sky130.mim_side()
    assert side >= sky130.MIM_WIDTH_MIN
    assert side <= sky130.MIM_SIDE_MAX
    assert sky130.mim_pitch(side) > side


def test_a_branch_boundary_is_wider_than_a_step_inside_a_branch():
    """And by the bottom plate's doing, not the capacitor's. This is what
    makes the array's footprint a consequence of its placement scheme."""
    side = sky130.mim_side()
    assert sky130.mim_pitch(side, shared=True) == pytest.approx(side + sky130.MIM_SPACING)
    assert sky130.mim_pitch(side, shared=False) == pytest.approx(
        side + 2 * sky130.MIM_PLATE_ENCLOSURE + sky130.MIM_PLATE_SPACING
    )
    assert sky130.mim_pitch(side, shared=False) > sky130.mim_pitch(side, shared=True)


def test_a_row_of_one_unit_is_the_unit():
    """The arithmetic's own edge, where a pitch has nowhere to be counted."""
    side = sky130.mim_side()
    assert sky130.mim_row(1, side) == pytest.approx(side)
    assert sky130.mim_row(2, side) == pytest.approx(side + sky130.mim_pitch(side))


def test_the_square_block_rounds_up_and_carries_its_ring():
    """A perfect square must not gain a row it puts nothing in, which is what
    the float route does at the resolutions this array is built at."""
    assert sky130.mim_array_side(1024, ring=0) == 32
    assert sky130.mim_array_side(1025, ring=0) == 33
    assert sky130.mim_array_side(1024, ring=1) == 34
    assert sky130.mim_array_side(1, ring=0) == 1


def test_a_strip_too_shallow_for_a_row_says_so_rather_than_refusing():
    """Zero rows is a floorplan to change and not a geometry error, so it is an
    answer. A side the process will not draw is the error, and it stays one
    however shallow the strip -- otherwise the two are reported the same way.
    """
    side = sky130.mim_side()
    assert sky130.mim_rows_within(side, side) == 0
    assert sky130.mim_rows_within(1000.0, side) > sky130.mim_rows_within(100.0, side)
    # And a ring costs rows, so asking for one leaves room for fewer.
    assert (
        sky130.mim_rows_within(100.0, side, ring=1)
        < sky130.mim_rows_within(100.0, side, ring=0) + 2
    )
    with pytest.raises(ValueError):
        sky130.mim_rows_within(1.0, TOO_SMALL)


def test_the_ring_steps_at_the_wider_pitch_whatever_the_branches_do():
    """Because a dummy carries no charge, so it is tied off somewhere of its
    own and is a different net from the branch beside it. Which makes the
    narrow pitch unreachable on any axis a ring crosses, and a figure that
    applied it to every step of a ringed array described an array nobody can
    place."""
    side = sky130.mim_side()
    assert sky130.mim_ring_step(side, 1) == pytest.approx(2 * sky130.mim_pitch(side, shared=False))
    assert sky130.mim_ring_step(side, 0) == 0.0
    grouped = sky130.mim_array_extent(1024, side, ring=1, shared=True)
    assert grouped > sky130.mim_row(sky130.mim_array_side(1024, 1), side, shared=True)
    with pytest.raises(ValueError):
        sky130.mim_ring_step(side, -1)


def test_the_interleaved_block_is_the_one_figure_a_ring_does_not_move():
    """Its every step is already the wider one, the ring's included, so the
    two expressions have to agree -- which is what says the ring is being
    charged at that pitch and not at some third thing."""
    side = sky130.mim_side()
    assert sky130.mim_array_extent(1024, side, ring=1, shared=False) == pytest.approx(
        sky130.mim_row(sky130.mim_array_side(1024, 1), side, shared=False)
    )


def test_the_keep_out_is_the_block_plus_the_rule_on_both_sides():
    extent = sky130.mim_array_extent(1024, sky130.mim_side())
    assert sky130.mim_keep_out(extent) == pytest.approx(extent + 2 * sky130.MIM_METAL_SPACING)


@pytest.mark.parametrize(
    "call",
    [
        lambda: sky130.mim_pitch(TOO_SMALL),
        lambda: sky130.mim_pitch(TOO_BIG),
        lambda: sky130.mim_row(0, 2.0),
        lambda: sky130.mim_array_side(0),
        lambda: sky130.mim_array_side(1024, ring=-1),
        lambda: sky130.mim_keep_out(0.0),
    ],
)
def test_a_geometry_the_rules_do_not_allow_is_refused(call):
    """Refused rather than extrapolated, the way the capacitance expressions
    are. A pitch returned for a plate the process will not draw is a number
    that looks like every other number and a floorplan built on nothing."""
    with pytest.raises(ValueError):
        call()


def test_the_fit_and_the_square_bound_are_different_answers():
    """And the fit is the smaller one, which is the whole reason it exists.

    `mim_array_extent` is the array drawn square; `mim_fit` is the array drawn
    to a strip. Where the strip is shallower than the square array is wide,
    the fit trades height for length and reaches further along the strip while
    needing less of its height -- so a square figure read against a strip
    height answers a question nobody asked. Reversing a size decision once was
    the cost of not having this (DD-16).
    """
    side = sky130.mim_side()
    height = 95.76  # the declared split's strip, named here as the case that bit
    square = sky130.mim_keep_out(sky130.mim_array_extent(1024, side, ring=1, shared=False))
    placed = sky130.mim_fit(1024, side, height, ring=1, shared=False)
    assert placed is not None, "the strip that the array was drawn for holds no row"
    rows, per_row, reach = placed
    assert square > height, "the square array fits; this test's premise is stale"
    assert reach > square, "trading height for length should reach further"
    assert rows * per_row >= 1024
    assert sky130.mim_rows_within(height, side, ring=1, shared=False) == rows


def test_a_strip_too_shallow_for_a_row_has_no_fit():
    """Rather than a row nobody can draw. `mim_rows_within` answers zero for
    the same case and this composes it, so the two agree about a floorplan
    that does not work."""
    side = sky130.mim_side()
    assert sky130.mim_fit(1024, side, side) is None
    assert sky130.mim_rows_within(side, side) == 0


@needs_pdk
def test_the_contact_and_upper_pad_rules_are_read_from_the_running_deck():
    deck = sky130.drc_klayout().read_text()
    contact = re.search(r"via3_not_mt\.width\(([\d.]+),", deck)
    area = re.search(r"m4\.with_area\(0\.\.([\d.]+)\)", deck)
    grid = re.search(r"^\s*gridlimit\s+(\d+)", sky130.drc_magic().read_text(), re.M)
    assert contact and area and grid
    assert sky130.MIM_CONTACT_SIDE == pytest.approx(float(contact.group(1)))
    assert sky130.METAL4_MIN_AREA == pytest.approx(float(area.group(1)))
    assert sky130.LAYOUT_GRID == pytest.approx(float(grid.group(1)) / PER_MICRON)
    for name, spec in (
        ("m3", sky130.MIM_GDS_BOTTOM),
        ("via3", sky130.MIM_GDS_CONTACT),
        ("m4", sky130.MIM_GDS_UPPER),
    ):
        found = re.search(rf'{name}_wildcard = "(\d+)/(\d+)"', deck)
        assert found and tuple(int(v) for v in found.groups()) == spec
    assert f"capm = polygons{sky130.MIM_GDS_PLATE}" in deck
