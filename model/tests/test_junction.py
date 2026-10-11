"""A nonlinear parasitic on the top plate, held to the claim that it is harmless.

The claim is strong enough to be worth attacking from several directions: that
a capacitance which changes with voltage, sitting on the one node whose charge
the whole conversion depends on, moves no threshold at all. Each test here is a
different way for that to be false.
"""

from __future__ import annotations

import numpy as np
import pytest

from junction import (
    ABRUPT,
    ABSENT,
    LINEARLY_GRADED,
    Junction,
    decisions,
    input_at_decision,
    leakage_droop_lsb,
    swing_gain,
    tau_multiplier,
    top_plate_voltage,
)
from metrics import inl, lsb_ideal
from protocol import trial_words
from sar import VCM_FRACTION, ideal_units, sar_convert
from sar import top_plate_voltage as linear_top_plate

VREF = 1.0
SMALL_BITS = 6
BITS = 10

#: Junction sizes as a fraction of the whole array, from one that would be
#: ignored to one no layout would tolerate. A claim that holds at the top of
#: this range is not resting on the parasitic being small.
FRACTIONS = (0.01, 0.1, 0.5, 2.0)

#: Grading exponents to hold every result at: the two the physics brackets, and
#: one between them.
GRADINGS = (LINEARLY_GRADED, 0.4, ABRUPT)

#: Built-in potentials either side of silicon's, so no result depends on the
#: particular value.
POTENTIALS = (0.4, 0.75, 1.2)

#: Where the junction's other side is held. Ground is the n-drain of a switch
#: in a p-substrate; the reference is one in a well tied up.
BODIES = (0.0, -VREF)

#: Inputs spread over the range, including both ends, where the node sits
#: closest to a rail and the junction is therefore least linear.
INPUTS = (0.001, 0.123, 0.5, 0.751, 0.999)

#: Volts of comparator offset to probe the offset-amplification result with.
#: Small enough that the first-order prediction is meant to hold.
OFFSET = 1e-4

#: A built-in potential far above the swing, where the depletion law is flat
#: and the nonlinear solve has to reproduce the linear closed form.
FLAT_POTENTIAL = 1e6

#: Agreement demanded of two ways of computing the same voltage, volts. Set by
#: the bisection's own tolerance, not by physics.
SOLVE_VOLTS = 1e-9

#: How closely the flat-junction limit must match the linear closed form, as a
#: fraction of an LSB. The law is flat, not constant, so the limit is
#: approached rather than reached.
FLAT_LSB = 1e-3

#: Fraction of an LSB that counts as the same threshold. Thresholds are
#: claimed exactly equal, so this is only the arithmetic's own noise.
SAME_THRESHOLD_LSB = 1e-6

#: How closely the offset shift must match (1 + C_j/C_total) * offset.
FIRST_ORDER = 1e-3

#: An illustrative leakage current and hold time, to check the droop
#: expression responds the way charge loss does. Neither is a design value.
LEAKAGE_AMPS = 1e-12
HOLD_SECONDS = 1e-6
TOTAL_FARADS = 8e-12


def junctions():
    """Every junction the sweeps are run against, as a fraction of the array."""
    total = 2**BITS
    return [
        Junction(c_zero=fraction * total, phi_b=phi_b, grading=grading)
        for fraction in FRACTIONS
        for grading in GRADINGS
        for phi_b in POTENTIALS
    ]


def test_no_junction_reproduces_the_linear_model():
    """The numerical balance and the rearranged closed form are two
    implementations of one equation, so they have to agree before anything
    built on the first means anything."""
    units = ideal_units(SMALL_BITS)
    for vin in INPUTS:
        for code in range(2**SMALL_BITS):
            got = top_plate_voltage(vin, code, units, ABSENT, vref=VREF)
            want = linear_top_plate(vin, code, units, vref=VREF)
            assert abs(got - want) < SOLVE_VOLTS, (vin, code)


def test_a_junction_flat_over_the_swing_is_the_linear_parasitic():
    """A depletion law whose built-in potential dwarfs the swing is a constant
    capacitance, and then the nonlinear solve has to land on the answer the
    linear parasitic already gives."""
    units = ideal_units(SMALL_BITS)
    total = float(units.sum())
    c_par = 0.25 * total
    flat = Junction(c_zero=c_par, phi_b=FLAT_POTENTIAL, grading=ABRUPT)
    tolerance = FLAT_LSB * lsb_ideal(SMALL_BITS, VREF)
    for vin in INPUTS:
        for trial in trial_words(vin, units, VREF):
            got = top_plate_voltage(vin, trial, units, flat, vref=VREF)
            want = linear_top_plate(vin, trial, units, vref=VREF, c_par=c_par)
            assert abs(got - want) < tolerance, (vin, trial)


def test_a_junction_moves_no_threshold_however_nonlinear_it_is():
    """The whole claim, over every junction and every code.

    A threshold is where the top plate reaches the comparator's reference, and
    the junction holds the same charge there as it held at sampling -- the two
    are the same voltage. The cancellation is of charge at a voltage, which a
    nonlinear capacitance supplies as readily as a linear one.
    """
    units = ideal_units(SMALL_BITS)
    tolerance = SAME_THRESHOLD_LSB * lsb_ideal(SMALL_BITS, VREF)
    ideal = [input_at_decision(code, units, ABSENT, vref=VREF) for code in range(2**SMALL_BITS)]
    for junction in junctions():
        for v_body in BODIES:
            got = [
                input_at_decision(code, units, junction, vref=VREF, v_body=v_body)
                for code in range(2**SMALL_BITS)
            ]
            assert np.allclose(got, ideal, atol=tolerance), (junction, v_body)


def test_a_junction_adds_no_integral_nonlinearity():
    """Said as the measurement a bench would make, rather than as an identity.

    Thresholds unmoved is the same statement as INL unchanged, but INL is the
    number a datasheet carries, and reading it off the junction model is what
    makes the claim falsifiable by the same code path the mismatch study uses.
    """
    units = ideal_units(BITS)
    assert np.abs(inl(units, VREF)).max() < SAME_THRESHOLD_LSB
    for junction in junctions():
        thresholds = np.array(
            [input_at_decision(code, units, junction, vref=VREF) for code in range(1, 2**BITS)]
        )
        steps = np.diff(thresholds)
        drift = np.abs(steps - steps.mean()).max() / lsb_ideal(BITS, VREF)
        assert drift < SAME_THRESHOLD_LSB, junction


def test_every_code_survives_the_nonlinear_node():
    """End to end: run the search against node voltages the junction produced,
    and the decisions have to be the ones the golden model takes."""
    units = ideal_units(SMALL_BITS)
    probes = junctions()[:: len(POTENTIALS)]
    for junction in probes:
        for vin in INPUTS:
            want_code, want_trace = sar_convert(vin, units, VREF)
            got_code, got_trace = decisions(vin, units, junction, vref=VREF)
            assert (got_code, got_trace) == (want_code, want_trace), (junction, vin)


def test_comparator_offset_is_amplified_but_stays_an_offset():
    """With a comparator offset the junction does appear in the threshold --
    and appears identically in every one of them, which is an offset and not a
    nonlinearity. That is the result that decides whether a nonlinear
    parasitic is a calibration problem or a scrap problem."""
    units = ideal_units(SMALL_BITS)
    total = float(units.sum())
    reference = VCM_FRACTION * VREF
    tolerance = SAME_THRESHOLD_LSB * lsb_ideal(SMALL_BITS, VREF)
    for junction in junctions():
        for v_body in BODIES:
            shifts = np.array(
                [
                    input_at_decision(
                        code, units, junction, vref=VREF, v_body=v_body, node_offset=OFFSET
                    )
                    - input_at_decision(code, units, junction, vref=VREF, v_body=v_body)
                    for code in range(2**SMALL_BITS)
                ]
            )
            assert np.ptp(shifts) < tolerance, (junction, v_body)
            gain = 1.0 + junction.capacitance(reference - v_body) / total
            assert abs(shifts.mean() / (-OFFSET * gain) - 1.0) < FIRST_ORDER, (junction, v_body)


def test_the_swing_is_worst_where_the_node_comes_closest_to_the_body():
    """What the parasitic does cost. The comparator sees a divided swing, and
    the divider is tightest where the junction is least reverse biased -- which
    for a switch in a grounded body is the bottom of the input range, the same
    place the comparator is already hardest to bias."""
    units = ideal_units(BITS)
    total = float(units.sum())
    junction = Junction(c_zero=0.1 * total, phi_b=0.75, grading=ABRUPT)
    worst = {}
    for vin in (0.001, 0.999):
        gains = [
            swing_gain(top_plate_voltage(vin, trial, units, junction, vref=VREF), total, junction)
            for trial in trial_words(vin, units, VREF)
        ]
        worst[vin] = min(gains)
        assert all(0.0 < g < 1.0 for g in gains), vin
    assert worst[0.999] < worst[0.001]


def test_the_settling_allowance_one_trial_needs_is_not_what_another_needs():
    """The one route by which a nonlinear parasitic reaches the codes. Charge
    conservation does not care how long the node took to get there; a settling
    budget does, and the capacitance it charges is not the same at every
    trial."""
    units = ideal_units(BITS)
    total = float(units.sum())
    junction = Junction(c_zero=0.1 * total, phi_b=0.75, grading=ABRUPT)
    multipliers = [
        tau_multiplier(top_plate_voltage(0.999, trial, units, junction, vref=VREF), total, junction)
        for trial in trial_words(vin=0.999, unit_caps=units, vref=VREF)
    ]
    assert min(multipliers) > 1.0
    assert max(multipliers) > min(multipliers)


def test_a_junction_with_no_capacitance_costs_nothing():
    """The absent case has to fall out of the same expressions, so that one
    code path serves both and the two can never disagree."""
    units = ideal_units(SMALL_BITS)
    total = float(units.sum())
    assert swing_gain(VCM_FRACTION * VREF, total, ABSENT) == 1.0
    assert tau_multiplier(VCM_FRACTION * VREF, total, ABSENT) == 1.0
    assert ABSENT.charge(0.5) == 0.0


def test_capacitance_falls_with_reverse_bias_and_charge_rises():
    """The law itself, in the direction depletion runs."""
    junction = Junction(c_zero=1.0, phi_b=0.75, grading=ABRUPT)
    bias = np.linspace(0.0, 2.0, 32)
    assert junction.capacitance(0.0) == junction.c_zero
    assert np.all(np.diff(junction.capacitance(bias)) < 0.0)
    assert np.all(np.diff(junction.charge(bias)) > 0.0)
    assert junction.charge(0.0) == 0.0


def test_the_state_the_sampling_contract_forbids_is_refused():
    """Holding the array at all-ground after sampling drives the top plate to
    the sampling reference minus the input, below the body for most of the
    range. The model refuses to report a voltage there, because a junction on
    that node is conducting and the charge the answer depends on is leaving."""
    units = ideal_units(SMALL_BITS)
    junction = Junction(c_zero=0.1 * float(units.sum()))
    with pytest.raises(ValueError, match="sampling contract"):
        top_plate_voltage(0.999, 0, units, junction, vref=VREF)
    first = 1 << (SMALL_BITS - 1)
    assert top_plate_voltage(0.999, first, units, junction, vref=VREF) >= 0.0


def test_forward_bias_is_refused_rather_than_extrapolated():
    """Below the body the junction conducts. A capacitance returned there would
    be a number with no physics behind it, in exactly the regime the
    architecture's sampling contract exists to stay out of."""
    junction = Junction(c_zero=1.0)
    with pytest.raises(ValueError, match="forward bias"):
        junction.capacitance(-0.1)
    with pytest.raises(ValueError, match="forward bias"):
        junction.charge(-0.1)


def test_leakage_is_the_cost_that_does_not_cancel():
    """Charge that left the node is gone, whatever voltage the node returns to.
    Unlike the capacitance, this is a real error budget item."""
    droop = leakage_droop_lsb(LEAKAGE_AMPS, HOLD_SECONDS, TOTAL_FARADS, BITS, VREF)
    assert droop > 0.0
    doubled = leakage_droop_lsb(LEAKAGE_AMPS, 2 * HOLD_SECONDS, TOTAL_FARADS, BITS, VREF)
    assert np.isclose(doubled, 2 * droop)
    finer = leakage_droop_lsb(LEAKAGE_AMPS, HOLD_SECONDS, TOTAL_FARADS, BITS + 1, VREF)
    assert np.isclose(finer, 2 * droop)


@pytest.mark.parametrize("bad", [{"c_zero": -1.0}, {"phi_b": 0.0}, {"grading": 1.0}])
def test_a_junction_that_is_not_one_is_refused(bad):
    with pytest.raises(ValueError):
        Junction(**{"c_zero": 1.0, **bad})


def test_the_trials_are_the_search_the_protocol_declares():
    """Every figure here is evaluated at the node voltages a conversion
    actually visits, so the trial words have to be the search's own -- taken
    from the module that owns the shape of a conversion, not rebuilt here."""
    units = ideal_units(SMALL_BITS)
    for vin in INPUTS:
        code, trace = sar_convert(vin, units, VREF)
        trials = trial_words(vin, units, VREF)
        assert len(trials) == SMALL_BITS
        settled = 0
        for k, (trial, bit) in enumerate(zip(trials, trace, strict=True)):
            assert trial == settled | (1 << (SMALL_BITS - 1 - k))
            if bit:
                settled = trial
        assert settled == code
