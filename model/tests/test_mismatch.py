"""Mismatch generators. Statistical claims are checked at sample sizes large
enough that a passing run is evidence rather than luck."""

import numpy as np
import pytest

from mismatch import (
    SKY130_CAP_A_C,
    area_for_sigma,
    cap_for_area,
    gradient,
    place,
    random_units,
    row_major,
    sigma_from_area,
)
from sar import branch_weights

RESOLUTIONS = (4, 8, 10)


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_batch_shape_is_trials_by_units(n_bits):
    rng = np.random.default_rng(0)
    assert random_units(n_bits, 0.01, rng).shape == (2**n_bits,)
    assert random_units(n_bits, 0.01, rng, trials=7).shape == (7, 2**n_bits)


def test_draws_have_the_requested_spread():
    """sigma_rel means sigma_u/C_u, so it must come back out of the sample."""
    rng = np.random.default_rng(1)
    u = random_units(10, 0.02, rng, trials=500)
    assert np.isclose(u.mean(), 1.0, atol=1e-3)
    assert np.isclose(u.std(), 0.02, rtol=0.02)


def test_same_seed_gives_the_same_array():
    a = random_units(8, 0.01, np.random.default_rng(42))
    b = random_units(8, 0.01, np.random.default_rng(42))
    assert np.array_equal(a, b)


def test_zero_sigma_is_a_perfect_array():
    u = random_units(8, 0.0, np.random.default_rng(3))
    assert np.array_equal(u, np.ones(2**8))


def test_gradient_tilts_without_changing_total():
    """A gradient redistributes capacitance; it does not add any.

    If it changed the total it would move full scale, and a full-scale shift
    is a gain error rather than the matching effect under study.
    """
    u = np.ones(2**8)
    g = gradient(u, 0.01)
    assert np.isclose(g.sum(), u.sum())
    assert np.isclose(g[-1] - g[0], 0.01, rtol=1e-9)


def test_gradient_of_zero_strength_changes_nothing():
    u = random_units(8, 0.01, np.random.default_rng(5))
    assert np.allclose(gradient(u, 0.0), u)


def test_row_major_placement_is_the_identity():
    u = random_units(8, 0.01, np.random.default_rng(6))
    assert np.array_equal(place(u, row_major(8)), u)


def test_placement_moves_mismatch_between_branches():
    """A permutation conserves total capacitance but not the branch weights.

    That is the entire mechanism a centroid scheme exploits: same units, same
    total, different DNL.
    """
    rng = np.random.default_rng(7)
    u = random_units(8, 0.02, rng)
    shuffled = place(u, rng.permutation(2**8))
    assert np.isclose(shuffled.sum(), u.sum())
    assert not np.allclose(branch_weights(shuffled), branch_weights(u))


def test_pelgrom_is_a_square_root_law():
    """Four times the area is half the sigma. This is the whole reason unit
    caps are large, and the exchange rate the sizing decision is paying."""
    a_c = 1.0
    assert np.isclose(sigma_from_area(4.0, a_c), sigma_from_area(1.0, a_c) / 2)


def test_area_and_sigma_invert_each_other():
    a_c = 1.5
    for area in (0.25, 1.0, 9.0):
        assert np.isclose(area_for_sigma(sigma_from_area(area, a_c), a_c), area)


def test_capacitance_follows_area_at_fixed_density():
    assert np.isclose(cap_for_area(2.0, 1.5), 3.0)


def test_the_coefficient_is_read_as_percent_not_fraction():
    """A_C is quoted in percent-micrometres and sigma_from_area returns a
    fraction, so a unit capacitor of one square micrometre must come back as
    the coefficient over a hundred. Getting that conversion wrong scales every
    area in the study by ten thousand and still looks plausible."""
    assert np.isclose(sigma_from_area(1.0, SKY130_CAP_A_C), SKY130_CAP_A_C / 100)


def test_the_sizing_direction_round_trips():
    """A matching target becomes an area, and that area has to give the target
    back. This is the direction the design decision actually runs."""
    for target in (0.005, 0.010, 0.020):
        area = area_for_sigma(target, SKY130_CAP_A_C)
        assert np.isclose(sigma_from_area(area, SKY130_CAP_A_C), target)
