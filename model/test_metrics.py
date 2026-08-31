"""Metrics are exercised on arrays we construct, so they are independent of the
conversion loop -- a bug in one cannot hide a bug in the other."""

import numpy as np

from metrics import (
    dnl,
    has_missing_codes,
    inl,
    msb_dnl,
    sigma_dnl_msb_analytic,
    transition_voltages,
)
from sar import ideal_units

N_BITS = 8


def test_ideal_array_is_perfectly_linear():
    u = ideal_units(N_BITS)
    assert np.allclose(dnl(u), 0.0, atol=1e-12)
    assert np.allclose(inl(u), 0.0, atol=1e-12)
    assert not has_missing_codes(u)


def test_one_lsb_step_is_one_unit():
    u = ideal_units(N_BITS)
    v = transition_voltages(u)
    assert np.isclose(v[1] - v[0], 1.0 / 2**N_BITS)


def test_msb_dnl_indexes_the_msb_transition():
    """Shrinking only the MSB branch must show up at the 127->128 step."""
    u = ideal_units(N_BITS)
    u[2 ** (N_BITS - 1) - 1 :] *= 0.99  # MSB branch is units[127:255]
    d = dnl(u)
    assert msb_dnl(u) == d[2 ** (N_BITS - 1) - 1]
    assert msb_dnl(u) < -0.5


def test_monte_carlo_matches_the_analytic_formula():
    """Task 4's cross-check. Disagreement means one of them is wrong."""
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
