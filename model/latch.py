"""What sizing a StrongARM latch buys, and what each gain costs.

A StrongARM decides in two stages, and they are not limited by the same
thing. While the strobe is high the tail current discharges the integration
nodes, and the input pair turns the difference it is asked about into a
charge difference on them -- a gain that grows with time. Once those nodes
have fallen far enough the cross-coupled pairs take over and the difference
grows exponentially instead. The first stage sets offset and noise; the
second sets only time, and time is not what binds here.

The one result worth carrying in your head: input-referred noise is
`4kTgamma/(gm*t)`, and the capacitance on the integration node cancels out of
it -- but only until the node's own fall time is substituted for `t`, because
that time is capacitance over current. Put back, the noise goes as the
reciprocal root of the *charge* swung on the node, and the tail current
cancels instead. Current buys speed. Only capacitance, swing and transistor
efficiency buy quiet.

That is why a quiet latch is a large one rather than a hungry one, and why a
preamplifier is the alternative to growing the latch: it supplies gain ahead
of the integration node, so the same node charge refers to a smaller input.

Contract: capacitances in farads, currents in amperes, times in seconds,
voltages in volts, temperatures in kelvin. Every voltage is at the latch's
own terminals, undivided -- the array's division onto those terminals is
applied once, by whoever writes the specification.
"""

from __future__ import annotations

import math

from noise import BOLTZMANN, ROOM
from power import switching_energy

#: How much more thermal noise a channel carries than a resistor of the same
#: conductance. An assumption, not a process fact: it is above the long-channel
#: two thirds for a short device and climbs with field, and the models carry no
#: single number for it. Sweep it rather than trusting it -- noise goes as its
#: root, so a factor of two in it is only a factor of root two in the answer.
EXCESS_NOISE = 1.0


def trip_time(c_node: float, tail_current: float, swing: float) -> float:
    """How long the integration node takes to fall by `swing`, seconds.

    The tail is a current source into a capacitance, so the fall is a ramp
    and this is the ramp's duration. It ends the integration stage: once the
    node has moved this far the cross-coupled devices are on and the latch
    stops integrating, whatever the strobe does afterwards. So it, and not the
    strobe length, is the time the input pair is given.
    """
    if c_node <= 0.0:
        raise ValueError(f"{c_node} F is not an integration node")
    if tail_current <= 0.0:
        raise ValueError(f"{tail_current} A is not a tail current")
    if swing <= 0.0:
        raise ValueError(f"{swing} V is not a swing")
    return c_node * swing / tail_current


def integration_gain(transconductance: float, t_int: float, c_node: float) -> float:
    """What the input pair multiplies its input by before regeneration, V/V.

    A transconductance driving a capacitance for a fixed time, which is a gain
    that grows linearly with the time allowed rather than settling to a
    value. It is what divides every mismatch downstream of the integration
    node when that mismatch is referred to the input.
    """
    if transconductance <= 0.0:
        raise ValueError(f"{transconductance} S is not a transconductance")
    if t_int <= 0.0:
        raise ValueError(f"{t_int} s is not an integration time")
    if c_node <= 0.0:
        raise ValueError(f"{c_node} F is not an integration node")
    return transconductance * t_int / c_node


def input_noise(
    transconductance: float,
    t_int: float,
    excess: float = EXCESS_NOISE,
    temperature: float = ROOM,
) -> float:
    """Input-referred noise of the integration stage, volts rms.

    The input pair's noise current integrates onto the node alongside the
    signal current, and both are divided by the same gain on the way back to
    the input, so the node's capacitance cancels and what is left is the
    charge gain `gm*t`. Written this way it takes a measured transconductance
    and a measured integration time, which is the form to check a circuit
    against.
    """
    if transconductance <= 0.0:
        raise ValueError(f"{transconductance} S is not a transconductance")
    if t_int <= 0.0:
        raise ValueError(f"{t_int} s is not an integration time")
    if excess <= 0.0:
        raise ValueError(f"{excess} is not an excess noise factor")
    if temperature <= 0.0:
        raise ValueError(f"{temperature} K is not a temperature")
    return math.sqrt(4.0 * BOLTZMANN * temperature * excess / (transconductance * t_int))


def input_noise_from_sizing(
    efficiency: float,
    c_node: float,
    swing: float,
    excess: float = EXCESS_NOISE,
    temperature: float = ROOM,
) -> float:
    """The same noise, from what a designer actually chooses, volts rms.

    Substituting the node's own fall time for the integration time removes the
    tail current entirely: a hungrier latch integrates for a shorter time by
    exactly as much as its transconductance rises. What is left is the charge
    swung on the node, `c_node*swing`, and the efficiency `gm/I` with which
    the input pair converts current into transconductance.

    So the three ways to make a latch quieter are a bigger integration node, a
    longer fall on it, and devices run closer to weak inversion. Spending
    current alone is not one of them.
    """
    if efficiency <= 0.0:
        raise ValueError(f"{efficiency} 1/V is not a transconductance efficiency")
    if c_node <= 0.0:
        raise ValueError(f"{c_node} F is not an integration node")
    if swing <= 0.0:
        raise ValueError(f"{swing} V is not a swing")
    if excess <= 0.0:
        raise ValueError(f"{excess} is not an excess noise factor")
    if temperature <= 0.0:
        raise ValueError(f"{temperature} K is not a temperature")
    charge = efficiency * c_node * swing
    return math.sqrt(8.0 * BOLTZMANN * temperature * excess / charge)


def node_for_noise(
    target: float,
    efficiency: float,
    swing: float,
    excess: float = EXCESS_NOISE,
    temperature: float = ROOM,
) -> float:
    """The integration node a noise target asks for, farads.

    The design direction: the converter fixes the margin, the margin fixes the
    noise, and the node follows. It goes as the inverse square of the target,
    so halving the noise asks for four times the node -- and the node is also
    the load the strobe drives and part of what the input pair's own gate
    presents to the array, which is what eventually makes a preamplifier
    cheaper than more latch.
    """
    if target <= 0.0:
        raise ValueError(f"{target} V is not a noise target")
    if efficiency <= 0.0:
        raise ValueError(f"{efficiency} 1/V is not a transconductance efficiency")
    if swing <= 0.0:
        raise ValueError(f"{swing} V is not a swing")
    if excess <= 0.0:
        raise ValueError(f"{excess} is not an excess noise factor")
    if temperature <= 0.0:
        raise ValueError(f"{temperature} K is not a temperature")
    return 8.0 * BOLTZMANN * temperature * excess / (efficiency * swing * target**2)


def preamp_gain_for_noise(target: float, bare: float) -> float:
    """The gain a stage ahead of the latch needs for the latch to stop
    mattering, V/V.

    Noise the preamplifier's own gain divides is the latch's contribution
    alone; the preamplifier then brings its own, which this does not pretend
    to know. So this is a lower bound on the gain, and the honest reading of
    it is how much headroom a preamplifier has to spend on its own noise
    before it has bought nothing.
    """
    if target <= 0.0:
        raise ValueError(f"{target} V is not a noise target")
    if bare <= 0.0:
        raise ValueError(f"{bare} V is not a latch noise")
    return max(1.0, bare / target)


def regeneration_tau(c_load: float, transconductance: float) -> float:
    """The time constant the cross-coupled pair separates with, seconds.

    A positive feedback loop of two transconductances into two equal loads,
    whose difference therefore grows as `e` to the time over this. It sets no
    specification by itself; it is the input to how long a decision takes.
    """
    if c_load <= 0.0:
        raise ValueError(f"{c_load} F is not an output load")
    if transconductance <= 0.0:
        raise ValueError(f"{transconductance} S is not a transconductance")
    return c_load / transconductance


def threshold_sigma(coefficient: float, width: float, length: float) -> float:
    """One device's threshold spread, volts, from its area.

    Pelgrom's law: mismatch is a surface effect averaged over the channel, so
    its spread falls as the root of the area. The coefficient is a process
    figure in volt-micrometres and is not published in a form that can be
    read off a datasheet -- it is measured, through the same netlister the
    benches use, because a device written out by hand without its fingers is a
    different device and matches differently.
    """
    if coefficient <= 0.0:
        raise ValueError(f"{coefficient} V*um is not a mismatch coefficient")
    if width <= 0.0:
        raise ValueError(f"{width} um is not a width")
    if length <= 0.0:
        raise ValueError(f"{length} um is not a length")
    return coefficient / math.sqrt(width * length)


def input_offset(pair_sigma: float, latch_sigma: float, gain: float) -> float:
    """Input-referred offset spread of the whole latch, volts rms.

    Two independent contributions, which is why a latch's offset is not
    simply its input pair's. The input pair's own mismatch arrives undivided.
    Everything past the integration node -- the cross-coupled devices, the
    precharge -- is divided by the gain the integration stage had already
    applied before it, so the same mismatch matters less in a latch that
    integrates for longer.

    Offset is not a budget item for this converter: a constant offset shifts
    every threshold equally and moves no code relative to its neighbours. It
    is here because it decides whether calibration has anything left to
    remove, and because its spread across a wafer is what a yield argument
    needs.
    """
    if pair_sigma < 0.0:
        raise ValueError(f"{pair_sigma} V is not a spread")
    if latch_sigma < 0.0:
        raise ValueError(f"{latch_sigma} V is not a spread")
    if gain <= 0.0:
        raise ValueError(f"{gain} V/V is not a gain")
    return math.hypot(pair_sigma, latch_sigma / gain)


def energy_per_decision(c_node: float, c_load: float, supply: float) -> float:
    """What one strobe costs, joules.

    Every node the latch moves is precharged back to a rail before the next
    decision, so the charge drawn is not recovered and the cost is the usual
    capacitance times the square of the supply. Both integration nodes and
    both outputs move, which is what makes a quiet latch an expensive one:
    the integration node is the term noise is bought with and the term energy
    is paid on.
    """
    if c_node < 0.0:
        raise ValueError(f"{c_node} F is not an integration node")
    if c_load < 0.0:
        raise ValueError(f"{c_load} F is not an output load")
    return switching_energy(c_node + c_load, supply, nodes=2)
