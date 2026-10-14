"""What a StrongARM latch can and cannot be sized into, before one exists.

The question these answer is whether this converter's noise target is
reachable by making the latch bigger, or whether it needs a stage in front of
it. That is decidable from the laws alone, which is why it is decided here
rather than after a week of sizing runs.
"""

from __future__ import annotations

import math

import pytest

import sky130
from comparator import decision_time, noise_for_margin, swing_division, worst_margin
from interface import N_BITS
from latch import (
    EXCESS_NOISE,
    energy_per_decision,
    input_noise,
    input_noise_from_sizing,
    input_offset,
    integration_gain,
    node_for_noise,
    preamp_gain_for_noise,
    regeneration_tau,
    threshold_sigma,
    trip_time,
)
from noise import BOLTZMANN, ROOM

VREF = 1.0
SUPPLY = 1.8

#: Standard deviations the design holds a decision to.
SIGMAS = 4.0

#: What the converter asks of its comparator, volts rms. Derived rather than
#: restated: the resolution fixes the margin and the confidence fixes the rest.
TARGET = noise_for_margin(worst_margin(N_BITS, VREF), SIGMAS)

#: Transconductance efficiency of an input pair run in moderate inversion,
#: per volt. An assumption: it is what a sized device measures, and the useful
#: range for a latch input is narrow, since weak inversion buys efficiency and
#: costs the area that was the point.
EFFICIENCY = 20.0

#: How far an integration node falls before the cross-coupled devices take
#: the decision away from the input pair, volts. An assumption, set by where
#: those devices turn on rather than by anything chosen.
SWING = 0.6

#: The integration node of a latch drawn near the process minimum, farads.
#: An assumption, and the one the rest of this is measured against.
BARE_NODE = 20e-15

#: A tail current in the range a tile can spend. Nothing here should depend on
#: it, which is itself one of the results.
TAIL = 20e-6

#: An input capacitance far above what a latch input pair presents, farads.
#: Used to bound what growing the pair can cost the array, not to predict it.
GENEROUS_INPUT = 100e-15

#: The array this design builds, farads.
ARRAY = 2**N_BITS * sky130.mim_unit()


def bare_noise(node: float = BARE_NODE) -> float:
    return input_noise_from_sizing(EFFICIENCY, node, SWING)


def test_the_two_forms_of_the_noise_are_one_law():
    """One takes a measured transconductance and integration time, the other
    takes what a designer chooses. They have to agree, or a measurement cannot
    be checked against a sizing decision."""
    drain = TAIL / 2
    gm = EFFICIENCY * drain
    measured = input_noise(gm, trip_time(BARE_NODE, TAIL, SWING))
    assert measured == pytest.approx(bare_noise())


def test_the_tail_current_cancels_out_of_the_noise():
    """The result worth knowing before sizing anything: a hungrier latch gains
    transconductance and loses integration time by the same factor. Current
    buys speed and nothing else."""
    quiet = []
    for tail in (TAIL, 4 * TAIL, 16 * TAIL):
        gm = EFFICIENCY * tail / 2
        quiet.append(input_noise(gm, trip_time(BARE_NODE, tail, SWING)))
    assert quiet[1] == pytest.approx(quiet[0])
    assert quiet[2] == pytest.approx(quiet[0])


def test_the_noise_is_the_law_and_not_an_approximation_of_it():
    gm, t_int = EFFICIENCY * TAIL / 2, trip_time(BARE_NODE, TAIL, SWING)
    assert input_noise(gm, t_int) == pytest.approx(
        math.sqrt(4.0 * BOLTZMANN * ROOM * EXCESS_NOISE / (gm * t_int))
    )


def test_quiet_is_bought_with_node_charge_and_efficiency_only():
    """Each of the three terms in the charge enters the same way, which is
    what makes them interchangeable in a sizing decision."""
    assert bare_noise(4 * BARE_NODE) == pytest.approx(bare_noise() / 2)
    assert input_noise_from_sizing(EFFICIENCY, BARE_NODE, 4 * SWING) == pytest.approx(
        bare_noise() / 2
    )
    assert input_noise_from_sizing(4 * EFFICIENCY, BARE_NODE, SWING) == pytest.approx(
        bare_noise() / 2
    )


def test_a_latch_drawn_near_the_process_minimum_misses_this_converters_target():
    """The reason M5 has a preamplifier decision in it at all. The latch is
    not close enough for sizing to be a detail."""
    assert bare_noise() > 2 * TARGET


def test_meeting_it_with_latch_alone_costs_an_order_of_magnitude_of_node():
    """Because noise goes as the reciprocal root of the node, the shortfall
    above is squared on the way to what fixes it."""
    needed = node_for_noise(TARGET, EFFICIENCY, SWING)
    assert bare_noise(needed) == pytest.approx(TARGET)
    assert needed > 8 * BARE_NODE


def test_halving_the_noise_asks_for_four_times_the_node():
    assert node_for_noise(TARGET / 2, EFFICIENCY, SWING) == pytest.approx(
        4 * node_for_noise(TARGET, EFFICIENCY, SWING)
    )


def test_a_preamplifier_has_to_beat_the_shortfall_and_nothing_more():
    gain = preamp_gain_for_noise(TARGET, bare_noise())
    assert gain == pytest.approx(bare_noise() / TARGET)
    assert bare_noise() / gain == pytest.approx(TARGET)


def test_a_latch_already_quiet_enough_asks_for_no_gain():
    """A gain below one is not a preamplifier, so the bound stops at one
    rather than going on to say an attenuator would do."""
    assert preamp_gain_for_noise(TARGET, TARGET / 2) == 1.0


def test_growing_the_input_pair_does_not_cost_this_array_its_swing():
    """The other end of the trade, and the reason it is open: whatever the
    pair's gate presents lands on the top plate, where it divides the margin
    the latch is being made quiet enough to resolve. On an array this large
    there is room to spend."""
    assert swing_division(ARRAY, GENEROUS_INPUT) > 0.98


def test_everything_past_the_integration_node_is_divided_by_its_gain():
    """Which is why a latch that integrates for longer is better centred as
    well as quieter, and why only the input pair's own mismatch is
    irreducible."""
    pair = threshold_sigma(5e-3, 2.0, 0.5)
    gain = integration_gain(EFFICIENCY * TAIL / 2, trip_time(BARE_NODE, TAIL, SWING), BARE_NODE)
    assert input_offset(pair, 10 * pair, gain) < input_offset(pair, 10 * pair, gain / 4)
    assert input_offset(pair, 10 * pair, gain) >= pair


def test_mismatch_falls_as_the_root_of_area():
    assert threshold_sigma(5e-3, 4.0, 1.0) == pytest.approx(threshold_sigma(5e-3, 1.0, 1.0) / 2)
    assert threshold_sigma(5e-3, 2.0, 2.0) == pytest.approx(threshold_sigma(5e-3, 1.0, 1.0) / 2)


def test_regeneration_is_not_what_binds():
    """A decision on half an LSB takes a few time constants, and the strobe is
    a settling time long. The latch's second stage never sets a
    specification here."""
    tau = regeneration_tau(BARE_NODE, EFFICIENCY * TAIL / 2)
    assert decision_time(worst_margin(N_BITS, VREF), tau, SUPPLY) < 100 * tau


def test_the_node_bought_for_quiet_is_also_what_the_strobe_pays_for():
    """The cost side of the same trade, and the reason a preamplifier competes
    rather than losing outright: energy goes up with the node that noise goes
    down with."""
    needed = node_for_noise(TARGET, EFFICIENCY, SWING)
    assert energy_per_decision(needed, BARE_NODE, SUPPLY) > energy_per_decision(
        BARE_NODE, BARE_NODE, SUPPLY
    )
    assert energy_per_decision(BARE_NODE, BARE_NODE, 2 * SUPPLY) == pytest.approx(
        4 * energy_per_decision(BARE_NODE, BARE_NODE, SUPPLY)
    )


@pytest.mark.parametrize(
    "call",
    [
        lambda: trip_time(0.0, TAIL, SWING),
        lambda: trip_time(BARE_NODE, 0.0, SWING),
        lambda: trip_time(BARE_NODE, TAIL, 0.0),
        lambda: integration_gain(0.0, 1e-9, BARE_NODE),
        lambda: integration_gain(1e-3, 0.0, BARE_NODE),
        lambda: input_noise(0.0, 1e-9),
        lambda: input_noise(1e-3, 1e-9, excess=0.0),
        lambda: input_noise(1e-3, 1e-9, temperature=0.0),
        lambda: input_noise_from_sizing(0.0, BARE_NODE, SWING),
        lambda: input_noise_from_sizing(EFFICIENCY, BARE_NODE, 0.0),
        lambda: node_for_noise(0.0, EFFICIENCY, SWING),
        lambda: preamp_gain_for_noise(0.0, 1e-4),
        lambda: preamp_gain_for_noise(1e-4, 0.0),
        lambda: regeneration_tau(0.0, 1e-3),
        lambda: regeneration_tau(BARE_NODE, 0.0),
        lambda: threshold_sigma(0.0, 1.0, 1.0),
        lambda: threshold_sigma(5e-3, 0.0, 1.0),
        lambda: input_offset(-1.0, 0.0, 1.0),
        lambda: input_offset(0.0, 0.0, 0.0),
        lambda: energy_per_decision(-1.0, BARE_NODE, SUPPLY),
    ],
)
def test_an_impossible_sizing_is_refused(call):
    with pytest.raises(ValueError):
        call()
