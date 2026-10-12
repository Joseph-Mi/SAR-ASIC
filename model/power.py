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

from dataclasses import dataclass

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


def switching_energy(capacitance: float, supply: float, nodes: int = 1) -> float:
    """Energy a node of this capacitance costs per cycle of full swing, joules.

    C*V^2, not half of it. Charging a node through a resistance dissipates as
    much as it stores, and discharging it dissipates what was stored, so a
    node taken up and back down once has cost the supply the whole of C*V^2
    whatever the resistance was.
    """
    if capacitance < 0.0 or supply < 0.0 or nodes < 0:
        raise ValueError("a switching node has no negative capacitance, supply or count")
    return nodes * capacitance * supply**2


@dataclass(frozen=True)
class Budget:
    """Energy one conversion costs, by where it goes.

    Three terms, and the honesty is in which of them are known. The reference
    is computed from the array and the search. The other two are arguments,
    because one needs a comparator that does not exist yet and the other needs
    a synthesised netlist -- and a budget that invented them would be a budget
    that always balances.
    """

    reference: float
    comparator: float = 0.0
    digital: float = 0.0

    def __post_init__(self) -> None:
        if min(self.reference, self.comparator, self.digital) < 0.0:
            raise ValueError("a term of an energy budget cannot be negative")

    @property
    def total(self) -> float:
        return self.reference + self.comparator + self.digital

    @property
    def shares(self) -> dict[str, float]:
        """Each term as a fraction of the whole, so the largest is obvious."""
        if self.total == 0.0:
            raise ValueError("a budget of nothing has no shares")
        return {
            name: getattr(self, name) / self.total
            for name in ("reference", "comparator", "digital")
        }

    def power(self, sample_rate: float) -> float:
        """Average power at a conversion rate, watts."""
        if sample_rate < 0.0:
            raise ValueError(f"{sample_rate} conversions per second is not a rate")
        return self.total * sample_rate


def rate_a_supply_can_carry(budget: Budget, supply: float, current_limit: float) -> float:
    """Conversions per second the supply's current allowance permits.

    The third bound on the rate, beside settling and the reference pin's own
    current. A platform states what it will deliver before its network droops;
    exceeding it is not a slow converter but a wrong one, because everything
    on the die shares that droop.
    """
    if supply <= 0.0 or current_limit <= 0.0:
        raise ValueError("a supply bound needs a voltage and a current")
    if budget.total <= 0.0:
        raise ValueError("a conversion that costs nothing has no rate limit")
    return supply * current_limit / budget.total


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
