"""What a conversion costs the reference, and whether that cost binds anything.

The charge bookkeeping is the part most likely to be subtly wrong -- a sign or
a plate counted on the wrong side changes the answer without changing its
order -- so it is checked against the one invariant the circuit cannot
violate: the top plate is floating, and its charge does not change from the
end of sampling to the last decision.
"""

from __future__ import annotations

import numpy as np
import pytest

from metrics import lsb_ideal, midcode_inputs
from power import (
    Budget,
    average_reference_current,
    enob_from_sndr,
    rate_a_pin_can_carry,
    rate_a_supply_can_carry,
    reference_charge,
    reference_energy,
    schreier_fom,
    switching_energy,
    walden_fom,
)
from protocol import trial_words
from sar import VCM_FRACTION, branch_weights, ideal_units, top_plate_voltage
from settling import sampling_loop_resistance, settle_time
from sky130 import mim_unit
from spectrum import DB_PER_BIT, SINE_HEADROOM_DB
from tinytapeout import I_PDN_DROP, I_PIN, R_PIN

VREF = 1.0
BITS = 8
WIDE_BITS = 10

#: The smallest unit the process draws, farads. Every absolute figure here
#: scales with it, so the conclusions are stated as ratios wherever they can
#: be -- and where they cannot, they are stated against the process's own
#: number rather than a round one.
C_UNIT = mim_unit()


#: Phases a conversion takes beyond its bit trials: the sample, and the cycle
#: that hands the result over.
OVERHEAD_PHASES = 2

#: How far above the settling-limited rate the pin's current limit has to sit
#: before the pin is not worth budgeting against.
PIN_HEADROOM = 100.0

#: Settling tolerance a path is held to, in LSB.
TOLERANCE_LSB = 0.5

#: Charge conservation on a floating node, as a fraction of one LSB of charge.
#: Arithmetic noise only -- the invariant is exact.
CONSERVED_LSB = 1e-9

#: Illustrative operating point for the figures of merit. Not design values.
SAMPLE_RATE = 1e6
POWER = 1e-6
BANDWIDTH = SAMPLE_RATE / 2


def test_the_top_plate_keeps_its_charge_through_the_conversion():
    """The invariant the whole bookkeeping rests on. The node is floating from
    the end of sampling, so every voltage the model reports has to leave its
    charge where sampling put it -- including the terminating unit, which is
    sampled with the rest and grounded afterwards."""
    units = ideal_units(BITS, C_UNIT)
    weights = branch_weights(units)
    terminating = float(units.sum() - weights.sum())
    reference = VCM_FRACTION * VREF
    tolerance = CONSERVED_LSB * C_UNIT * VREF
    for vin in midcode_inputs(BITS, 16, VREF):
        held = []
        for state in [None, *trial_words(vin, units, VREF)]:
            v_top = reference if state is None else top_plate_voltage(vin, state, units, VREF)
            bottoms = (
                np.full(len(weights), vin)
                if state is None
                else np.array([VREF if state >> k & 1 else 0.0 for k in range(len(weights))])
            )
            terminating_bottom = vin if state is None else 0.0
            held.append(
                float(
                    (weights * (bottoms - v_top)).sum() + terminating * (terminating_bottom - v_top)
                )
            )
        assert np.ptp(held) < tolerance, vin


def test_a_conversion_draws_charge_of_the_order_the_array_holds():
    """An order check, which is what catches a plate counted on the wrong side:
    the reference cannot supply much more than the array can hold, nor
    meaningfully less."""
    units = ideal_units(BITS, C_UNIT)
    total = float(units.sum())
    for vin in midcode_inputs(BITS, 16, VREF):
        charge = reference_charge(vin, units, VREF)
        assert 0.0 < charge < total * VREF, vin


def test_the_cost_of_a_conversion_falls_as_the_input_rises():
    """Architecture-specific, and the opposite of the textbook mid-code peak.

    A trial that fails is charge taken from the reference and handed to ground,
    and a low code is a conversion whose trials mostly fail. With the input
    sampled onto the bottom plates the first trial costs the same whatever the
    input, so what is left to vary is how many later trials are undone.
    """
    units = ideal_units(BITS, C_UNIT)
    charges = [reference_charge(vin, units, VREF) for vin in midcode_inputs(BITS, 64, VREF)]
    assert np.all(np.diff(charges) <= 0.0)
    assert charges[0] > charges[-1]


def test_the_first_trial_costs_the_same_whatever_the_input():
    """Which is why the worst case is a code and not an input extreme: the
    largest single charge event in a conversion is input-independent, and only
    the trials after it depend on where the input was."""
    units = ideal_units(BITS, C_UNIT)
    weights = branch_weights(units)
    first = 1 << (BITS - 1)
    reference = VCM_FRACTION * VREF
    costs = []
    for vin in midcode_inputs(BITS, 16, VREF):
        v_new = top_plate_voltage(vin, first, units, VREF)
        costs.append(weights[BITS - 1] * ((VREF - v_new) - (vin - reference)))
    assert np.ptp(costs) < CONSERVED_LSB * C_UNIT * VREF


def test_energy_is_the_reference_pushing_that_charge_through_itself():
    units = ideal_units(BITS, C_UNIT)
    for vin in midcode_inputs(BITS, 8, VREF):
        assert reference_energy(vin, units, VREF) == VREF * reference_charge(vin, units, VREF)


def test_a_finer_array_costs_more_charge_for_the_same_reference():
    """Resolution is bought with capacitance, and capacitance is what the
    reference has to charge. The cost per conversion rises with the array, not
    with the number of trials."""
    coarse = reference_charge(0.3, ideal_units(BITS, C_UNIT), VREF)
    fine = reference_charge(0.3, ideal_units(WIDE_BITS, C_UNIT), VREF)
    assert fine > coarse


def test_average_current_is_charge_at_the_conversion_rate():
    units = ideal_units(BITS, C_UNIT)
    charge = reference_charge(0.0, units, VREF)
    assert average_reference_current(charge, SAMPLE_RATE) == charge * SAMPLE_RATE
    assert average_reference_current(charge, 2 * SAMPLE_RATE) == 2 * charge * SAMPLE_RATE


def test_the_pin_current_limit_is_not_what_bounds_the_converter():
    """The result that decides whether power needs designing around. Settling
    through the pin's resistance is slower, by a wide margin, than its current
    limit -- so the reference pin is budgeted for sag during a trial, not for
    average current.

    Every resistance in the sampling loop is taken at the pin's own bound,
    which overstates the on-chip switch and so understates the settling-limited
    rate: the margin found here is the conservative one.
    """
    units = ideal_units(WIDE_BITS, C_UNIT)
    total = float(units.sum())
    worst = max(reference_charge(vin, units, VREF) for vin in midcode_inputs(WIDE_BITS, 16, VREF))

    tau = sampling_loop_resistance(R_PIN, R_PIN, R_PIN) * total
    lsb = VREF / 2**WIDE_BITS
    phase = settle_time(tau, VREF, lsb / 2)
    settling_limited = 1.0 / ((WIDE_BITS + OVERHEAD_PHASES) * phase)

    assert rate_a_pin_can_carry(worst, I_PIN) > PIN_HEADROOM * settling_limited
    assert average_reference_current(worst, settling_limited) < I_PIN / PIN_HEADROOM


def test_a_conversion_that_draws_nothing_has_no_rate_limit_to_report():
    with pytest.raises(ValueError):
        rate_a_pin_can_carry(0.0, I_PIN)


def test_effective_bits_from_a_measured_ratio_matches_the_spectrum():
    """One conversion between decibels and bits, so a figure of merit and a
    spectrum cannot disagree about what a part's resolution was."""
    for n_bits in (8, 10, 12):
        assert np.isclose(enob_from_sndr(DB_PER_BIT * n_bits + SINE_HEADROOM_DB), n_bits)


def test_the_figures_of_merit_move_the_way_they_are_defined_to():
    """Both reward the same two things in opposite directions, so a sign error
    in either would make a worse part look better."""
    base = walden_fom(POWER, 10.0, SAMPLE_RATE)
    assert walden_fom(2 * POWER, 10.0, SAMPLE_RATE) > base
    assert walden_fom(POWER, 11.0, SAMPLE_RATE) < base
    assert walden_fom(POWER, 10.0, 2 * SAMPLE_RATE) < base

    quiet = schreier_fom(60.0, BANDWIDTH, POWER)
    assert schreier_fom(66.0, BANDWIDTH, POWER) > quiet
    assert schreier_fom(60.0, BANDWIDTH, 2 * POWER) < quiet


#: An illustrative comparator load and a digital term, for the budget's
#: arithmetic. Neither is a design value: one needs a comparator that does not
#: exist and the other a synthesised netlist.
LATCH_FARADS = 10e-15
LATCH_NODES = 4
DIGITAL_JOULES = 1e-12

#: The supply the digital half runs from, volts.
VDD = 1.8


def budget_for(vin: float = 0.0) -> Budget:
    units = ideal_units(WIDE_BITS, C_UNIT)
    return Budget(
        reference=reference_charge(vin, units, VREF) * VREF,
        comparator=WIDE_BITS * switching_energy(LATCH_FARADS, VDD, LATCH_NODES),
        digital=DIGITAL_JOULES,
    )


def test_a_switching_node_costs_the_whole_of_c_v_squared():
    """Not half. Charging through a resistance dissipates as much as it
    stores, and discharging dissipates what was stored, so one up-and-down
    costs the supply all of it whatever the resistance was."""
    assert switching_energy(LATCH_FARADS, VDD) == pytest.approx(LATCH_FARADS * VDD**2)
    assert switching_energy(LATCH_FARADS, VDD, LATCH_NODES) == pytest.approx(
        LATCH_NODES * LATCH_FARADS * VDD**2
    )
    assert switching_energy(LATCH_FARADS, 2 * VDD) == pytest.approx(
        4 * switching_energy(LATCH_FARADS, VDD)
    )


def test_a_budget_is_its_terms_and_says_which_one_dominates():
    """The point of splitting it: a total alone does not say where to look."""
    budget = budget_for()
    assert budget.total == pytest.approx(budget.reference + budget.comparator + budget.digital)
    assert sum(budget.shares.values()) == pytest.approx(1.0)
    assert max(budget.shares, key=budget.shares.get) == "reference"


def test_the_array_is_where_this_converter_spends():
    """And the result that makes the reference pin the one to design around:
    charging a picofarad array off a volt costs more than everything else a
    conversion does put together. Not by orders, though -- a latch switching a
    few nodes once per trial is a sixth of it, which is enough that a
    comparator sized without thought could change the answer."""
    budget = budget_for()
    assert budget.reference > budget.comparator + budget.digital


def test_power_is_energy_at_a_rate():
    budget = budget_for()
    assert budget.power(SAMPLE_RATE) == pytest.approx(budget.total * SAMPLE_RATE)
    assert budget.power(0.0) == 0.0


def test_the_supply_allowance_is_a_third_bound_on_the_rate():
    """Beside settling and the reference pin's own current. Exceeding it is
    not a slow converter but a wrong one, because everything on the die shares
    the droop it causes."""
    budget = budget_for()
    rate = rate_a_supply_can_carry(budget, VDD, I_PDN_DROP)
    assert rate > 0.0
    assert budget.power(rate) == pytest.approx(VDD * I_PDN_DROP)


def test_the_supply_is_not_what_binds_this_converter_either():
    """Like the reference pin's current limit: the platform's allowance sits
    far above the rate settling permits."""
    units = ideal_units(WIDE_BITS, C_UNIT)
    total = float(units.sum())
    tau = sampling_loop_resistance(R_PIN, R_PIN, R_PIN) * total
    phase = settle_time(tau, VREF, TOLERANCE_LSB * lsb_ideal(WIDE_BITS, VREF))
    settling_limited = 1.0 / ((WIDE_BITS + OVERHEAD_PHASES) * phase)
    worst = max(budget_for(vin).total for vin in midcode_inputs(WIDE_BITS, 16, VREF))
    assert rate_a_supply_can_carry(Budget(reference=worst), VDD, I_PDN_DROP) > (
        PIN_HEADROOM * settling_limited
    )


@pytest.mark.parametrize(
    "call",
    [
        lambda: switching_energy(-1e-15, VDD),
        lambda: Budget(reference=-1.0),
        lambda: Budget(reference=0.0).shares,
        lambda: Budget(reference=1e-12).power(-1.0),
        lambda: rate_a_supply_can_carry(Budget(reference=0.0), VDD, I_PDN_DROP),
    ],
)
def test_a_budget_that_is_not_one_is_refused(call):
    with pytest.raises(ValueError):
        call()
