"""The charge a switch holds, and what releasing it does to a node."""

import pytest

from injection import beyond_a_line, channel_charge, hold_step, referred_to_input

W, L, COX = 2e-6, 0.15e-6, 8e-3
C_NODE = 1e-12

#: A gate drive, one below threshold, and the scale by which a test doubles a
#: quantity.
OVERDRIVE = 0.5
BELOW_THRESHOLD = -0.1
DOUBLE = 2

#: The share of a channel's charge the node receives by default.
HALF_SHARE = 0.5

#: Illustrative per-input steps: one constant, and deviations that wander
#: around it.
STEP = -1e-3
WANDER = (0.0, -0.2e-3, -0.1e-3, 0.1e-3, -0.3e-3)

#: A straight-line error across the range: an offset and a gain, and a kink.
LINE_INPUTS = [0.0, 0.25, 0.5, 0.75, 1.0]
OFFSET, GAIN = 0.3, 0.2
KINK = 0.1
ROUNDING = 1e-12


def test_an_off_switch_holds_no_channel():
    assert channel_charge(W, L, COX, BELOW_THRESHOLD) == 0.0


def test_the_channel_grows_with_width_and_overdrive():
    """A wider switch, or one driven harder, holds proportionally more charge:
    the price of the lower resistance that makes it settle faster."""
    base = channel_charge(W, L, COX, OVERDRIVE)
    assert channel_charge(DOUBLE * W, L, COX, OVERDRIVE) == pytest.approx(DOUBLE * base)
    assert channel_charge(W, L, COX, DOUBLE * OVERDRIVE) == pytest.approx(DOUBLE * base)


def test_releasing_electrons_pulls_the_node_down_by_its_share():
    q = channel_charge(W, L, COX, OVERDRIVE)
    assert hold_step(q, C_NODE) == pytest.approx(-q * HALF_SHARE / C_NODE)
    assert hold_step(q, C_NODE, share=1.0) == pytest.approx(-q / C_NODE)


def test_a_bigger_node_moves_less():
    q = channel_charge(W, L, COX, OVERDRIVE)
    bigger = abs(hold_step(q, DOUBLE * C_NODE))
    assert bigger == pytest.approx(abs(hold_step(q, C_NODE)) / DOUBLE)


def test_a_constant_step_is_an_offset_and_a_varying_one_is_not():
    """What matters is how the step varies with the input: a constant one is
    an offset -- measured and removed -- and whatever varies is left."""
    constant = [STEP] * len(WANDER)
    varying = [STEP + w for w in WANDER]
    assert referred_to_input(constant) == (pytest.approx(STEP), pytest.approx(0.0))
    offset, residue = referred_to_input(varying)
    assert offset == pytest.approx(STEP + (min(WANDER) + max(WANDER)) / 2)
    assert residue == pytest.approx(max(WANDER) - min(WANDER))


def test_an_offset_and_a_gain_leave_nothing_beyond_a_line():
    steps = [OFFSET + GAIN * x for x in LINE_INPUTS]
    assert beyond_a_line(LINE_INPUTS, steps) == pytest.approx(0.0, abs=ROUNDING)


def test_a_bend_is_what_remains():
    """A kink at one input stands out of the line by exactly its size, where
    the offset/spread split would count the whole slope as spread too."""
    steps = [GAIN * x for x in LINE_INPUTS]
    steps[len(steps) // 2] += KINK
    assert beyond_a_line(LINE_INPUTS, steps) == pytest.approx(KINK)
    assert referred_to_input(steps)[1] > beyond_a_line(LINE_INPUTS, steps)
