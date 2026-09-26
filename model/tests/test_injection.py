"""The charge a switch holds, and what releasing it does to a node."""

import pytest

from injection import channel_charge, hold_step, referred_to_input

W, L, COX = 2e-6, 0.15e-6, 8e-3
C_NODE = 1e-12


def test_an_off_switch_holds_no_channel():
    assert channel_charge(W, L, COX, -0.1) == 0.0


def test_the_channel_grows_with_width_and_overdrive():
    """A wider switch, or one driven harder, holds proportionally more charge:
    the price of the lower resistance that makes it settle faster."""
    base = channel_charge(W, L, COX, 0.5)
    assert channel_charge(2 * W, L, COX, 0.5) == pytest.approx(2 * base)
    assert channel_charge(W, L, COX, 1.0) == pytest.approx(2 * base)


def test_releasing_electrons_pulls_the_node_down_by_its_share():
    q = channel_charge(W, L, COX, 0.5)
    assert hold_step(q, C_NODE) == pytest.approx(-q / 2 / C_NODE)
    assert hold_step(q, C_NODE, share=1.0) == pytest.approx(-q / C_NODE)


def test_a_bigger_node_moves_less():
    q = channel_charge(W, L, COX, 0.5)
    assert abs(hold_step(q, 2 * C_NODE)) == pytest.approx(abs(hold_step(q, C_NODE)) / 2)


def test_a_constant_step_is_an_offset_and_a_varying_one_is_not():
    """What matters is how the step varies with the input: a constant one is
    an offset -- measured and removed -- and whatever varies is left."""
    constant = [-1e-3] * 5
    varying = [-1e-3, -1.2e-3, -1.1e-3, -0.9e-3, -1.3e-3]
    assert referred_to_input(constant) == (pytest.approx(-1e-3), pytest.approx(0.0))
    offset, residue = referred_to_input(varying)
    assert offset == pytest.approx(-1.1e-3)
    assert residue == pytest.approx(0.4e-3)
