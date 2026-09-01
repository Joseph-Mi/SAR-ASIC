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

# The structural metrics must hold at every resolution; only the two tests
# that are about 8-bit magnitudes stay pinned to N_BITS.
RESOLUTIONS = (4, 8, 10)
N_BITS = 8


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_ideal_array_is_perfectly_linear(n_bits):
    u = ideal_units(n_bits)
    assert np.allclose(dnl(u), 0.0, atol=1e-12)
    assert np.allclose(inl(u), 0.0, atol=1e-12)
    assert not has_missing_codes(u)


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_one_lsb_step_is_one_unit(n_bits):
    u = ideal_units(n_bits)
    v = transition_voltages(u)
    assert np.isclose(v[1] - v[0], 1.0 / 2**n_bits)


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_msb_dnl_indexes_the_worst_transition(n_bits):
    """Shrink only the MSB branch and the damage must appear at the MSB step.

    Asserting it is the *worst* step rather than a fixed magnitude is what
    makes this resolution-independent: the size of the error scales with
    2**N, its location does not.
    """
    u = ideal_units(n_bits)
    u[2 ** (n_bits - 1) - 1 :] *= 0.99
    d = dnl(u)
    assert msb_dnl(u) == d[2 ** (n_bits - 1) - 1]
    assert msb_dnl(u) == d.min()


def test_monte_carlo_matches_the_analytic_formula():
    """Simulated spread must match the closed form. One of them is wrong
    otherwise, and the closed form is what sizes the array."""
    u = ideal_units(N_BITS)
    rng = np.random.default_rng(12345)
    sigma = 0.02
    trials = [msb_dnl(u * (1 + rng.normal(0, sigma, u.size))) for _ in range(4000)]
    simulated = np.std(trials)
    predicted = sigma_dnl_msb_analytic(N_BITS, sigma)
    assert np.isclose(simulated, predicted, rtol=0.05)


def test_ten_bits_needs_twice_the_matching_not_eight_times():
    """The LSB-referred requirement scales as sqrt(2**N - 1), and that formula
    is already in LSB -- so 8 -> 10 bits tightens sigma_u/C_u by 2x, not 8x."""
    ratio = sigma_dnl_msb_analytic(10, 1.0) / sigma_dnl_msb_analytic(8, 1.0)
    assert np.isclose(ratio, 2.0, atol=0.01)


def test_fast_curve_matches_the_conversion_loop():
    """The matmul in transition_voltages and the sum in dac_voltage are two
    implementations of one equation. The fast one is only allowed to exist
    because it is checked against the slow one on a mismatched array."""
    rng = np.random.default_rng(7)
    u = ideal_units(N_BITS) * (1 + rng.normal(0, 0.02, 2**N_BITS))
    weights = branch_weights(u)
    total_cap = u.sum()

    fast = transition_voltages(u)
    slow = np.array([dac_voltage(c, weights, total_cap, 1.0) for c in range(2**N_BITS)])
    assert np.allclose(fast, slow, rtol=0, atol=1e-15)
