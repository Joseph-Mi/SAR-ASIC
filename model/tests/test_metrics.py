"""Metrics are exercised on arrays we construct, so they are independent of the
conversion loop -- a bug in one cannot hide a bug in the other."""

import numpy as np
import pytest

from metrics import (
    dnl,
    has_missing_codes,
    inl,
    msb_dnl,
    sigma_dnl_msb_analytic,
    transition_voltages,
)
from sar import branch_weights, dac_voltage, ideal_units

# The structural metrics must hold at every resolution. Tests that assert a
# magnitude rather than a shape stay pinned to a single N, because the
# magnitude is exactly what changes with it.
RESOLUTIONS = (4, 8, 10)
N_BITS = 8
VREF = 1.0

#: Exact arithmetic on an ideal array agrees to this.
ROUNDING = 1e-12
FLOAT_EXACT = 1e-15

#: How much smaller the MSB branch's units are made, to damage one step.
SHRINK = 0.99

#: The Monte Carlo against the closed form: mismatch, draws, seed, and how
#: closely the simulated spread must land with that many draws.
SIGMA = 0.02
DRAWS = 4000
SEED = 12345
MC_TOLERANCE = 0.05

#: Two resolutions a quarter apart in bits, and the matching ratio between
#: them the formula predicts: sqrt((2^10 - 1) / (2^8 - 1)), within rounding.
LOW_BITS, HIGH_BITS = 8, 10
RATIO_TOLERANCE = 0.01

#: A mismatched array for comparing the two curve implementations.
CURVE_SEED = 7


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_ideal_array_is_perfectly_linear(n_bits):
    u = ideal_units(n_bits)
    assert np.allclose(dnl(u), 0.0, atol=ROUNDING)
    assert np.allclose(inl(u), 0.0, atol=ROUNDING)
    assert not has_missing_codes(u)


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_one_lsb_step_is_one_unit(n_bits):
    u = ideal_units(n_bits)
    v = transition_voltages(u)
    assert np.isclose(v[1] - v[0], VREF / 2**n_bits)


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_msb_dnl_indexes_the_worst_transition(n_bits):
    """Shrink only the MSB branch and the damage must appear at the MSB step.

    Asserting it is the *worst* step rather than a fixed magnitude is what
    makes this resolution-independent: the size of the error scales with
    2**N, its location does not.
    """
    u = ideal_units(n_bits)
    msb_step = 2 ** (n_bits - 1) - 1
    u[msb_step:] *= SHRINK
    d = dnl(u)
    assert msb_dnl(u) == d[msb_step]
    assert msb_dnl(u) == d.min()


def test_monte_carlo_matches_the_analytic_formula():
    """Simulated spread must match the closed form. One of them is wrong
    otherwise, and the closed form is what sizes the array."""
    u = ideal_units(N_BITS)
    rng = np.random.default_rng(SEED)
    trials = [msb_dnl(u * (1 + rng.normal(0, SIGMA, u.size))) for _ in range(DRAWS)]
    simulated = np.std(trials)
    predicted = sigma_dnl_msb_analytic(N_BITS, SIGMA)
    assert np.isclose(simulated, predicted, rtol=MC_TOLERANCE)


def test_more_bits_needs_matching_tighter_by_the_root_of_the_code_ratio():
    """The LSB-referred requirement scales as sqrt(2**N - 1), and that formula
    is already in LSB -- so two more bits tighten sigma_u/C_u by about 2x,
    not by the 4x the LSB shrinks."""
    ratio = sigma_dnl_msb_analytic(HIGH_BITS, 1.0) / sigma_dnl_msb_analytic(LOW_BITS, 1.0)
    predicted = np.sqrt((2**HIGH_BITS - 1) / (2**LOW_BITS - 1))
    assert np.isclose(ratio, predicted, atol=RATIO_TOLERANCE)


def test_fast_curve_matches_the_conversion_loop():
    """The matmul in transition_voltages and the sum in dac_voltage are two
    implementations of one equation. The fast one is only allowed to exist
    because it is checked against the slow one on a mismatched array."""
    rng = np.random.default_rng(CURVE_SEED)
    u = ideal_units(N_BITS) * (1 + rng.normal(0, SIGMA, 2**N_BITS))
    weights = branch_weights(u)
    total_cap = u.sum()

    fast = transition_voltages(u)
    slow = np.array([dac_voltage(c, weights, total_cap, VREF) for c in range(2**N_BITS)])
    assert np.allclose(fast, slow, rtol=0, atol=FLOAT_EXACT)
