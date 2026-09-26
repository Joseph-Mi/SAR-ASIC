"""How long a node takes to settle, and what it is charging while it does.

Every phase of a conversion ends with a node that has to be within a tolerance
of where it is going: the bottom plates of Vin while sampling, the top plate
after each trial's reference switching. Each is a resistance charging a
capacitance, so each follows one law -- the gap closes by e every time
constant -- and every phase length in the design is that law solved for time.

The textbook form, (N+1) ln 2 time constants, is this law at a full-scale step
and a half-LSB tolerance. It is derived here rather than written down because
both the step and the tolerance move with the question being asked.
"""

from __future__ import annotations

import math


def residual(t: float, tau: float, step: float) -> float:
    """What is left of a `step` after settling for `t` with time constant `tau`."""
    return step * math.exp(-t / tau)


def settle_time(tau: float, step: float, tolerance: float) -> float:
    """Time for a `step` to close to within `tolerance`."""
    return tau * math.log(step / tolerance)


def c_seen_by_reference(c_selected: float, c_total: float) -> float:
    """Capacitance the reference charges when `c_selected` switches to it.

    The top plate floats, so the branches pulled to the reference charge
    through the ones held at ground: the two groups are in series. That is
    zero with nothing or everything selected, and a quarter of the array at
    the first trial, where half of it switches -- the worst load the reference
    ever sees, and the one its pin has to recover from.
    """
    if c_total == 0.0:
        return 0.0
    return c_selected * (c_total - c_selected) / c_total
