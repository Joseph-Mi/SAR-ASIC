"""What a record of codes contains: the tone, its harmonics, and the rest.

SNDR says how much of the output is not the signal. It does not say whether
what is left is spread thinly over every bin or concentrated in one, and those
have different causes and different cures: broadband energy is noise and
quantisation, a single tall bin at a multiple of the input is distortion, and a
tall bin that is not a multiple is something coupling in. A converter reported
only by SNDR hides which of the three it has.

So every figure here is the same record read a different way, and the set of
them is what a bench reports:

  SNDR   the tone against everything else
  SNR    the tone against everything that is not a harmonic of it
  THD    the harmonics against the tone
  SFDR   the tone against the single worst bin, whatever it is

Contract: records are coherently sampled -- the input completes `cycles` whole
periods in the record, and `cycles` shares no factor with the record length, so
the tone lands entirely in one bin and no window is needed. Windowing to repair
an incoherent record spreads the tone over neighbouring bins and buys the
leakage back as uncertainty in every figure above.
"""

from __future__ import annotations

import numpy as np

#: A power-of-two record for a fast transform, and a prime cycle count so the
#: two share no factor and the tone closes exactly. Any coprime pair works;
#: these put the tone clear of DC and of Nyquist, and keep the harmonics the
#: figures below separate from both.
RECORD = 4096
CYCLES = 401

#: Highest harmonic a distortion figure accounts for. Above this the terms are
#: below the floor of any record a converter of this resolution produces, so
#: including them adds the floor rather than the distortion.
HARMONIC_ORDER = 5

#: Ideal SNDR of a full-scale sine into an N-bit quantiser is DB_PER_BIT*N +
#: SINE_HEADROOM_DB. Both follow from uniform quantisation error; neither is a
#: tuning knob.
DB_PER_BIT = 6.02
SINE_HEADROOM_DB = 1.76

#: Decibels per decade of power, and of amplitude.
DB_POWER = 10.0
DB_AMPLITUDE = 20.0

#: The test sine's amplitude as a fraction of the reference: just under half,
#: so its peaks stay inside the range and never clip.
AMPLITUDE_FRACTION = 0.49

#: Returned where a figure's denominator is empty -- a record with nothing but
#: the tone in it. Infinite is the true answer and propagates as one.
PERFECT_DB = float("inf")


def coherent_sine(
    n_samples: int = RECORD,
    cycles: int = CYCLES,
    vref: float = 1.0,
    amplitude_frac: float = AMPLITUDE_FRACTION,
    phase: float = 0.0,
) -> np.ndarray:
    """A sine that fits the record a whole number of times.

    Centred at mid-scale and kept just inside the rails: a clipped converter
    reports distortion that belongs to the stimulus, not to the array.
    """
    n = np.arange(n_samples)
    angle = 2 * np.pi * cycles * n / n_samples + phase
    return vref * (0.5 + amplitude_frac * np.sin(angle))


def power_spectrum(record) -> np.ndarray:
    """Power per bin of a real record, DC first."""
    return np.abs(np.fft.rfft(np.asarray(record, dtype=float))) ** 2


def harmonic_bins(cycles: int = CYCLES, n_samples: int = RECORD, order: int = HARMONIC_ORDER):
    """Which bin each harmonic of the tone lands in, by order.

    A harmonic above Nyquist aliases back into the band and folds about it, so
    its bin is not its order times the tone's. A harmonic that folds onto DC or
    onto the tone cannot be told from them, which makes every distortion figure
    meaningless rather than merely wrong -- so the cycle count is refused
    rather than silently reported against.
    """
    tone = cycles % n_samples
    bins = {}
    for h in range(2, order + 1):
        landed = (h * cycles) % n_samples
        if landed > n_samples // 2:
            landed = n_samples - landed
        if landed in (0, tone):
            raise ValueError(
                f"harmonic {h} of {cycles} cycles in {n_samples} samples folds onto "
                "the tone or onto DC, where it cannot be measured separately"
            )
        bins[h] = landed
    return bins


def _ratio_db(numerator: float, denominator: float) -> float:
    if denominator <= 0.0:
        return PERFECT_DB
    return float(DB_POWER * np.log10(numerator / denominator))


def sndr_db(record, cycles: int = CYCLES) -> float:
    """The tone against everything else in the record, in dB.

    Quantisation, mismatch distortion and harmonics alike count against the
    converter. That is the point of the measurement: it does not care why the
    energy is in the wrong place. DC is excluded -- the stimulus is centred at
    mid-scale, so bin zero carries the offset, not the signal.
    """
    spectrum = power_spectrum(record)
    signal = spectrum[cycles]
    return _ratio_db(signal, spectrum[1:].sum() - signal)


def harmonic_power(record, cycles: int = CYCLES, order: int = HARMONIC_ORDER) -> dict[int, float]:
    """Power in each harmonic bin, by order."""
    spectrum = power_spectrum(record)
    bins = harmonic_bins(cycles, 2 * (len(spectrum) - 1), order)
    return {h: float(spectrum[b]) for h, b in bins.items()}


def thd_db(record, cycles: int = CYCLES, order: int = HARMONIC_ORDER) -> float:
    """Total harmonic distortion, as dB below the tone.

    Negative, and more negative is better. Reported against the tone rather
    than as a percentage because that is the unit every other figure here uses.
    """
    spectrum = power_spectrum(record)
    harmonics = sum(harmonic_power(record, cycles, order).values())
    return -_ratio_db(spectrum[cycles], harmonics)


def snr_db(record, cycles: int = CYCLES, order: int = HARMONIC_ORDER) -> float:
    """The tone against everything that is not a harmonic of it.

    SNDR minus the distortion. Where this is close to SNDR the converter is
    noise limited and a quieter comparator buys resolution; where it is far
    above, the limit is distortion and a quieter comparator buys nothing.
    """
    spectrum = power_spectrum(record)
    signal = spectrum[cycles]
    harmonics = sum(harmonic_power(record, cycles, order).values())
    return _ratio_db(signal, spectrum[1:].sum() - signal - harmonics)


def worst_spur(record, cycles: int = CYCLES) -> tuple[int, float]:
    """The single largest bin that is neither DC nor the tone, and its power.

    Whatever it is. A spur that is not a harmonic is not distortion of the
    signal path, and finding it in the bin list rather than in the SNDR figure
    is what points at the coupling that made it.
    """
    spectrum = power_spectrum(record).copy()
    spectrum[0] = 0.0
    spectrum[cycles] = 0.0
    index = int(np.argmax(spectrum))
    return index, float(spectrum[index])


def sfdr_db(record, cycles: int = CYCLES) -> float:
    """The tone against the worst single bin in the record, in dB."""
    spectrum = power_spectrum(record)
    _, spur = worst_spur(record, cycles)
    return _ratio_db(spectrum[cycles], spur)


def enob(sndr: float, amplitude_frac: float = AMPLITUDE_FRACTION) -> float:
    """Effective bits from SNDR, corrected back to full scale.

    The constants assume a full-scale sine, so a stimulus backed off from the
    rails would otherwise be reported as a worse converter than it is.
    """
    full_scale_penalty = DB_AMPLITUDE * np.log10(2 * amplitude_frac)
    return (sndr - SINE_HEADROOM_DB - full_scale_penalty) / DB_PER_BIT
