"""Golden model of the SAR conversion algorithm.

Contract: this module defines what "correct" means for the project. The Verilog
FSM is judged against `bit_trace`, and every mismatch study calls `sar_convert`
with perturbed unit capacitors. Change it when the architecture changes, never
to make a failing test pass.

Unit capacitors, not branch capacitors, are the interface. A binary-weighted
array of N bits is built from 2**N nominally identical units: branch k owns
2**k of them and one unit is left over as the terminating dummy, so the total is
2**N units and one LSB is exactly one unit.

Units are assigned to branches by position, LSB branch first:

    branch 0 -> unit[0]          (1 unit)
    branch 1 -> unit[1:3]        (2 units)
    branch k -> unit[2**k-1 : 2**(k+1)-1]
    dummy    -> unit[2**N-1]     (1 unit)

That fixed convention is what makes placement a *permutation of the input array*
rather than a different function: pass `unit_caps[perm]` and `perm` is the
layout. Row-major is `arange`; common-centroid is a different `perm`; a process
gradient is applied to the array before permuting.
"""

from __future__ import annotations

import numpy as np


def branch_slices(n_bits: int) -> list[slice]:
    """Unit indices belonging to each binary branch, LSB branch first."""
    return [slice(2**k - 1, 2 ** (k + 1) - 1) for k in range(n_bits)]


def n_bits_of(unit_caps) -> int:
    """Resolution implied by the array length. Requires a power-of-two length."""
    size = len(unit_caps)
    n = int(round(np.log2(size)))
    if 2**n != size:
        raise ValueError(f"unit_caps length must be a power of two, got {size}")
    return n


def branch_weights(unit_caps) -> np.ndarray:
    """Sum unit capacitors into binary branch capacitances, LSB branch first.

    With ideal units this returns [1, 2, 4, ...] * C_u. Mismatch makes the
    branches non-binary, which is the entire source of DNL.
    """
    caps = np.asarray(unit_caps, dtype=float)
    return np.array([caps[s].sum() for s in branch_slices(n_bits_of(caps))])


def dac_voltage(code: int, weights, total_cap: float, vref: float) -> float:
    """Voltage the capacitive DAC produces for `code`.

    The array is a charge divider: the branches switched to VREF drive the top
    plate through their share of the total capacitance.
    """
    selected = sum(w for k, w in enumerate(weights) if code & (1 << k))
    return vref * selected / total_cap


def sar_convert(
    vin: float,
    unit_caps,
    vref: float = 1.0,
    cmp_offset: float = 0.0,
    cmp_noise_rms: float = 0.0,
    rng: np.random.Generator | None = None,
) -> tuple[int, list[int]]:
    """Run one successive-approximation conversion.

    Args:
        vin: sampled input voltage.
        unit_caps: per-unit capacitances, length 2**N. Only ratios matter.
        vref: reference voltage; full scale.
        cmp_offset: comparator input-referred offset, volts. Constant for the
            whole conversion, so it shifts the transfer curve and does not
            create DNL.
        cmp_noise_rms: comparator noise, volts RMS, redrawn at *every* bit
            trial. A binary-weighted SAR has no redundancy, so a wrong decision
            on bit k is never corrected and costs 2**k LSB.
        rng: numpy Generator, required when cmp_noise_rms > 0 so studies are
            reproducible from a seed.

    Returns:
        (code, bit_trace) where bit_trace holds the N decisions MSB-first.
        cocotb compares the trace, not just the code: an FSM that reaches the
        right answer by the wrong path is still broken.
    """
    caps = np.asarray(unit_caps, dtype=float)
    n_bits = n_bits_of(caps)
    weights = branch_weights(caps)
    total_cap = caps.sum()

    if cmp_noise_rms > 0.0 and rng is None:
        raise ValueError("cmp_noise_rms > 0 requires an rng, for reproducibility")

    code = 0
    bit_trace = []
    for k in range(n_bits - 1, -1, -1):
        trial = code | (1 << k)
        v_cmp = vin + cmp_offset
        if cmp_noise_rms > 0.0:
            v_cmp += rng.normal(0.0, cmp_noise_rms)
        # A real comparator's output at exact equality is undefined, so the
        # model has to pick a side and the FSM has to pick the same one.
        # Resolving ties upward is what puts mid-scale at 2**(N-1) rather
        # than one code below it.
        bit = int(v_cmp >= dac_voltage(trial, weights, total_cap, vref))
        if bit:
            code = trial
        bit_trace.append(bit)

    return code, bit_trace


def ideal_units(n_bits: int, c_unit: float = 1.0) -> np.ndarray:
    """A perfectly matched array. The reference every mismatch study perturbs."""
    return np.full(2**n_bits, c_unit, dtype=float)
