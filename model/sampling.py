"""What a moving input costs, as against a held one.

Every other model here converts one voltage at a time, which assumes the input
stood still long enough for the array to reach it. A real input does not, and
the error that leaves depends on the *previous* sample as well as this one:
sampling pushes charge proportional to the input's change between conversions
into the common-mode node, and whatever is still recovering when sampling ends
recovers during the conversion, where it is a threshold shift.

That mechanism is a first difference of the input, and a first difference is a
filter. So the memory by itself costs gain and phase against frequency and
produces no harmonics at all -- a result worth having explicitly, because
"memory effect" sounds like distortion and budgeting it as distortion would be
budgeting for the wrong thing.

Distortion needs the coefficient to depend on the signal, which it does as
soon as anything in the recovery path does: a switch resistance that varies
with the voltage across it, a decoupling capacitance that varies with bias.
Then the error is a product of the step and a function of the level, and the
harmonics appear. `sweep` is the measurement that separates the two, and
`step_coefficient` is where a circuit measurement enters.

Contract: a record is a sequence of inputs sampled at a uniform rate, oldest
first, and it wraps -- the sample before the first is the last, which is what
makes a coherently sampled record one period of a periodic steady state rather
than a transient with an edge at each end.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

from common_mode import drift_within_conversion
from dynamic import codes_from_curve
from sar import ideal_units
from spectrum import (
    AMPLITUDE_FRACTION,
    RECORD,
    coherent_sine,
    enob,
    sfdr_db,
    sndr_db,
    snr_db,
    thd_db,
)


def step_coefficient(
    c_total: float,
    c_dec: float,
    r_th: float,
    t_sample: float,
    t_conversion: float,
) -> float:
    """Threshold shift per volt of change between consecutive inputs.

    The settling law applied to a unit step, so the one law covers both the
    single-conversion question and this one. A coefficient of zero is a source
    that has fully recovered before the conversion starts; a coefficient of one
    is one that has not begun to.
    """
    return drift_within_conversion(1.0, c_total, c_dec, r_th, t_sample, t_conversion)


def sampled(record, coefficient: float | Callable[[float], float]) -> np.ndarray:
    """The voltages a conversion actually sees, given the record offered to it.

    `coefficient` is the shift per volt of inter-sample change. A number makes
    the error a first difference of the input and therefore a filter; a
    callable of the input level makes it a product of the step and that level,
    which is what produces harmonics.
    """
    values = np.asarray(record, dtype=float)
    previous = np.roll(values, 1)
    step = values - previous
    gain = coefficient(values) if callable(coefficient) else np.full_like(values, coefficient)
    return values + gain * step


def level_dependent(nominal: float, slope: float, vref: float = 1.0) -> Callable:
    """A step coefficient that varies linearly across the input range.

    The simplest departure from a constant that still has a cause: a recovery
    path whose resistance rises with the voltage across it recovers less by the
    end of sampling, and does so progressively. `slope` is the fractional
    change over the whole range, so zero reproduces the constant case through
    the same code path.
    """

    def coefficient(v):
        return nominal * (1.0 + slope * (np.asarray(v, dtype=float) / vref - 0.5))

    return coefficient


def coherent_cycles(fraction: float, n_samples: int = RECORD) -> int:
    """An odd cycle count nearest `fraction` of the way to Nyquist.

    Odd, so that it shares no factor with a power-of-two record: that is what
    keeps every tone in a sweep coherent, and a tone that is not coherent
    reports leakage as distortion.
    """
    if not 0.0 < fraction < 1.0:
        raise ValueError(f"{fraction} is not a fraction of the Nyquist frequency")
    wanted = fraction * n_samples / 2
    cycles = int(round(wanted)) | 1
    if math.gcd(cycles, n_samples) != 1:
        raise ValueError(f"{cycles} cycles in {n_samples} samples is not coherent")
    return cycles


def measure(codes, cycles: int, amplitude_frac: float = AMPLITUDE_FRACTION) -> dict[str, float]:
    """Every figure the spectrum offers, for one record."""
    sndr = sndr_db(codes, cycles)
    return {
        "cycles": cycles,
        "sndr": sndr,
        "snr": snr_db(codes, cycles),
        "thd": thd_db(codes, cycles),
        "sfdr": sfdr_db(codes, cycles),
        "enob": enob(sndr, amplitude_frac),
    }


def sweep(
    fractions,
    coefficient: float | Callable[[float], float],
    unit_caps=None,
    n_bits: int = 10,
    vref: float = 1.0,
    n_samples: int = RECORD,
    amplitude_frac: float = AMPLITUDE_FRACTION,
) -> list[dict[str, float]]:
    """Measure the converter against input frequency.

    The array is ideal unless one is given: an array with mismatch has its own
    distortion, and a point that moved both would not say which one moved the
    result.
    """
    units = ideal_units(n_bits) if unit_caps is None else unit_caps
    rows = []
    for fraction in fractions:
        cycles = coherent_cycles(fraction, n_samples)
        offered = coherent_sine(n_samples, cycles, vref, amplitude_frac)
        held = sampled(offered, coefficient)
        if held.min() < 0.0 or held.max() > vref:
            raise ValueError(
                f"at {fraction:g} of Nyquist the memory raises the record's amplitude "
                f"past the range: it would be measuring the converter's saturation, "
                "not its sampling. Offer a smaller amplitude"
            )
        codes = codes_from_curve(held, units, vref)
        rows.append({"fraction": fraction, **measure(codes, cycles, amplitude_frac)})
    return rows
