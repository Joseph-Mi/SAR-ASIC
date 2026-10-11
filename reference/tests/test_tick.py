"""How often the search steps, and what moving the rate is allowed to disturb.

The rate is the one setting a user is expected to change on a bench, by hand,
while the part is running. So these are the cases that has to survive: the
fastest and slowest the field can ask for, and a change arriving mid-interval.
"""

from __future__ import annotations

import pytest

from registers import BY_NAME, Registers
from tick import DIVISOR_FIELD, MAX_DIVISOR, RESET_DIVISOR, Tick, period

#: Divisors covering both ends of the field and some of the middle. A power of
#: two and its neighbours, because an off-by-one in the counter's reload shows
#: up first where the count rolls over.
DIVISORS = (0, 1, 2, 3, 7, 8, 9, MAX_DIVISOR - 1, MAX_DIVISOR)

#: Intervals to measure before believing they are all the same length.
INTERVALS = 4


def ticks(counter: Tick, cycles: int) -> list[int]:
    """The cycle number of every step in the next `cycles` cycles."""
    return [i for i in range(cycles) if counter.cycle()]


def gaps(counter: Tick, intervals: int) -> list[int]:
    """The length of each of the next `intervals` intervals, the first one
    measured from where the counter is now."""
    lengths = []
    count = 0
    while len(lengths) < intervals:
        count += 1
        if counter.cycle():
            lengths.append(count)
            count = 0
    return lengths


def test_the_period_is_the_divisor_plus_one():
    assert [period(d) for d in DIVISORS] == [d + 1 for d in DIVISORS]


@pytest.mark.parametrize("divisor", DIVISORS)
def test_every_divisor_the_field_can_hold_names_a_rate(divisor):
    assert period(divisor) >= 1


@pytest.mark.parametrize("divisor", (-1, MAX_DIVISOR + 1))
def test_a_divisor_the_field_cannot_hold_is_refused(divisor):
    with pytest.raises(ValueError):
        period(divisor)
    with pytest.raises(ValueError):
        Tick().divide_by(divisor)


def test_it_comes_up_at_the_slowest_rate_the_field_can_ask_for():
    """A converter too slow out of reset still converts; one too fast returns
    codes that are wrong and plausible, which is the worse thing to ship."""
    assert RESET_DIVISOR == MAX_DIVISOR
    assert Tick().divisor == MAX_DIVISOR


def test_the_rate_it_comes_up_at_is_the_one_the_register_comes_up_at():
    """Two counters out of the same reset, one here and one on the chip."""
    assert Tick().divisor == Registers()[DIVISOR_FIELD]


def test_the_divisor_is_as_wide_as_the_field_that_carries_it():
    assert MAX_DIVISOR == BY_NAME[DIVISOR_FIELD].mask


@pytest.mark.parametrize("divisor", DIVISORS)
def test_the_search_advances_once_per_period(divisor):
    counter = Tick(divisor=divisor)
    cycles = period(divisor) * INTERVALS
    assert len(ticks(counter, cycles)) == INTERVALS


@pytest.mark.parametrize("divisor", DIVISORS)
def test_every_interval_is_the_same_length_including_the_first(divisor):
    """The sample phase is one interval and it is the slowest path in the
    design, so an interval short by a cycle is wrong there before anywhere."""
    assert gaps(Tick(divisor=divisor), INTERVALS) == [period(divisor)] * INTERVALS


def test_the_fastest_rate_advances_every_cycle():
    """The degenerate case has to be a rate like any other: it is what a bench
    clocked at the conversion rate itself asks for."""
    assert ticks(Tick(divisor=0), INTERVALS) == list(range(INTERVALS))


def test_a_new_rate_does_not_shorten_the_interval_in_flight():
    """Cutting the interval the array is already settling in is how a change
    made while converting decides a bit the array had not finished moving for."""
    slow, fast = MAX_DIVISOR, 1
    counter = Tick(divisor=slow)
    counter.cycle()
    counter.divide_by(fast)
    assert gaps(counter, 1) == [period(slow) - 1]


def test_a_new_rate_holds_from_the_next_interval():
    slow, fast = MAX_DIVISOR, 3
    counter = Tick(divisor=slow)
    counter.divide_by(fast)
    gaps(counter, 1)
    assert gaps(counter, INTERVALS) == [period(fast)] * INTERVALS


def test_a_rate_that_does_not_change_is_not_a_change():
    """`divide_by` is called every cycle by hardware that cannot tell whether
    the field moved, so saying the same thing twice has to be saying nothing."""
    divisor, spent = 7, 3
    counter = Tick(divisor=divisor)
    for _ in range(spent):
        counter.cycle()
        counter.divide_by(divisor)
    assert gaps(counter, INTERVALS) == [period(divisor) - spent] + [period(divisor)] * (
        INTERVALS - 1
    )
