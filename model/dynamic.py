"""Dynamic performance: what the converter is worth as a signal path.

DNL and INL describe the transfer curve one step at a time. ENOB describes the
whole thing with one number, and it is the number "8-bit" actually claims: an
array whose mismatch costs it a bit is a 7-bit ADC no matter what the FSM does.

Measured the way a bench measures it. Drive a sine, take an FFT, compare the
power in the signal bin against everything else. The only difference from a
bench is that nothing here is noisy unless asked.

Coherent sampling: the input completes a whole number of cycles in the record,
and that cycle count shares no factor with the record length. Then the tone
lands entirely in one bin and no window is needed -- windowing to fix an
incoherent record spreads the signal across bins and buys back the leakage as
uncertainty in the answer.
"""

from __future__ import annotations

import numpy as np

from metrics import transition_voltages
from sar import n_bits_of

# A power-of-two record for a fast transform, and a prime cycle count so the
# two share no factor and the tone closes exactly. Any coprime pair works;
# these only put the tone clear of DC and of Nyquist.
RECORD = 4096
CYCLES = 401

# Ideal SNDR of a full-scale sine into an N-bit quantiser is DB_PER_BIT*N +
# SINE_HEADROOM_DB. Both follow from uniform quantisation error; neither is a
# tuning knob.
DB_PER_BIT = 6.02
SINE_HEADROOM_DB = 1.76


def coherent_sine(n_samples=RECORD, cycles=CYCLES, vref=1.0, amplitude_frac=0.49):
    """A sine that fits the record a whole number of times.

    Centred at mid-scale and kept just inside the rails: a clipped converter
    reports distortion that belongs to the stimulus, not to the array.
    """
    n = np.arange(n_samples)
    return vref * (0.5 + amplitude_frac * np.sin(2 * np.pi * cycles * n / n_samples))


def codes_from_curve(vin, unit_caps, vref: float = 1.0) -> np.ndarray:
    """Convert a whole record at once, by looking the input up in the curve.

    A SAR settles on the largest code whose DAC output does not exceed the
    input, so on a monotonic array the binary search and a lookup agree
    exactly -- and the lookup takes the whole record in one call rather than
    one search per sample. Non-monotonic arrays are refused rather than silently
    mis-converted: the search can land on either side of a reversal, and a
    part with a missing code is scrap before its ENOB is interesting.
    """
    v = transition_voltages(unit_caps, vref)
    if np.any(np.diff(v) <= 0):
        raise ValueError("array is non-monotonic; its ENOB is not well defined")
    top = 2 ** n_bits_of(unit_caps) - 1
    return np.clip(np.searchsorted(v, vin, side="right") - 1, 0, top)


def sndr_db(codes, cycles: int = CYCLES) -> float:
    """Signal-to-noise-and-distortion of a coherently sampled record, in dB.

    Everything that is not the tone and not DC counts against the converter --
    quantisation, mismatch distortion and harmonics alike. That is the point
    of the measurement: it does not care why the energy is in the wrong place.
    """
    spectrum = np.abs(np.fft.rfft(np.asarray(codes, dtype=float))) ** 2
    signal = spectrum[cycles]
    rest = spectrum[1:].sum() - signal
    return float(10.0 * np.log10(signal / rest))


def enob(sndr: float, amplitude_frac: float = 0.49) -> float:
    """Effective bits from SNDR, corrected back to full scale.

    The constants assume a full-scale sine, so a stimulus backed off from the
    rails would otherwise be reported as a worse converter than it is.
    """
    full_scale_penalty = 20.0 * np.log10(2 * amplitude_frac)
    return (sndr - SINE_HEADROOM_DB - full_scale_penalty) / DB_PER_BIT


def enob_of(unit_caps, vref: float = 1.0, amplitude_frac: float = 0.49) -> float:
    """End to end: an array in, effective bits out."""
    vin = coherent_sine(vref=vref, amplitude_frac=amplitude_frac)
    codes = codes_from_curve(vin, unit_caps, vref)
    return enob(sndr_db(codes), amplitude_frac)
