"""The comparator, as a thing with a speed and a floor rather than a sign.

These fix what the converter asks of it, which is the half of the
specification that belongs to the converter and can be written before any
comparator exists.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from comparator import (
    decision_time,
    margin_after,
    margins,
    noise_for_margin,
    resolution,
    swing_division,
    worst_margin,
)
from sar import ideal_units, sar_convert

VREF = 1.0
N_BITS = 10

#: Regeneration time constants to bracket a real latch with, seconds. A small
#: one in this process is tens of picoseconds; the slow end is generous.
FAST_TAU, SLOW_TAU = 20e-12, 500e-12

#: Separation that counts as decided, volts: a supply rail.
SWING = 1.8

#: Strobe lengths, seconds: one the design gives, and one far too short.
DESIGN_STROBE, STARVED_STROBE = 100e-9, 100e-12

#: A strobe of a few tens of time constants: long enough that the floor is
#: small, short enough that it is still a number a double can hold. The
#: design's own strobe is not, which is a result in itself.
MODEST_STROBE = 20 * SLOW_TAU

#: Inputs to read margins at, chosen off every threshold.
PROBES = (0.0137, 0.3137, 0.5137, 0.9137)

#: Agreement demanded where two routes compute the same quantity.
EXACT = 1e-12

#: Standard deviations a decision is held to. Ten bits is a thousand codes
#: and a converter runs many conversions, so the confidence has to be high
#: enough that the bottom bit is right nearly always, not merely usually.
SIGMAS = 4.0


def test_a_longer_strobe_resolves_a_smaller_difference():
    """Exponentially: which is why a comparator fast enough at all is usually
    fast enough by a wide margin, and one that is not fails suddenly."""
    generous = resolution(FAST_TAU, DESIGN_STROBE, SWING)
    starved = resolution(FAST_TAU, STARVED_STROBE, SWING)
    assert generous < starved < SWING
    assert resolution(FAST_TAU, 0.0, SWING) == SWING


def test_the_two_forms_are_the_same_law():
    """A difference exactly at the floor takes exactly the strobe to resolve.
    They are each other's inverse, so a bound derived from one holds in the
    other."""
    for tau in (FAST_TAU, SLOW_TAU):
        floor = resolution(tau, MODEST_STROBE, SWING)
        assert floor > 0.0
        assert decision_time(floor, tau, SWING) == pytest.approx(MODEST_STROBE)


def test_the_strobe_this_design_gives_leaves_no_window_a_number_can_hold():
    """The result worth having before designing anything: at this conversion
    rate the latch is given hundreds of time constants, so the difference it
    could fail to separate underflows a double. Metastability is a thing to
    detect, not a thing to budget for -- and that is why the flag is cheap
    insurance rather than a live hazard.
    """
    assert resolution(FAST_TAU, DESIGN_STROBE, SWING) == 0.0
    assert resolution(SLOW_TAU, DESIGN_STROBE, SWING) < worst_margin(N_BITS, VREF) / 1e60


def test_a_smaller_difference_takes_longer_but_only_logarithmically():
    """The reason a hundredfold harder decision is not a hundredfold slower."""
    near = decision_time(1e-3, FAST_TAU, SWING)
    far = decision_time(1e-5, FAST_TAU, SWING)
    assert far > near
    assert far - near == pytest.approx(FAST_TAU * math.log(100))


def test_a_difference_already_separated_needs_no_time():
    assert decision_time(SWING, FAST_TAU, SWING) == 0.0


def test_the_search_halves_what_it_asks_for():
    """Which is what makes the last trial the one a specification is written
    from: every trial before it is an easier question."""
    units = ideal_units(N_BITS)
    for vin in PROBES:
        asked = margins(vin, units, VREF)
        assert len(asked) == N_BITS
        assert min(asked) <= worst_margin(N_BITS, VREF)


def test_the_margins_are_the_differences_the_search_really_presents():
    """Read against the decisions themselves: a margin is only meaningful if
    it belongs to the trial the converter actually ran."""
    units = ideal_units(N_BITS)
    for vin in PROBES:
        _, trace = sar_convert(vin, units, VREF)
        assert len(margins(vin, units, VREF)) == len(trace)


def test_the_worst_question_is_half_a_least_significant_bit():
    """The number every comparator figure is a fraction of."""
    for n_bits in (8, 10, 12):
        assert worst_margin(n_bits, VREF) == pytest.approx(VREF / 2**n_bits / 2)
    assert worst_margin(N_BITS, VREF) > worst_margin(N_BITS + 1, VREF)


def test_a_parasitic_divides_every_margin_by_the_same_factor():
    """Which is why a specification is written at the comparator and converted
    once, rather than carried divided through every expression."""
    assert swing_division(1.0, 0.0) == 1.0
    assert swing_division(1.0, 1.0) == pytest.approx(0.5)
    assert swing_division(1.0, 0.1) < 1.0


def test_an_unresolved_trial_falls_either_way():
    """The state the interface carries two wires to detect. A window wide
    enough to swallow the last trial makes the bottom bit a coin toss, and no
    amount of averaging in the converter recovers it."""
    units = ideal_units(N_BITS)
    vin = 0.5 + worst_margin(N_BITS, VREF) / 2
    window = 2 * worst_margin(N_BITS, VREF)
    seen = {
        sar_convert(vin, units, VREF, cmp_resolution=window, rng=np.random.default_rng(seed))[0]
        for seed in range(32)
    }
    assert len(seen) > 1


def test_a_window_the_search_never_enters_changes_nothing():
    """And the design point: a latch given far more time than it needs decides
    exactly as an exact one would."""
    units = ideal_units(N_BITS)
    tiny = resolution(FAST_TAU, DESIGN_STROBE, SWING)
    for vin in PROBES:
        want = sar_convert(vin, units, VREF)
        got = sar_convert(vin, units, VREF, cmp_resolution=tiny, rng=np.random.default_rng(0))
        assert got == want


def test_a_comparator_that_is_not_exact_needs_a_seed():
    units = ideal_units(N_BITS)
    with pytest.raises(ValueError, match="rng"):
        sar_convert(0.3, units, VREF, cmp_resolution=1e-6)


@pytest.mark.parametrize(
    "call",
    [
        lambda: resolution(0.0, 1e-9, SWING),
        lambda: resolution(FAST_TAU, -1.0, SWING),
        lambda: resolution(FAST_TAU, DESIGN_STROBE, 0.0),
        lambda: decision_time(1e-3, 0.0, SWING),
        lambda: decision_time(1e-3, FAST_TAU, 0.0),
        lambda: decision_time(0.0, FAST_TAU, SWING),
        lambda: worst_margin(0),
        lambda: swing_division(0.0, 1e-15),
        lambda: swing_division(1e-12, -1e-15),
    ],
)
def test_a_quantity_that_is_not_one_is_refused(call):
    with pytest.raises(ValueError):
        call()


def test_a_margin_is_eaten_by_offset_directly_and_by_noise_at_a_confidence():
    """The specification, written as a subtraction. Positive means the input
    decides the bit; negative means the comparator does."""
    margin = worst_margin(N_BITS, VREF)
    assert margin_after(margin, 0.0, 0.0, SIGMAS) == margin
    assert margin_after(margin, margin / 4, 0.0, SIGMAS) == pytest.approx(3 * margin / 4)
    assert margin_after(margin, 0.0, margin / SIGMAS, SIGMAS) == pytest.approx(0.0)
    assert margin_after(margin, 0.0, margin, SIGMAS) < 0.0


def test_offset_is_subtracted_whichever_way_it_leans():
    margin = worst_margin(N_BITS, VREF)
    assert margin_after(margin, 1e-4, 0.0, SIGMAS) == margin_after(margin, -1e-4, 0.0, SIGMAS)


def test_the_noise_a_margin_allows_is_the_specification_read_backwards():
    """The direction a comparator is designed in: the converter fixes the
    margin, the confidence is chosen, and the number the latch must meet falls
    out."""
    margin = worst_margin(N_BITS, VREF)
    allowed = noise_for_margin(margin, SIGMAS)
    assert margin_after(margin, 0.0, allowed, SIGMAS) == pytest.approx(0.0)
    assert noise_for_margin(margin, 2 * SIGMAS) == pytest.approx(allowed / 2)


def test_a_parasitic_makes_the_specification_harder_by_exactly_its_divider():
    """Where the two halves of the budget meet. A margin at the converter's
    input arrives at the comparator divided, so the noise it will carry is
    divided with it."""
    margin = worst_margin(N_BITS, VREF)
    divided = margin * swing_division(1.0, 0.25)
    assert noise_for_margin(divided, SIGMAS) == pytest.approx(
        noise_for_margin(margin, SIGMAS) * 0.8
    )


@pytest.mark.parametrize(
    "call",
    [
        lambda: margin_after(1e-3, 0.0, -1e-6, SIGMAS),
        lambda: margin_after(1e-3, 0.0, 1e-6, -1.0),
        lambda: noise_for_margin(0.0, SIGMAS),
        lambda: noise_for_margin(1e-3, 0.0),
    ],
)
def test_a_specification_that_is_not_one_is_refused(call):
    with pytest.raises(ValueError):
        call()
