"""Charge injection: what a MOS switch leaves behind when it turns off.

An on switch holds an inversion channel, W * L * Cox * (Vgs - Vth) of charge.
Turning it off, that charge has to leave through the two terminals; roughly
half goes each way, the split set by the impedance either side and how fast
the gate falls. Whatever lands on a node with nothing driving it stays, as a
step of charge over the node's capacitance.

Vgs is the gate drive minus the voltage being switched, so a switch passing
the signal holds a channel that depends on the signal: its step varies with
the input, and a varying step is error no single correction removes. A switch
at a constant voltage leaves the same step every time: an offset. Bottom-plate
sampling is the arrangement that makes the only step that stays on the
floating node come from a switch at a constant voltage.
"""

from __future__ import annotations


def channel_charge(w: float, length: float, cox: float, overdrive: float) -> float:
    """Charge in an on channel, in coulombs; zero when the switch is off."""
    return w * length * cox * max(overdrive, 0.0)


def hold_step(charge: float, c_node: float, share: float = 0.5) -> float:
    """Voltage step a node takes when `share` of a channel's electrons land on it."""
    return -share * charge / c_node


def referred_to_input(steps: list[float]) -> tuple[float, float]:
    """Split a set of per-input steps into the offset and what varies.

    The offset is the mid-point of the spread, removable by one correction;
    the residue is the spread itself, which no single correction removes.
    """
    low, high = min(steps), max(steps)
    return (low + high) / 2, high - low


def beyond_a_line(inputs: list[float], steps: list[float]) -> float:
    """How far a set of per-input steps strays from the straight line through
    its end points: what remains once an offset and a gain correction have
    each done what one number can. A step that varies with the input in
    proportion is a gain error, calibrated away like an offset; only a bend
    is left for the converter's linearity to carry.
    """
    (x0, y0), (x1, y1) = (inputs[0], steps[0]), (inputs[-1], steps[-1])
    slope = (y1 - y0) / (x1 - x0)
    return max(abs(y - (y0 + slope * (x - x0))) for x, y in zip(inputs, steps, strict=True))
