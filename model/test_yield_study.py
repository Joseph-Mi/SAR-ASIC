"""The sweep is a regression, not a one-off. These tests are what make a
changed number a reviewable diff instead of something nobody notices."""

import numpy as np
import pytest

from metrics import sigma_dnl_msb_analytic
from yield_study import BASELINE, Study, format_table, rng_for, sweep


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
    sweep it happened to be run in, and nothing would be comparable to
    anything from last week.
    """
    first = rng_for(study, 8, 0.01).normal(size=4)
    again = rng_for(study, 8, 0.01).normal(size=4)
    neighbour = rng_for(study, 8, 0.015).normal(size=4)
    other_resolution = rng_for(study, 10, 0.01).normal(size=4)

    assert np.array_equal(first, again)
    assert not np.array_equal(first, neighbour)
    assert not np.array_equal(first, other_resolution)


def test_simulation_tracks_the_closed_form(rows):
    """Two independent routes to the same number. Divergence means one is wrong,
    and the closed form is what sizes the array."""
    for row in rows:
        assert np.isclose(row["sigma_dnl_msb"], row["analytic"], rtol=0.05)


def test_missing_codes_only_get_worse_as_matching_degrades(study, rows):
    """Yield is monotonic in sigma. A non-monotonic sweep is a seeding bug."""
    for n_bits in study.resolutions:
        p = [r["p_missing"] for r in rows if r["n_bits"] == n_bits]
        assert p == sorted(p)


def test_ten_bits_costs_a_factor_of_two_in_matching(rows):
    """M1's actual question. Two more bits double the mismatch amplification,
    so the same yield needs half the sigma -- not a quarter, not an eighth."""
    by_point = {(r["n_bits"], round(r["sigma_rel"], 6)): r["p_missing"] for r in rows}
    for sigma in (0.015, 0.020):
        ten = by_point[(10, sigma)]
        eight = by_point[(8, round(2 * sigma, 6))]
        assert ten > 0.0
        assert np.isclose(ten, eight, rtol=0.5)


def test_the_analytic_ratio_is_what_drives_that(study):
    """And the reason is the formula, not a coincidence of these seeds."""
    for sigma in study.sigmas:
        assert np.isclose(
            sigma_dnl_msb_analytic(10, sigma),
            sigma_dnl_msb_analytic(8, 2 * sigma),
            rtol=0.02,
        )
