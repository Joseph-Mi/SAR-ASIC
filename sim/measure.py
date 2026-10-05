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
from sar import VCM_FRACTION, ideal_units, top_plate_voltage
from settling import settle_time

#: Sample lengths at which the top plate's remaining gap is read, to find its
#: time constant from their ratio: past the generator's start-up, and short
#: enough that the gap is still far above the solver's floor.
GAP_SHORT, GAP_LONG = bench.PHASE, 2 * bench.PHASE

#: The inputs either side of the kick that sets the top switch's time constant,
#: as fractions of the reference: across most of the range, so the kick is
#: nearly a full-scale one.
KICK_FROM, KICK_TO = 0.1, 0.95

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


def first_trial_error(
    workdir: pathlib.Path, block: Block, vin: float, phase: float = bench.PHASE
) -> float:
    """The top plate against the model at the first trial after a settled
    sample of `vin`, in volts, read at the end of a trial `phase` long.

    A block behind a reference pin is still recovering from the first trial's
    charge for a while after it starts, so the error read depends on when: to
    learn what the loop sees, read it at the clock the loop runs at.
    """
    units = ideal_units(block.n_bits)
    msb = 1 << (block.n_bits - 1)
    b = Bench(
        [Phase(sample=1)] * SETTLED_SAMPLE + [Phase(dac_b=msb)],
        replace(block, supplies=replace(block.supplies, vin=vin)),
        phase=phase,
        read=[SETTLED_SAMPLE],
        probes={"m_top": "v(xdut.top)"},
    )
    got = ngspice.run(bench.deck(b), workdir)["m_top"][0]
    return got - top_plate_voltage(vin, msb, units, block.supplies.vref)


def top_gap(workdir: pathlib.Path, block: Block, phase: float) -> float:
    """What is left between the top plate and Vcm at the end of a sample of
    length `phase` that follows a conversion of another level."""
    vref = block.supplies.vref
    low, high = KICK_FROM * vref, KICK_TO * vref
    b = Bench(
        [Phase(sample=1, vin=low), Phase(vin=low), Phase(sample=1, vin=high)],
        block,
        phase=phase,
        read=[2],
        probes={"m_top": "v(xdut.top)"},
    )
    return abs(ngspice.run(bench.deck(b), workdir)["m_top"][0] - VCM_FRACTION * vref)


def sampling_tau(workdir: pathlib.Path, block: Block) -> float:
    """The sampling loop's time constant, in seconds: the whole array,
    charged through the top switch and whatever pins the block has."""
    short, long = (top_gap(workdir, block, p) for p in (GAP_SHORT, GAP_LONG))
    if not long < short:
        raise ValueError(
            "the top plate settled to the solver's floor within the shorter sample: "
            "the loop is too fast for these sample lengths to measure"
        )
    return tau_from_gaps(short, long, GAP_SHORT, GAP_LONG)


def law_clock(workdir: pathlib.Path, block: Block, tolerance: float) -> float:
    """The shortest clock sampling allows: a full-reference step closed to
    `tolerance` volts in one sample, which the controller gives one clock."""
    return settle_time(sampling_tau(workdir, block), block.supplies.vref, tolerance)
