"""Mismatch generators. Statistical claims are checked at sample sizes large
enough that a passing run is evidence rather than luck."""

import numpy as np
import pytest

import sky130
from mismatch import (
    PERCENT,
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

#: The resolution the single-array tests use.
N_BITS = 8

#: A mismatch small enough to keep every array monotonic, one large enough to
#: move branch weights visibly, and a gradient strength across the array.
SIGMA = 0.01
SIGMA_LARGE = 0.02
TILT = 0.01

#: A batch size, and a sample large enough that its spread is the requested
#: one to within the tolerances below.
BATCH = 7
SAMPLE = 500
MEAN_TOLERANCE = 1e-3
SPREAD_TOLERANCE = 0.02
EXACT = 1e-9

#: Seeds, one per test, so no test's draws depend on another's.
SEED_SHAPE, SEED_SPREAD, SEED_ZERO, SEED_GRADIENT, SEED_PLACE, SEED_PERMUTE, SEED_REPEAT = (
    0,
    1,
    3,
    5,
    6,
    7,
    42,
)

#: Pelgrom's law checked at a unit area and four times it; a coefficient, a
#: second one, and areas to round-trip through it; a density.
UNIT_AREA, QUADRUPLE = 1.0, 4.0
A_C, A_C_OTHER = 1.0, 1.5
AREAS = (0.25, 1.0, 9.0)
DENSITY = 1.5

#: Matching targets the sizing decision might ask for.
TARGETS = (0.005, 0.010, 0.020)


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_batch_shape_is_trials_by_units(n_bits):
    rng = np.random.default_rng(SEED_SHAPE)
    assert random_units(n_bits, SIGMA, rng).shape == (2**n_bits,)
    assert random_units(n_bits, SIGMA, rng, trials=BATCH).shape == (BATCH, 2**n_bits)


def test_draws_have_the_requested_spread():
    """sigma_rel means sigma_u/C_u, so it must come back out of the sample."""
    rng = np.random.default_rng(SEED_SPREAD)
    u = random_units(max(RESOLUTIONS), SIGMA_LARGE, rng, trials=SAMPLE)
    assert np.isclose(u.mean(), 1.0, atol=MEAN_TOLERANCE)
    assert np.isclose(u.std(), SIGMA_LARGE, rtol=SPREAD_TOLERANCE)


def test_same_seed_gives_the_same_array():
    a = random_units(N_BITS, SIGMA, np.random.default_rng(SEED_REPEAT))
    b = random_units(N_BITS, SIGMA, np.random.default_rng(SEED_REPEAT))
    assert np.array_equal(a, b)


def test_zero_sigma_is_a_perfect_array():
    u = random_units(N_BITS, 0.0, np.random.default_rng(SEED_ZERO))
    assert np.array_equal(u, np.ones(2**N_BITS))


def test_gradient_tilts_without_changing_total():
    """A gradient redistributes capacitance; it does not add any.

    If it changed the total it would move full scale, and a full-scale shift
    is a gain error rather than the matching effect under study.
    """
    u = np.ones(2**N_BITS)
    g = gradient(u, TILT)
    assert np.isclose(g.sum(), u.sum())
    assert np.isclose(g[-1] - g[0], TILT, rtol=EXACT)


def test_gradient_of_zero_strength_changes_nothing():
    u = random_units(N_BITS, SIGMA, np.random.default_rng(SEED_GRADIENT))
    assert np.allclose(gradient(u, 0.0), u)


def test_row_major_placement_is_the_identity():
    u = random_units(N_BITS, SIGMA, np.random.default_rng(SEED_PLACE))
    assert np.array_equal(place(u, row_major(N_BITS)), u)


def test_placement_moves_mismatch_between_branches():
    """A permutation conserves total capacitance but not the branch weights.

    That is the entire mechanism a centroid scheme exploits: same units, same
    total, different DNL.
    """
    rng = np.random.default_rng(SEED_PERMUTE)
    u = random_units(N_BITS, SIGMA_LARGE, rng)
    shuffled = place(u, rng.permutation(2**N_BITS))
    assert np.isclose(shuffled.sum(), u.sum())
    assert not np.allclose(branch_weights(shuffled), branch_weights(u))


def test_pelgrom_is_a_square_root_law():
    """Four times the area is half the sigma. This is the whole reason unit
    caps are large, and the exchange rate the sizing decision is paying."""
    bigger = sigma_from_area(QUADRUPLE * UNIT_AREA, A_C)
    assert np.isclose(bigger, sigma_from_area(UNIT_AREA, A_C) / np.sqrt(QUADRUPLE))


def test_area_and_sigma_invert_each_other():
    for area in AREAS:
        assert np.isclose(area_for_sigma(sigma_from_area(area, A_C_OTHER), A_C_OTHER), area)


def test_capacitance_follows_area_at_fixed_density():
    assert np.isclose(cap_for_area(QUADRUPLE, DENSITY), QUADRUPLE * DENSITY)


def test_the_coefficient_is_read_as_percent_not_fraction():
    """A_C is quoted in percent-micrometres and sigma_from_area returns a
    fraction, so a unit capacitor of one square micrometre must come back as
    the coefficient in percent. Getting that conversion wrong scales every
    area in the study by ten thousand and still looks plausible."""
    assert np.isclose(sigma_from_area(UNIT_AREA, sky130.CAP_A_C), sky130.CAP_A_C / PERCENT)


def test_the_sizing_direction_round_trips():
    """A matching target becomes an area, and that area has to give the target
    back. This is the direction the design decision actually runs."""
    for target in TARGETS:
        area = area_for_sigma(target, sky130.CAP_A_C)
        assert np.isclose(sigma_from_area(area, sky130.CAP_A_C), target)
