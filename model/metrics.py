"""Static linearity metrics for a binary-weighted charge-redistribution DAC.

These are computed from the branch weights directly, not by sweeping vin through
`sar_convert`. The transition from code k-1 to k happens exactly where the DAC
output for code k sits, so the whole transfer curve is 2**N evaluations of a dot
product rather than 2**N conversions. That difference is what makes a 1000-seed
Monte Carlo sweep take seconds instead of hours.

`sar_convert` is still the authority on what the converter *does*; this module
describes what its DAC *is*. Task 4's cross-check compares the two.
"""

from __future__ import annotations

import numpy as np

from sar import branch_weights, n_bits_of


def transition_voltages(unit_caps, vref: float = 1.0) -> np.ndarray:
    """DAC output for every code, in volts. Length 2**N."""
    caps = np.asarray(unit_caps, dtype=float)
    weights = branch_weights(caps)
    codes = np.arange(2 ** n_bits_of(caps))
    bits = ((codes[:, None] >> np.arange(len(weights))) & 1).astype(float)
    return vref * (bits @ weights) / caps.sum()


def lsb_ideal(n_bits: int, vref: float = 1.0) -> float:
    return vref / 2**n_bits


def dnl(unit_caps, vref: float = 1.0) -> np.ndarray:
    """Differential non-linearity per code step, in LSB. Length 2**N - 1.

    dnl[k] is the step from code k to code k+1. Index 2**(N-1) - 1 is the
    MSB transition (127 -> 128 at 8 bits), where no unit capacitor is shared
    between the two codes and mismatch is therefore maximally exposed.
    """
    caps = np.asarray(unit_caps, dtype=float)
    v = transition_voltages(caps, vref)
    return np.diff(v) / lsb_ideal(n_bits_of(caps), vref) - 1.0


def inl(unit_caps, vref: float = 1.0) -> np.ndarray:
    """Integral non-linearity per code, in LSB, endpoint-referred."""
    caps = np.asarray(unit_caps, dtype=float)
    v = transition_voltages(caps, vref)
    codes = np.arange(len(v))
    # Endpoint fit: force zero error at the first and last code.
    line = v[0] + (v[-1] - v[0]) * codes / (len(v) - 1)
    return (v - line) / lsb_ideal(n_bits_of(caps), vref)


def has_missing_codes(unit_caps, vref: float = 1.0) -> bool:
    """True if any step is non-positive -- a code that can never be produced.

    DNL <= -1 is the definition. This is the yield criterion for Task 4.
    """
    return bool(np.any(dnl(unit_caps, vref) <= -1.0))


def msb_dnl(unit_caps, vref: float = 1.0) -> float:
    """DNL at the MSB transition, in LSB. The number the analytic formula predicts."""
    caps = np.asarray(unit_caps, dtype=float)
    return float(dnl(caps, vref)[2 ** (n_bits_of(caps) - 1) - 1])


def sigma_dnl_msb_analytic(n_bits: int, sigma_rel: float) -> float:
    """sqrt(2**N - 1) * sigma_u/C_u, in LSB.

    Derivation: at the MSB transition the 2**(N-1) units of the MSB branch
    switch on while the 2**(N-1) - 1 units of every lower branch switch off.
    The two groups share no devices, so their variances add: the step variance
    is (2**N - 1) * sigma_u**2, and one LSB is one unit.

    Note this is already expressed in LSB -- the LSB shrinking with N is the
    normalisation baked into it, not a second effect to multiply in.
    """
    return float(np.sqrt(2**n_bits - 1) * sigma_rel)
