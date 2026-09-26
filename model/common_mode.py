"""The common mode's source, and what its movement costs a conversion.

The top plate is sampled to Vcm and later compared against Vcm, so Vcm cancels
out of every decision -- provided it is the same Vcm both times. What a
threshold sees is the difference between the value sampled and the value
compared against. Accuracy costs nothing; movement within a conversion costs
exactly itself.

Vcm moves because sampling draws charge from it: every bottom plate that
changes voltage while the top plate is held pushes charge through the top
switch into the Vcm node. Whatever drives that node then has to put it back,
and any part of the recovery still under way once sampling ends happens during
the conversion, where it is a threshold shift.
"""

from __future__ import annotations

import math


def threshold_shift(vcm_sampled: float, vcm_compared: float) -> float:
    """Input-referred shift of every threshold, in volts.

    Sampling traps C_total * (vcm_sampled - Vin); comparing against
    vcm_compared then asks whether Vin exceeds the DAC voltage plus the
    difference.
    """
    return vcm_sampled - vcm_compared


def divider(r_total: float, vref: float, fraction: float) -> tuple[float, float]:
    """A resistor string from VREF to ground, tapped at `fraction`.

    Returns the Thevenin resistance the tap presents -- the two halves in
    parallel -- and the static current the string draws from the reference.
    A stiffer tap costs current in inverse proportion: that is the whole
    trade.
    """
    r_th = r_total * fraction * (1 - fraction)
    return r_th, vref / r_total


def drift_within_conversion(
    step: float,
    c_total: float,
    c_dec: float,
    r_th: float,
    t_sample: float,
    t_conversion: float,
) -> float:
    """Worst threshold shift a Vcm source leaves, in volts.

    A bottom-plate `step` while sampling kicks the Vcm node by the array's
    share of the node's capacitance: the jump. The node recovers through
    `r_th` with everything on it; what is left when sampling ends is what the
    array samples, and the part of that which recovers during the conversion
    is the shift.

    With no decoupling capacitor the jump is the whole step and the recovery
    fast, so nearly all of what sampling left drifts away. A large one makes
    the jump small and the recovery slow: the node ends sampling unsettled but
    hardly moves in one conversion.
    """
    c_node = c_total + c_dec
    jump = step * c_total / c_node
    tau = r_th * c_node
    left = jump * math.exp(-t_sample / tau)
    return left * (1 - math.exp(-t_conversion / tau))


def loaded_reference(vref: float, r_total: float, r_pin: float) -> float:
    """The reference the array sees when a divider hangs on its pin.

    The string's static current crosses the pin's resistance, so inside the
    chip the reference sits below its source by that drop. Every DAC voltage
    scales with it: a gain error, set by the string's current and the pin, and
    present whether or not anything is converting.
    """
    return vref * r_total / (r_total + r_pin)
