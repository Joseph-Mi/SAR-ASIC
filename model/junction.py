"""Voltage-dependent parasitic capacitance on the top plate, and what it costs.

A switch drain sitting on the top plate is a reverse-biased pn junction, so the
parasitic it adds is not a fixed capacitance: it falls as the node moves away
from its body. The linear case is settled -- a parasitic to a fixed potential
moves no threshold, because the node is back at the sampling reference whenever
a decision is taken, and the parasitic therefore holds the charge it started
with. A nonlinear parasitic is the case that argument looks like it should
fail for, since a capacitance that changes with voltage is exactly what turns
a harmless divider into distortion elsewhere in a signal path.

It does not fail here, and `input_at_decision` is why: the cancellation is of
stored charge at one node voltage, and a nonlinear capacitance stores a
definite charge at a definite voltage like any other. The argument never used
linearity. What survives is that the comparator's decision point, not the
input, is what has to be the same every time -- and in this architecture it is,
because the comparator always decides against the same reference.

So the cost of a nonlinear top-plate parasitic is not gain error and not INL.
It is the three things this module puts numbers on:

  swing        the comparator resolves a divided-down swing, and the divider
               is now input-dependent, so the worst case is what budgets it
  settling     the node charges through a capacitance that varies over the
               conversion, so one trial's time constant is not another's
  leakage      a reverse-biased junction passes current, and the node it sits
               on is floating while the sample is held

Contract: capacitances share the units of `unit_caps`, voltages are volts, and
a junction voltage is reverse bias -- positive when reverse biased, which is
the only regime a depletion law describes. Forward bias is refused rather than
extrapolated: there the junction conducts, and what matters about it is charge
leaving the node, not capacitance.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sar import VCM_FRACTION, branch_weights, n_bits_of

#: Grading exponent of an abrupt junction and of a linearly graded one. A real
#: diffusion sits between the two, so a design held at both ends is held
#: whatever the process draws.
ABRUPT = 0.5
LINEARLY_GRADED = 1.0 / 3.0

#: Built-in potential of a silicon pn junction near room temperature, volts.
PHI_B = 0.75


@dataclass(frozen=True)
class Junction:
    """A reverse-biased junction, as a capacitance and as a stored charge.

    `c_zero` is the capacitance at zero bias, in the units the array uses.
    Charge is measured from zero bias, which is the only constant the
    cancellation needs: every expression here uses charge *differences*.
    """

    c_zero: float
    phi_b: float = PHI_B
    grading: float = ABRUPT

    def __post_init__(self) -> None:
        if self.c_zero < 0.0:
            raise ValueError(f"a junction cannot have capacitance {self.c_zero}")
        if self.phi_b <= 0.0:
            raise ValueError(f"{self.phi_b} is not a built-in potential")
        if not 0.0 < self.grading < 1.0:
            raise ValueError(f"{self.grading} is not a depletion grading exponent")

    def _depletion(self, reverse_bias):
        bias = np.asarray(reverse_bias, dtype=float)
        # A junction with no capacitance is the absence of one: it stores
        # nothing at any bias, so there is no law for a bias to fall outside.
        if self.c_zero == 0.0:
            return np.ones_like(bias)
        if np.any(bias < 0.0):
            raise ValueError(
                "forward bias is outside the depletion law: there the junction "
                "conducts, and the node loses charge rather than storing it"
            )
        return 1.0 + bias / self.phi_b

    def capacitance(self, reverse_bias):
        """Small-signal capacitance at a given reverse bias."""
        return self.c_zero * self._depletion(reverse_bias) ** -self.grading

    def charge(self, reverse_bias):
        """Charge stored between zero bias and `reverse_bias`.

        The integral of the depletion law. Charge, not capacitance, is what a
        floating node conserves, so this is the quantity every result here is
        built from.
        """
        scaled = self._depletion(reverse_bias)
        exponent = 1.0 - self.grading
        return self.c_zero * self.phi_b / exponent * (scaled**exponent - 1.0)


#: A junction that is not there. Lets one code path serve both cases, so the
#: linear result and the nonlinear one are never computed by different code.
ABSENT = Junction(c_zero=0.0)


def _common_mode(vref: float, vcm: float | None) -> float:
    return VCM_FRACTION * vref if vcm is None else vcm


def _selected(code: int, unit_caps) -> float:
    weights = branch_weights(np.asarray(unit_caps, dtype=float))
    return float(sum(w for k, w in enumerate(weights) if code & (1 << k)))


def top_plate_voltage(
    vin: float,
    code: int,
    unit_caps,
    junction: Junction = ABSENT,
    vref: float = 1.0,
    vcm: float | None = None,
    v_body: float = 0.0,
) -> float:
    """Top-plate voltage with a voltage-dependent parasitic on the node.

    Charge conservation, as in the linear case, but the parasitic's charge no
    longer collapses to a capacitance times a voltage, so the balance is solved
    rather than rearranged. `v_body` is the potential the junction's other side
    is held at; the bias across it is the node above that.

    The balance is strictly increasing in the node voltage -- total array
    capacitance is positive and stored charge rises with bias -- so the root is
    unique and bisection finds it without a starting guess.
    """
    caps = np.asarray(unit_caps, dtype=float)
    total = float(caps.sum())
    reference = _common_mode(vref, vcm)
    selected = _selected(code, caps)

    held = total * (reference - vin) + junction.charge(reference - v_body)

    def imbalance(v: float) -> float:
        return total * v - vref * selected + junction.charge(v - v_body) - held

    floor = None if junction.c_zero == 0.0 else v_body
    if floor is not None and imbalance(floor) >= 0.0:
        raise ValueError(
            "the charge balance puts the top plate below the junction's body, "
            "where it conducts and the held charge drains -- the state the "
            "sampling contract exists to keep the node out of"
        )
    return _root(imbalance, floor)


#: Volts the bracket grows by until it spans the root, and how far bisection
#: narrows it. The tolerance is far below any capacitance ratio the array can
#: resolve, so the solve never limits an answer this module reports.
BRACKET_STEP = 1.0
BRACKET_LIMIT = 1 << 20
ROOT_TOLERANCE = 1e-15


def _root(imbalance, floor: float | None) -> float:
    """Bisect a strictly increasing function.

    `floor` is the lowest voltage the balance is defined at, or None when it is
    defined everywhere. Bracketing outward by doubling needs no starting guess,
    which matters because the node's range depends on the array.
    """
    if floor is None:
        low = -BRACKET_STEP
        while imbalance(low) >= 0.0:
            low *= 2.0
            if -low > BRACKET_LIMIT:
                raise ValueError("the charge balance has no root in any sane range")
    else:
        low = floor
    high = low + BRACKET_STEP
    while imbalance(high) < 0.0:
        high += high - low
        if high - low > BRACKET_LIMIT:
            raise ValueError("the charge balance has no root in any sane range")
    while high - low > ROOT_TOLERANCE:
        middle = 0.5 * (low + high)
        if imbalance(middle) < 0.0:
            low = middle
        else:
            high = middle
    return 0.5 * (low + high)


def input_at_decision(
    code: int,
    unit_caps,
    junction: Junction = ABSENT,
    vref: float = 1.0,
    vcm: float | None = None,
    v_body: float = 0.0,
    node_offset: float = 0.0,
) -> float:
    """The input voltage at which the trial `code` decides: the threshold.

    Closed form, because the node voltage is known -- a decision happens when
    the top plate reaches the comparator's own switching point, and that is the
    sampling reference offset by the comparator's input-referred offset,
    whatever the input was. Putting that voltage into charge conservation and
    solving for the input leaves

        vin = vref * C_selected / C_total - node_offset
              - (Q(vcm + node_offset - v_body) - Q(vcm - v_body)) / C_total

    The first term is the ideal threshold. The parasitic appears only in the
    last, as a difference of its stored charge between two *fixed* voltages --
    so it is one number for every threshold in the converter, which is an
    offset and cannot be a nonlinearity. At zero comparator offset the two
    voltages coincide and the term is identically zero: the parasitic does not
    appear at all, however nonlinear it is.
    """
    caps = np.asarray(unit_caps, dtype=float)
    total = float(caps.sum())
    reference = _common_mode(vref, vcm)
    decision = reference + node_offset
    spilled = junction.charge(decision - v_body) - junction.charge(reference - v_body)
    return vref * _selected(code, caps) / total - node_offset - spilled / total


def swing_gain(
    v_top: float,
    total_cap: float,
    junction: Junction = ABSENT,
    v_body: float = 0.0,
) -> float:
    """Fraction of the ideal swing the comparator is left to resolve.

    The parasitic divides the node's excursion down, which multiplies every
    input-referred comparator figure -- offset, noise, hysteresis -- by the
    inverse of this. With a voltage-dependent parasitic the divider is a
    function of where the node sits, so a comparator budget is held to the
    worst value over the conversion, not to a single ratio.
    """
    return total_cap / (total_cap + junction.capacitance(v_top - v_body))


def tau_multiplier(
    v_top: float,
    total_cap: float,
    junction: Junction = ABSENT,
    v_body: float = 0.0,
) -> float:
    """What the parasitic does to a settling time constant at this node voltage.

    Every path into the top plate charges the parasitic as well as the array,
    so each time constant grows by this factor. It varies over a conversion,
    which is the one way a nonlinear parasitic reaches the codes: a settling
    allowance sized for one trial is not the allowance the next one needs.
    """
    return 1.0 + junction.capacitance(v_top - v_body) / total_cap


def leakage_droop_lsb(
    leakage_current: float,
    hold_time: float,
    total_cap_farads: float,
    n_bits: int,
    vref: float = 1.0,
) -> float:
    """Charge lost from the floating node during a hold, in LSB.

    The junction that adds the parasitic also passes a reverse current, and the
    node it sits on is floating from the end of sampling to the last decision.
    Unlike the capacitance, this does not cancel: it is charge that left.
    """
    lsb = vref / 2**n_bits
    return leakage_current * hold_time / (total_cap_farads * lsb)


def decisions(
    vin: float,
    unit_caps,
    junction: Junction = ABSENT,
    vref: float = 1.0,
    vcm: float | None = None,
    v_body: float = 0.0,
    node_offset: float = 0.0,
) -> tuple[int, list[int]]:
    """Run the search against node voltages this module computes.

    The comparator's question is asked where it is really asked -- of the top
    plate against its reference -- rather than of the input against a divider
    output. Both forms are the same inequality when nothing is on the node;
    this one stays available when something nonlinear is.
    """
    caps = np.asarray(unit_caps, dtype=float)
    n_bits = n_bits_of(caps)
    reference = _common_mode(vref, vcm) + node_offset

    code = 0
    trace = []
    for k in range(n_bits - 1, -1, -1):
        trial = code | (1 << k)
        v_top = top_plate_voltage(vin, trial, caps, junction, vref=vref, vcm=vcm, v_body=v_body)
        bit = int(v_top <= reference)
        if bit:
            code = trial
        trace.append(bit)
    return code, trace
