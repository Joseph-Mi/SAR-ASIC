"""The sweep is a regression, not a one-off. These tests are what make a
changed number a reviewable diff instead of something nobody notices."""

import numpy as np
import pytest

import sky130
from dynamic import enob_of
from interface import N_BITS
from metrics import has_missing_codes, sigma_dnl_msb_analytic
from mismatch import random_units, sigma_from_area
from yield_study import BASELINE, Study, format_table, rng_for, sweep

#: Failures a point needs before its rate is worth comparing against another's.
MIN_EVENTS_FOR_RATIO = 100

#: Two resolutions two bits apart, and the matching factor between them: the
#: amplification grows as the root of the code count, so two bits cost a
#: factor of the root of four.
LOW_BITS, HIGH_BITS = 8, 10
MATCHING_FACTOR = 2 ** ((HIGH_BITS - LOW_BITS) / 2)

#: A point's coordinates, a neighbour's, and how many draws to compare.
POINT_SIGMA, NEIGHBOUR_SIGMA = 0.01, 0.015
DRAWS = 4

#: Arrays drawn at the process's own matching floor, and how many of those
#: are converted end to end. Enough that a lost code would be seen, and few
#: enough to stay inside a second.
FLOOR_ARRAYS = 200
FLOOR_ENOB_ARRAYS = 40

#: Bits the floor is allowed to cost at the target resolution. A tenth of a
#: bit is below what any other term in the budget contributes.
FLOOR_MARGIN_BITS = 0.1

#: Digits a sweep coordinate is compared at, so float spellings of one value
#: meet.
SIGMA_DIGITS = 6

#: How closely the simulation must track the closed form; how closely two
#: failure rates at equivalent points must agree given their counting noise;
#: and how closely the closed form's own ratio must hold.
CLOSED_FORM = 0.05
RATE_AGREEMENT = 0.5
FORMULA = 0.02


@pytest.fixture(scope="module")
def study():
    return Study()


@pytest.fixture(scope="module")
def rows(study):
    return sweep(study)


def test_committed_baseline_still_reproduces(study, rows):
    """The whole point of committing the artifact. A diff here means either
    the model changed or the seeding did, and both are things to look at."""
    assert format_table(study, rows) == BASELINE.read_text()


def test_a_points_stream_depends_only_on_its_coordinates(study):
    """Adding or reordering sweep points must not move the points already in it.

    Seeding from a running generator would make every result depend on the
    sweep it happened to be run in, and nothing would be comparable to any
    earlier run.
    """
    first = rng_for(study, LOW_BITS, POINT_SIGMA).normal(size=DRAWS)
    again = rng_for(study, LOW_BITS, POINT_SIGMA).normal(size=DRAWS)
    neighbour = rng_for(study, LOW_BITS, NEIGHBOUR_SIGMA).normal(size=DRAWS)
    other_resolution = rng_for(study, HIGH_BITS, POINT_SIGMA).normal(size=DRAWS)

    assert np.array_equal(first, again)
    assert not np.array_equal(first, neighbour)
    assert not np.array_equal(first, other_resolution)


def test_simulation_tracks_the_closed_form(rows):
    """Two independent routes to the same number. Divergence means one is wrong,
    and the closed form is what sizes the array."""
    for row in rows:
        assert np.isclose(row["sigma_dnl_msb"], row["analytic"], rtol=CLOSED_FORM)


def test_missing_codes_only_get_worse_as_matching_degrades(study, rows):
    """Yield is monotonic in sigma. A non-monotonic sweep is a seeding bug."""
    for n_bits in study.resolutions:
        p = [r["p_missing"] for r in rows if r["n_bits"] == n_bits]
        assert p == sorted(p)


def test_two_more_bits_cost_a_factor_of_two_in_matching(study, rows):
    """M1's actual question. Two more bits double the mismatch amplification,
    so the same yield needs half the sigma -- not a quarter, not an eighth.

    The points come from the sweep rather than being written down, and only
    where enough arrays failed for a ratio to mean anything: a handful of
    events carries counting noise wider than the effect under test.
    """
    by_point = {(r["n_bits"], round(r["sigma_rel"], SIGMA_DIGITS)): r["p_missing"] for r in rows}
    compared = 0
    for sigma in sorted({round(r["sigma_rel"], SIGMA_DIGITS) for r in rows}):
        high = by_point.get((HIGH_BITS, sigma))
        low = by_point.get((LOW_BITS, round(MATCHING_FACTOR * sigma, SIGMA_DIGITS)))
        if high is None or low is None:
            continue
        if min(high, low) * study.trials < MIN_EVENTS_FOR_RATIO:
            continue
        compared += 1
        assert np.isclose(high, low, rtol=RATE_AGREEMENT)
    assert compared, "sweep spans no sigma pair with enough failures to compare"


def test_the_analytic_ratio_is_what_drives_that(study):
    """And the reason is the formula, not a coincidence of these seeds."""
    for sigma in study.sigmas:
        assert np.isclose(
            sigma_dnl_msb_analytic(HIGH_BITS, sigma),
            sigma_dnl_msb_analytic(LOW_BITS, MATCHING_FACTOR * sigma),
            rtol=FORMULA,
        )


def test_the_smallest_unit_the_process_draws_already_carries_the_resolution():
    """The design-closure question the sweep exists to answer, asked of the
    process rather than of an abstract matching figure.

    Matching improves with area and the process will not draw below a minimum,
    so the smallest unit is the worst matching an array can be built to have.
    If that is already good enough at the target resolution, then matching is
    not what limits this converter and area is being spent on something else.
    """
    sigma = sigma_from_area(sky130.CAP_MIN_AREA_MIM, sky130.CAP_A_C)
    rng = rng_for(Study(), N_BITS, sigma)
    units = random_units(N_BITS, sigma, rng, FLOOR_ARRAYS)
    missing = has_missing_codes(units)
    assert not missing.any(), "the process floor loses codes at the target resolution"
    bits = np.array([enob_of(u) for u in units[:FLOOR_ENOB_ARRAYS]])
    assert bits.min() > N_BITS - FLOOR_MARGIN_BITS
