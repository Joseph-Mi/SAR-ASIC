"""What the result pins show, and when the flag says they changed.

The firmware on the other side is written against one rule: wait for the flag,
then read the pins. These are the cases that rule has to survive -- including a
mechanical button, whose contacts bounce.
"""

from __future__ import annotations

import pytest

from readout import EDGE_CAPTURE, INITIAL_CODE, LEVEL_HOLD, MODES, Readout

#: Codes distinct from each other and from the register's reset value, so a
#: result that failed to land is never mistaken for one that did.
CODES = (3, 7, 11, 21)

#: Contact bounces before a button's level settles.
BOUNCES = 3


def test_a_mode_it_cannot_be_in_is_refused():
    with pytest.raises(ValueError):
        Readout(mode="hold_forever")


def test_nothing_shows_before_the_first_conversion():
    for mode in MODES:
        assert Readout(mode=mode).code == INITIAL_CODE


def test_every_conversion_reaches_the_pins_while_the_pin_is_low():
    """The default: live, so a part with nothing attached to the pin converts
    and shows it."""
    r = Readout()
    for code in CODES:
        r.pin(False)
        r.finished(code)
        assert r.code == code
        assert r.done


def test_a_held_pin_freezes_the_pins():
    r = Readout()
    r.pin(False)
    r.finished(CODES[0])
    r.pin(True)
    for code in CODES[1:]:
        r.finished(code)
        assert r.code == CODES[0]
        assert not r.done


def test_releasing_the_hold_lets_the_next_result_through():
    r = Readout()
    r.pin(True)
    r.finished(CODES[0])
    r.pin(False)
    r.finished(CODES[1])
    assert r.code == CODES[1]
    assert r.done


def test_edge_capture_shows_nothing_until_one_is_asked_for():
    r = Readout(mode=EDGE_CAPTURE)
    for code in CODES:
        r.pin(False)
        r.finished(code)
        assert r.code == INITIAL_CODE
        assert not r.done


def test_one_edge_serves_one_result():
    r = Readout(mode=EDGE_CAPTURE)
    r.pin(False)
    r.pin(True)
    r.finished(CODES[0])
    assert r.code == CODES[0]
    assert r.done
    r.finished(CODES[1])
    assert r.code == CODES[0]
    assert not r.done


def test_a_request_outlives_the_edge_that_made_it():
    """The edge lands on whatever cycle the button closes, which is almost
    never the cycle a conversion ends."""
    r = Readout(mode=EDGE_CAPTURE)
    r.pin(False)
    r.pin(True)
    for _ in range(BOUNCES):
        r.idle()
    r.finished(CODES[0])
    assert r.code == CODES[0]
    assert r.done


def test_a_bouncing_button_captures_once():
    """Several edges before a conversion ask for the same one result, so no
    debounce is needed: the request is not a count."""
    r = Readout(mode=EDGE_CAPTURE)
    for _ in range(BOUNCES):
        r.pin(False)
        r.pin(True)
    r.finished(CODES[0])
    assert r.code == CODES[0]
    assert r.done
    r.finished(CODES[1])
    assert r.code == CODES[0]


def test_the_flag_is_up_exactly_when_the_pins_took_the_result():
    """The one rule the firmware is written against: the flag up means these
    pins are this conversion's, and the flag down means they are not."""
    for mode in MODES:
        r = Readout(mode=mode)
        for code in CODES:
            for level in (False, True):
                r.pin(level)
                before = r.code
                r.finished(code)
                assert r.code == (code if r.done else before)


def test_a_cycle_with_no_conversion_lowers_the_flag():
    r = Readout()
    r.pin(False)
    r.finished(CODES[0])
    r.idle()
    assert not r.done
    assert r.code == CODES[0]
