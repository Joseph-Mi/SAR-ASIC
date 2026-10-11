"""What asks for a conversion, in the two modes a jumper chooses between.

The request pin is a mechanical button in the mode that reads it, so these are
the cases a button produces: held down, released, already down when the power
came up, and pressed while the part was busy.
"""

from __future__ import annotations

import pytest

from start import CONTINUOUS, INITIAL_LEVEL, MODES, SINGLE_SHOT, Start
from tick import MAX_DIVISOR, period

#: Cycles a request has to survive to be heard: one interval of the slowest
#: conversion clock the field can ask for, which is the longest the search can
#: go without listening.
WAITING = period(MAX_DIVISOR)

#: Contact bounces before a button's level settles.
BOUNCES = 3

LOW, HIGH = False, True


def cycles(start: Start, count: int, level: bool, ready: bool = True, stepping: bool = True):
    """`count` cycles at a steady pin level: what was asked on each of them."""
    asked = []
    for _ in range(count):
        asked.append(start.asking(ready))
        start.cycle(level, ready, stepping)
    return asked


def press(start: Start, **kwargs) -> None:
    """The pin low for a cycle and then high, which is one press."""
    cycles(start, 1, LOW, **kwargs)
    cycles(start, 1, HIGH, **kwargs)


def test_the_default_mode_converts_without_being_asked():
    """The platform leaves an unconnected input low, so this is the mode a part
    with nothing wired to it is in. Waiting to be asked would read as a dead
    chip on a bench."""
    assert Start().mode == CONTINUOUS
    assert Start().asking(ready=True)


def test_a_mode_it_cannot_be_in_is_refused():
    with pytest.raises(ValueError):
        Start(mode="once_an_hour")


@pytest.mark.parametrize("mode", MODES)
def test_nothing_is_asked_while_the_search_is_busy(mode):
    """An ask that reached a running search would restart it part way, and the
    code that came out would belong to neither conversion."""
    start = Start(mode=mode)
    press(start)
    assert not any(cycles(start, WAITING, HIGH, ready=False))


def test_continuous_asks_again_as_soon_as_the_search_is_idle():
    """Back to back, with no gap it does not ask in: the mode exists so a
    sample rate is the conversion time and nothing else."""
    assert all(cycles(Start(), WAITING, LOW))


def test_continuous_reads_no_pin():
    """So the one that chooses the mode is the only pin this mode needs, and a
    board can leave the other floating."""
    for level in (LOW, HIGH):
        assert all(cycles(Start(), WAITING, level))


def test_single_shot_waits_to_be_asked():
    assert not any(cycles(Start(mode=SINGLE_SHOT), WAITING, LOW))


def test_a_press_asks_for_one_conversion():
    start = Start(mode=SINGLE_SHOT)
    press(start)
    assert start.asking(ready=True)
    start.cycle(HIGH, ready=True, stepping=True)
    assert not start.asking(ready=True)


def test_a_press_held_down_asks_only_once():
    """A finger stays on a button for thousands of cycles. The level is not the
    request; the edge is."""
    start = Start(mode=SINGLE_SHOT)
    press(start)
    assert sum(cycles(start, WAITING, HIGH)) == 1


def test_a_request_outlives_the_wait_for_a_step():
    """The search hears a request only on a step of the conversion clock, and
    at the slowest rate those are two hundred and fifty six cycles apart."""
    start = Start(mode=SINGLE_SHOT)
    press(start, stepping=False)
    assert all(cycles(start, WAITING, HIGH, stepping=False))
    assert start.asking(ready=True)


def test_a_request_outlives_a_conversion_in_flight():
    """Pressing while the part is busy is asking for the next one, not a
    mistake to be thrown away."""
    start = Start(mode=SINGLE_SHOT)
    press(start, ready=False)
    cycles(start, WAITING, HIGH, ready=False)
    assert start.asking(ready=True)


def test_a_press_landing_on_the_cycle_a_request_is_served_is_not_lost():
    """Two asks are two conversions. Dropping the second loses a press that was
    really made, and the part then looks like it missed one."""
    start = Start(mode=SINGLE_SHOT)
    # Pressed and released with the clock not stepping, so the first request is
    # still waiting to be heard.
    press(start, stepping=False)
    cycles(start, 1, LOW, stepping=False)
    assert start.asking(ready=True)
    # The second press lands on the very cycle a step serves the first.
    start.cycle(HIGH, ready=True, stepping=True)
    assert start.pending, "the second press was dropped"
    assert start.asking(ready=True)


def test_a_pin_already_high_out_of_reset_is_not_a_press():
    """There was no edge. A part whose button is wired the other way up would
    otherwise convert once at every power-up."""
    assert INITIAL_LEVEL
    start = Start(mode=SINGLE_SHOT)
    assert not any(cycles(start, WAITING, HIGH))


def test_a_press_in_continuous_mode_is_not_remembered():
    """Moving the jumper is not a request, so a part converting continuously
    does not fire one more conversion the moment it is made single-shot."""
    start = Start()
    for _ in range(BOUNCES):
        press(start)
    start.mode = SINGLE_SHOT
    assert not any(cycles(start, WAITING, HIGH))


def test_moving_the_jumper_with_the_pin_low_leaves_nothing_pending():
    start = Start()
    cycles(start, WAITING, LOW)
    start.mode = SINGLE_SHOT
    assert not any(cycles(start, WAITING, LOW))


def test_a_mode_it_cannot_be_in_is_refused_on_a_cycle_too():
    """The mode is read from a pin every cycle, so it is checked every cycle
    rather than only where the model was built."""
    start = Start()
    start.mode = "once_an_hour"
    with pytest.raises(ValueError):
        start.cycle(LOW, ready=True, stepping=True)
