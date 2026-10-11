"""What a board has to meet at the asynchronous pins.

There is one clock domain inside the chip, so nothing here is a flop-to-flop
setup or hold time -- those come from the place and route tools and apply to
paths this module cannot see. What this module declares is the other kind of
timing constraint, the one that exists because four of the pins are driven by
something that does not share the clock: a wire's clock, a chip select, a
button. Those are sampled, and a level that is not held long enough is not
sampled at all.

The requirement follows from one fact about sampling and does not depend on
the synchroniser: a clock edge landing while the pin is in transition takes a
sample that is not reliably either value, so only the edges falling clear of
both of a level's transitions are observations of it. A level one cycle long
offers exactly one edge, and at some phase between the pin and the clock that
one edge is the unreliable one. The synchroniser decides when an observation
becomes safe to use downstream; it does not create one.

Contract: every figure here is in system-clock cycles, and each is a bound a
*board* has to honour, not something the design can enforce. A frame driven
faster than `max_wire_fraction` allows loses bits, and a frame that loses bits
can still land a write -- which is why a host confirms a configuration by
reading it back rather than by trusting the write.
"""

from __future__ import annotations

from itertools import count

#: Flops an asynchronous input passes through before anything may read it. The
#: first is where metastability resolves, so its output is not an observation.
SYNCHRONISER_STAGES = 2

#: Clock edges the design has to catch within one level to register it. An edge
#: detector compares the level against the level before it, so each of the two
#: phases has to be observed once.
EDGES_PER_LEVEL = 1


def edges_guaranteed(level_cycles: int) -> int:
    """Clock edges certain to sample a level held for this long.

    Edges falling clear of both transitions, whatever the phase between the
    pin and the clock. One of the edges a level offers can always be the one
    that lands in a transition, so the guarantee is one fewer than the count a
    lucky alignment would give.

    A simulator cannot show this: it resolves a pin changing on a clock edge
    to a definite value by scheduling order, so below this bound a bench passes
    and the chip does not. That is why the bound is derived here and only
    confirmed, never discovered, in a testbench.
    """
    if level_cycles < 0:
        raise ValueError(f"{level_cycles} is not a duration")
    return max(0, level_cycles - 1)


#: Cycles a level on an asynchronous pin must be held for the design to be
#: certain of registering it: the shortest duration whose guarantee is enough.
MIN_LEVEL_CYCLES = next(n for n in count(1) if edges_guaranteed(n) >= EDGES_PER_LEVEL)


def min_wire_period_cycles() -> int:
    """Shortest period of an external clock the design can follow.

    Both phases have to be registered, and each phase is a level.
    """
    return 2 * MIN_LEVEL_CYCLES


def max_wire_fraction() -> float:
    """Fastest an external clock may run, as a fraction of the system clock."""
    return 1.0 / min_wire_period_cycles()


def latency_cycles() -> int:
    """Cycles from a pin changing to the design having acted on the change.

    The synchroniser's stages, plus the cycle the logic behind it takes to use
    what arrived. What a bench has to wait before reading a consequence.
    """
    return SYNCHRONISER_STAGES + 1


def frame_cycles(data_bytes: int, register_width: int) -> int:
    """Cycles the shortest legal frame of this many data bytes occupies.

    A command byte, then the data, every bit at the fastest wire period the
    bound above allows, with the select line asserted a level either side of
    the bits so its own edges are registered too.
    """
    if data_bytes < 0:
        raise ValueError(f"{data_bytes} is not a number of bytes")
    bits = (1 + data_bytes) * register_width
    return bits * min_wire_period_cycles() + 2 * MIN_LEVEL_CYCLES
