"""What a conversion costs: charge off the reference, and the figures that uses.

The reference pin is where this architecture spends. Every bit trial moves
bottom plates between the reference and ground, and the charge for that comes
through a pin with real series resistance -- so the same number bounds three
different things: the energy a conversion costs, the average current the pin
has to carry, and the sag that current leaves on the reference while the
comparator is deciding.

The charge is code-dependent, which is the part a single number hides.
Conventional binary switching undoes its own first guess whenever the first
decision goes the other way, and that undoing is the most expensive thing the
array does, so what a conversion costs depends on the input.

Contract: capacitances are farads, voltages volts, and the result is charge in
coulombs or energy in joules. The array's dummy unit terminates to ground and
is never switched, so it holds charge but draws none from the reference.
Energy supplied by an ideal source at `vref` pushing charge Q through itself
is vref*Q; what the array then dissipates in the switches is that minus what
the capacitors store, which this does not separate -- the pin carries the
whole of it either way.
"""

from __future__ import annotations

import numpy as np

from protocol import trial_words
from sar import VCM_FRACTION, branch_weights, top_plate_voltage

#: Bits of resolution each decibel of SNDR is worth, and the headroom a
#: full-scale sine carries. A figure of merit is quoted against effective
#: bits, so the conversion from a measured SNDR has to be the same one the
#: spectrum uses.
DB_PER_BIT = 6.02
SINE_HEADROOM_DB = 1.76


def _bottom_voltages(code: int | None, n_bits: int, vin: float, vref: float) -> np.ndarray:
    """Where each branch's bottom plate sits. `None` is the sampling phase,
    where every bottom plate is held at the input instead."""
    if code is None:
        return np.full(n_bits, vin, dtype=float)
    return np.array([vref if code & (1 << k) else 0.0 for k in range(n_bits)], dtype=float)


def reference_charge(
    vin: float,
    unit_caps,
    vref: float = 1.0,
    vcm: float | None = None,
) -> float:
    """Charge the reference supplies over one whole conversion, coulombs.

    Walked transition by transition, because the charge a branch takes depends
    on where the top plate is -- and the top plate moves with every trial. A
    branch that ends a transition connected to the reference draws all of its
    plate's charge change through that switch, whatever it was connected to
    before: the old connection opens first.
    """
    caps = np.asarray(unit_caps, dtype=float)
    weights = branch_weights(caps)
    n_bits = len(weights)
    reference = VCM_FRACTION * vref if vcm is None else vcm

    states = [None, *trial_words(vin, caps, vref)]

    total = 0.0
    for previous, current in zip(states[:-1], states[1:], strict=True):
        v_old = (
            reference
            if previous is None
            else top_plate_voltage(vin, previous, caps, vref, vcm=reference)
        )
        v_new = top_plate_voltage(vin, current, caps, vref, vcm=reference)
        bottoms_old = _bottom_voltages(previous, n_bits, vin, vref)
        for k in range(n_bits):
            if current & (1 << k):
                total += weights[k] * ((vref - v_new) - (bottoms_old[k] - v_old))
    return float(total)


def reference_energy(
    vin: float,
    unit_caps,
    vref: float = 1.0,
    vcm: float | None = None,
) -> float:
    """Energy one conversion takes out of the reference source, joules."""
    return vref * reference_charge(vin, unit_caps, vref, vcm)


def average_reference_current(charge: float, sample_rate: float) -> float:
    """Mean current the reference pin carries, amps.

    Mean, not peak. The peak is set by the pin's own resistance and the step
    across it, and arrives entirely in the first trial; this is the figure a
    supply and a decoupling capacitor are sized against.
    """
    return charge * sample_rate


def rate_a_pin_can_carry(charge: float, i_pin: float) -> float:
    """Conversions per second the pin's current limit allows.

    A pin bound rather than a settling bound. Whichever of the two is lower is
    the converter's rate, and finding out which only needs the charge above and
    the platform's own limit.
    """
    if charge <= 0.0:
        raise ValueError("a conversion that draws no charge has no rate limit")
    return i_pin / charge


def walden_fom(power: float, enob: float, sample_rate: float) -> float:
    """Energy per conversion step, joules. The lower, the better.

    The figure converters are compared by, and the reason power belongs in a
    characterisation rather than beside it: a part is not better for being
    quiet if it spent twice the energy getting there.
    """
    return power / (2**enob * sample_rate)


def schreier_fom(sndr_db: float, bandwidth: float, power: float) -> float:
    """Dynamic range per watt, in dB. The higher, the better.

    The other convention. It rewards resolution more steeply than Walden's
    does, which is why a part is quoted under both.
    """
    return sndr_db + 10.0 * np.log10(bandwidth / power)


def enob_from_sndr(sndr: float) -> float:
    """Effective bits of a full-scale sine at this SNDR."""
    return (sndr - SINE_HEADROOM_DB) / DB_PER_BIT
