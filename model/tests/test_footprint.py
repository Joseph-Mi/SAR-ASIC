"""Whether the array the contract asks for fits the strip the split gives it.

The one question in this repository that needs the process's drawing rules,
the platform's die and the contract's resolution at the same time, which is
why it sits here: `tech/` holds the rules and the die but may not know the
resolution, and knowing all three is what this layer is for.

It was an open finding rather than a number -- a square array plus a dummy
ring at MiM pitch might not fit the analog strip once power-stripe margins
came off -- and the reason it stayed open is that the pitch had never been
read out of the process. It is read now (`tech/tests/test_drc.py`), so the
finding is arithmetic, and the arithmetic says the finding was right: the
square array misses by four micrometres at the most compact pitch an array of
several branches could have, and by twenty-four at the matched one.

What fits is the same array not drawn square. The strip is three times as wide
as it is tall, so the rows are what the height decides and the columns have
room to spare. Square is the shape that makes a gradient shortest in both
directions, and losing it is the real cost here -- paid in matching along the
array's long axis, not in area.

One figure here is a bound rather than a layout, and it is the compact one.
The narrow pitch belongs to two units of the same branch, so claiming it for
every step of an array means claiming no branch boundary falls on that axis.
No placement of several branches does that, and the ring never does: a dummy
carries no charge, so it is tied off on its own and the step across it is the
wider one whatever the branches inside do.
"""

from __future__ import annotations

import pytest

import sky130
import template
from interface import N_BITS

#: One ring of dummies around the array: the units that carry charge are the
#: interior ones, and the perimeter is there to be their neighbour.
RING = 1

#: Units the array is made of. Two to the resolution, stated nowhere else: a
#: footprint computed from a stale count is wrong in the direction that looks
#: fine, because fewer units always fit.
UNITS = 2**N_BITS


def square(shared: bool, ring: int = RING) -> float:
    """What a square array needs of either dimension, keep-away included."""
    return sky130.mim_keep_out(sky130.mim_array_extent(UNITS, sky130.mim_side(), ring, shared))


def reaches(units: int, shared: bool) -> float:
    """How far that many charge-carrying units reach, ring and keep-away on."""
    side = sky130.mim_side()
    return sky130.mim_keep_out(
        sky130.mim_row(units, side, shared) + sky130.mim_ring_step(side, RING)
    )


def laid_to_the_strip(shared: bool) -> tuple[int, int]:
    """The same array shaped to the strip: how many rows and columns of units.

    The rows are whatever the height holds, and the columns are then however
    many it takes to hold every unit that carries charge. Composed here rather
    than in `tech/`, because how many rows to spend is a floorplan choice and
    the process only says how far a row reaches. Both counts are of the units
    inside the ring.
    """
    _, height = template.analog_strip()
    rows = sky130.mim_rows_within(height, sky130.mim_side(), RING, shared) - 2 * RING
    assert rows > 0, f"a {height} um strip holds too few rows to ring"
    return rows, -(-UNITS // rows)


def test_the_square_array_does_not_fit_the_strip():
    """The open finding, measured, and the reason the array is not square.

    Both placements miss, and the compact one is a bound rather than a layout,
    so this is not a choice between them: it is the shape that has to go. When
    this fails -- a larger split, a smaller unit, a rule relaxed -- the array
    can be square again, and the paragraphs above about a gradient's symmetry
    and about bounds come out with it.
    """
    _, height = template.analog_strip()
    for shared in (True, False):
        assert square(shared) > height, (
            f"a square array now fits the {height:.2f} um strip with "
            f"{height - square(shared):.2f} um to spare: it can be drawn square"
        )


def test_the_ring_is_what_costs_the_square_array_its_fit():
    """At the compact bound, where it is the whole of the overrun. It holds no
    charge, is drawn, and is paid for in area, which makes it the part of a
    budget most easily left out of one -- and it is charged at the wider pitch
    on top of that, being a net of its own."""
    _, height = template.analog_strip()
    assert square(shared=True, ring=0) < height
    assert square(shared=True, ring=RING) > height
    assert square(shared=True, ring=RING) - height < sky130.mim_ring_step(sky130.mim_side(), RING)


@pytest.mark.parametrize("shared", (True, False))
def test_the_array_fits_the_strip_once_it_is_shaped_to_it(shared):
    """And with either placement, which is what makes the shape the answer."""
    width, height = template.analog_strip()
    rows, columns = laid_to_the_strip(shared)
    assert reaches(rows, shared) <= height, (
        f"{rows} rows need {reaches(rows, shared):.2f} um of a {height:.2f} um strip"
    )
    assert reaches(columns, shared) < width, (
        f"{rows} rows of {columns} need {reaches(columns, shared):.1f} um of a {width:.1f} um strip"
    )
    assert rows * columns >= UNITS


def test_one_more_row_than_fits_does_not_fit():
    """What makes the row count a measurement rather than a formula with a
    margin hidden in it: the next row over is the one that misses."""
    _, height = template.analog_strip()
    for shared in (True, False):
        rows, _ = laid_to_the_strip(shared)
        assert reaches(rows + 1, shared) > height


def test_the_placement_scheme_is_what_moves_the_footprint():
    """And by enough to matter to the floorplan rather than to a diagram.

    Units of one branch share a bottom plate and step at the plate-to-plate
    spacing; units of different branches do not and step at the wider metal
    spacing. So grouping each branch is the compact array and interleaving
    them is the matched one, and the gradient a common-centroid scheme cancels
    is paid for in tile area. These are what that trade costs.
    """
    grouped, interleaved = laid_to_the_strip(True), laid_to_the_strip(False)
    assert grouped[0] > interleaved[0], "the compact pitch must fit more rows"
    assert reaches(grouped[1], True) < reaches(interleaved[1], False), (
        "and need less width for the same units"
    )


def test_the_strip_is_what_the_split_leaves_of_the_die():
    """Read rather than restated: the die comes out of the vendored template
    and the split is the one decision on top of it, so the strip cannot drift
    from either."""
    _, die = template.die_area()
    width, height = template.analog_strip()
    assert (width, height + template.DIGITAL_HEIGHT) == template.die_area()
    assert 0.0 < height < die


def test_the_keep_away_is_most_of_three_micrometres_of_it():
    """Why the array's own extent is not the number that has to fit. A power
    stripe is unrelated metal, and the rule holds it off every plate."""
    extent = sky130.mim_array_extent(UNITS, sky130.mim_side(), RING)
    assert square(shared=False) - extent == pytest.approx(2 * sky130.MIM_METAL_SPACING)
