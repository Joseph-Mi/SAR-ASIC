"""Static linearity metrics for a binary-weighted charge-redistribution DAC.

These are computed from the branch weights directly, not by sweeping vin through
`sar_convert`. The transition from code k-1 to k happens exactly where the DAC
output for code k sits, so the whole transfer curve is one dot product per code
rather than one conversion per code. That is what keeps a Monte Carlo sweep
something you rerun while thinking rather than something you start and leave.

`sar_convert` is still the authority on what the converter *does*; this module
describes what its DAC *is*. Two implementations of one curve is exactly the
shape that drifts apart, so the tests hold them against each other.
"""

from __future__ import annotations

import numpy as np

from sar import branch_weights, n_bits_of


def transition_voltages(unit_caps, vref: float = 1.0) -> np.ndarray:
    """DAC output for every code, in volts. Trailing axis is the 2**N codes.

    Accepts one array or a stack of them. A stack costs one matmul rather than
    one per trial, which is what keeps a Monte Carlo sweep interactive.
    """
    caps = np.asarray(unit_caps, dtype=float)
    n_bits = n_bits_of(caps)
    weights = branch_weights(caps)
    codes = np.arange(2**n_bits)
    bits = ((codes[:, None] >> np.arange(n_bits)) & 1).astype(float)
    return vref * (weights @ bits.T) / caps.sum(axis=-1, keepdims=True)


def lsb_ideal(n_bits: int, vref: float = 1.0) -> float:
    return vref / 2**n_bits


def dnl(unit_caps, vref: float = 1.0) -> np.ndarray:
    """Differential non-linearity per code step, in LSB. Length 2**N - 1.

    dnl[k] is the step from code k to code k+1. Index 2**(N-1) - 1 is the
    MSB transition, where no unit capacitor is shared between the two codes
    and mismatch is therefore maximally exposed.
    """
    caps = np.asarray(unit_caps, dtype=float)
    v = transition_voltages(caps, vref)
    return np.diff(v, axis=-1) / lsb_ideal(n_bits_of(caps), vref) - 1.0


def inl(unit_caps, vref: float = 1.0) -> np.ndarray:
    """Integral non-linearity per code, in LSB, endpoint-referred."""
    caps = np.asarray(unit_caps, dtype=float)
    v = transition_voltages(caps, vref)
    codes = np.arange(v.shape[-1])
    # Endpoint fit: force zero error at the first and last code.
    first, last = v[..., :1], v[..., -1:]
    line = first + (last - first) * codes / (v.shape[-1] - 1)
    return (v - line) / lsb_ideal(n_bits_of(caps), vref)


def has_missing_codes(unit_caps, vref: float = 1.0) -> np.ndarray:
    """Whether any step is non-positive -- a code that can never be produced.

    DNL <= -1 is the definition, and it is the yield criterion: an array
    with a missing code is a part that fails, however good its other codes are.

    Follows the trailing-axis convention, so a stack answers per array. Test
    the result elementwise rather than with `if`: a stacked answer is an array
    and has no single truth value.
    """
    return np.any(dnl(unit_caps, vref) <= -1.0, axis=-1)


def msb_dnl(unit_caps, vref: float = 1.0) -> np.ndarray:
    """DNL at the MSB transition, in LSB. The number the analytic formula predicts.

    Follows the trailing-axis convention: one value per array, so a stack gives
    the sample the mismatch study takes a standard deviation over.
    """
    caps = np.asarray(unit_caps, dtype=float)
    return dnl(caps, vref)[..., 2 ** (n_bits_of(caps) - 1) - 1]


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
