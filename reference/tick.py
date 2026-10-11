"""The conversion clock: how often the search is allowed to take a step.

The array needs time to settle before the comparator decides, and how much
depends on the board -- the series resistance of the pins, and whatever drives
the reference and the common-mode node. So the rate is a register field rather
than a number fixed at tapeout: the part is clocked at whatever the board
provides, and the search steps at a fraction of it.

It is a clock enable, never a divided clock. A second clock is a second domain,
and every signal crossing between two of them needs a reason to be trusted; one
domain means the configuration side, the result pins and the search all sample
the same edge, and the only thing the divisor changes is which of those edges
the search moves on.

Contract: `cycle` is called once per system-clock cycle and returns whether the
search advances on it. The intervals between the cycles it returns true for are
all the same length, the first one after reset included -- the sample phase is
one such interval and it is the longest path of the lot, charging the whole
array through the input pin where a bit trial charges a quarter of it, so an
interval short by even a cycle is wrong there first.

The counter runs whether a conversion does or not. A request to start therefore
waits up to one interval to be seen, and has to outlive that wait: at the
slowest rate the field can ask for, a request one cycle long is missed on all
but one cycle in two hundred and fifty six.

A new divisor takes effect from the next interval and never shortens the one in
flight. The field that carries it is held until no conversion is running, so a
search never sees its own rate move.
"""

from __future__ import annotations

from dataclasses import dataclass

from registers import BY_NAME

#: The field the divisor arrives in. Its width and reset value are the register
#: map's to state, not this module's -- they are one fact, and the map is where
#: the host reads it.
DIVISOR_FIELD = "clk_div"

#: The widest divisor that can be asked for, and the one the part comes up at.
MAX_DIVISOR = BY_NAME[DIVISOR_FIELD].mask
RESET_DIVISOR = BY_NAME[DIVISOR_FIELD].reset


def period(divisor: int) -> int:
    """System-clock cycles per step of the search.

    The divisor plus one, so every value the field can hold names a usable
    rate: nothing plus one is still a clock, where nothing on its own is not.
    """
    if not 0 <= divisor <= MAX_DIVISOR:
        raise ValueError(f"{divisor} is not a divisor the field can hold")
    return divisor + 1


@dataclass
class Tick:
    """The counter behind the conversion clock."""

    divisor: int = RESET_DIVISOR

    #: Cycles left of the interval in progress. Counting down rather than up
    #: makes the comparison zero whatever the divisor, and the divisor is read
    #: only where the count reloads -- which is what keeps a change out of the
    #: interval it arrived in.
    remaining: int | None = None

    def __post_init__(self) -> None:
        if self.remaining is None:
            self.remaining = period(self.divisor) - 1

    def cycle(self) -> bool:
        """One system-clock cycle, and whether the search advances on it."""
        if self.remaining:
            self.remaining -= 1
            return False
        self.remaining = period(self.divisor) - 1
        return True

    def divide_by(self, divisor: int) -> None:
        """The divisor in force from the next interval onwards."""
        period(divisor)
        self.divisor = divisor
