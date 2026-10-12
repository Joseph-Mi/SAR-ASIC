"""Dynamic performance of an array: what it is worth as a signal path.

DNL and INL describe the transfer curve one step at a time. ENOB describes the
whole thing with one number, and it is the number a resolution actually
claims: an array whose mismatch costs it a bit converts a bit worse no matter
what the FSM does.

Measured the way a bench measures it -- drive a sine, transform the record,
read the tone against the rest. The only difference from a bench is that
nothing here is noisy unless asked.

Contract: this reads the array's static transfer curve and nothing else. Every
error it can report is one the curve already contains, which is mismatch. An
error that depends on when a sample was taken rather than on where it landed
is invisible here by construction.
"""

from __future__ import annotations

import numpy as np

from metrics import transition_voltages
from sar import n_bits_of
from spectrum import AMPLITUDE_FRACTION, coherent_sine, enob, sndr_db


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


def enob_of(unit_caps, vref: float = 1.0, amplitude_frac: float = AMPLITUDE_FRACTION) -> float:
    """End to end: an array in, effective bits out."""
    vin = coherent_sine(vref=vref, amplitude_frac=amplitude_frac)
    codes = codes_from_curve(vin, unit_caps, vref)
    return enob(sndr_db(codes), amplitude_frac)
