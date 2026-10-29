"""The unit capacitor study: that it reproduces, and what it says.

The table is arithmetic on declared facts, so a regression here is a change in
one of those facts -- the process's capacitance, its drawing rules, the pin
resistance the platform specifies, or a law in `model/`. The baseline is
committed so that such a change arrives as a diff rather than as a number
nobody compared.

The rest of this asserts the shape of the answer rather than its digits: which
way each column moves with size, and the two findings the study exists to
produce -- that matching is not what decides this, and that the smallest unit
the process draws is the one whose array fits the strip however it is placed.
"""

from __future__ import annotations

import pytest

import sky130
import template
from interface import N_BITS
from unit_study import BASELINE, Study, format_table, run_point, sweep


@pytest.fixture(scope="module")
def study() -> Study:
    return Study()


@pytest.fixture(scope="module")
def rows(study) -> list[dict]:
    return sweep(study)


def test_the_committed_baseline_still_reproduces(study, rows):
    """Nothing here is random, so this is a strict equality: a difference is
    a fact that moved, and the diff says which column it moved."""
    assert format_table(study, rows) == BASELINE.read_text()


def test_the_table_covers_the_size_the_project_draws(study):
    """The sweep has to contain today's unit, or it compares candidates
    against a point that is not in it."""
    assert sky130.mim_side() in study.sides


def test_a_unit_below_the_process_minimum_is_refused(study):
    """The floor is a drawing rule and not a preference: `capm.1` is the only
    size rule either running deck states for the MiM."""
    with pytest.raises(ValueError):
        run_point(study, sky130.MIM_WIDTH_MIN / 2)


def test_a_bigger_unit_matches_better_and_takes_more_room(rows):
    """Pelgrom one way and geometry the other, which is the whole trade."""
    for smaller, bigger in zip(rows, rows[1:], strict=False):
        assert bigger["sigma_rel"] < smaller["sigma_rel"]
        assert bigger["sigma_dnl_msb"] < smaller["sigma_dnl_msb"]
        assert bigger["noise_lsb"] < smaller["noise_lsb"]
        assert bigger["block_group"] > smaller["block_group"]
        assert bigger["block_inter"] > smaller["block_inter"]
        assert bigger["tau_fixed_ns"] > smaller["tau_fixed_ns"]


def test_interleaving_always_costs_room(rows):
    """A common-centroid array pays the inter-net pitch at nearly every step,
    so the matched placement is the wide one at every size."""
    for row in rows:
        assert row["block_inter"] > row["block_group"]


def test_matching_is_not_what_decides_this(rows):
    """Every candidate leaves the MSB's spread far inside half an LSB and
    kT/C far under the LSB. Stated as a test because it is the finding: the
    size is chosen on area and on what the switch's charge is worth, and a
    reader who assumes matching binds will choose the wrong one.
    """
    for row in rows:
        assert row["sigma_dnl_msb"] < 0.5, row
        assert row["noise_lsb"] < 0.5, row


def test_the_parasitic_this_counts_is_not_what_decides_it_either(rows):
    """The top switch's diffusion leaves the comparator essentially the whole
    swing at every size. What this column does not count -- the comparator's
    own input and the routing over the array -- is pinned where it can be
    measured, by `sim/tests/test_strongarm.py`."""
    for row in rows:
        assert row["swing_gain"] > 0.99, row


def test_the_smallest_unit_is_the_one_that_fits_however_it_is_placed(rows):
    """The finding the floorplan was waiting on.

    A square array plus its dummy ring does not fit the strip at the size the
    project draws today, and it does at the smallest the process draws --
    interleaved, which is the placement that cancels a gradient and the one
    that costs the most room. So the choice between grouped and interleaved
    stops being a choice between symmetry and fit.
    """
    _, height = template.analog_strip()
    smallest, today = rows[0], next(r for r in rows if r["side_um"] == sky130.mim_side())
    assert smallest["side_um"] == sky130.MIM_WIDTH_MIN
    assert smallest["block_inter"] < height
    assert today["block_inter"] > height
    assert today["block_group"] > height


def test_a_smaller_array_buys_a_narrower_switch_and_less_charge(rows):
    """The part that is not a trade.

    The sampling loop is R times C, so a smaller array settles faster, and
    the speed can be given back as a narrower top switch -- whose width is
    what its charge on the top plate is proportional to. Below today's size
    the switch shrinks faster than the array does, so holding the clock makes
    the injection *better*, not worse. Keeping the switch as it is instead
    makes it worse, and that is the other column.
    """
    today = next(r for r in rows if r["side_um"] == sky130.mim_side())
    assert today["inject_scaled"] == pytest.approx(1.0)
    assert today["inject_fixed"] == pytest.approx(1.0)
    smaller = [r for r in rows if r["side_um"] < sky130.mim_side()]
    assert smaller, "the sweep has nothing below today's unit to compare"
    for row in smaller:
        assert row["w_top_um"] < sky130.TOP_SWITCH_WIDTH
        assert row["inject_scaled"] < 1.0
        assert row["inject_fixed"] > 1.0


def test_a_bigger_unit_cannot_hold_the_clock_at_any_switch(rows):
    """Above today's size the loop is lost before the switch is reached.

    The pins are 500 ohms each and are in series with it, so a large enough
    array exceeds today's time constant on the pins alone -- the narrowest
    switch the process draws is then the best available and the clock slows
    anyway. Which is why `inject_scaled` is only comparable between rows
    whose `tau_min_ns` is today's.
    """
    today = next(r for r in rows if r["side_um"] == sky130.mim_side())
    for row in [r for r in rows if r["side_um"] > sky130.mim_side()]:
        assert row["w_top_um"] == sky130.W_MIN
        assert row["tau_min_ns"] > today["tau_min_ns"]


def test_the_resolution_the_table_is_written_for_is_the_declared_one(study):
    """A study of the array has to be a study of this array."""
    assert study.n_bits == N_BITS
