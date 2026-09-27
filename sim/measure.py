"""Measurements the tests make of the block, each defined once.

Contract: every function here runs the block through a bench and returns a
number in the units its name gives -- seconds or volts. Expectations are the
caller's: nothing here asserts.
"""

from __future__ import annotations

import math
import pathlib
from dataclasses import replace

import bench
import ngspice
from bench import Bench, Block, Phase
from sar import ideal_units, top_plate_voltage

#: Sampling phases long enough that nothing of the previous state is left:
#: what remains is what the switches leave, not what they had no time for.
SETTLED_SAMPLE = 5


def settled_for(phase: float) -> float:
    """How long a node has settled when a phase's read is taken.

    Less than the phase: the read comes a fraction of it early, and the step
    that started the settling ramps over an edge, which on average starts it
    half an edge late.
    """
    return phase * (1 - bench.READ_BEFORE_END) - bench.EDGE / 2


def tau_from_gaps(gap_short: float, gap_long: float, phase_short: float, phase_long: float):
    """Time constant from what is left of a step after two phase lengths.

    The ratio of the gaps is exp(-difference / tau), so whatever delay each
    phase spends before the node starts to move cancels out.
    """
    return (settled_for(phase_long) - settled_for(phase_short)) / math.log(gap_short / gap_long)


def first_trial_error(workdir: pathlib.Path, block: Block, vin: float) -> float:
    """The top plate against the model at the first trial after a settled
    sample of `vin`, in volts."""
    units = ideal_units(block.n_bits)
    msb = 1 << (block.n_bits - 1)
    b = Bench(
        [Phase(sample=1)] * SETTLED_SAMPLE + [Phase(dac_b=msb)],
        replace(block, supplies=replace(block.supplies, vin=vin)),
        read=[SETTLED_SAMPLE],
        probes={"m_top": "v(xdut.top)"},
    )
    got = ngspice.run(bench.deck(b), workdir)["m_top"][0]
    return got - top_plate_voltage(vin, msb, units, block.supplies.vref)
