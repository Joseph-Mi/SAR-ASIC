"""Finite resistance: the circuit settles the way the settling law says, and a
phase shorter than the law demands breaks conversions it should not.

Each test turns on one resistance and leaves the rest ideal, so a result can be
pinned on it. Time constants are measured without knowing a node's starting
point: read the gap to the final value after two different phase lengths, and
the ratio of the two gaps is exp(-difference / tau).

The resistances are illustrative: each is chosen so its path's time constant
is `TAU`, well above the bench's edges and well inside a run. The law under
test does not depend on them. The design's own values -- the pin's from the TinyTapeout
analog spec, the switches' from a sized device -- go through the same law.
"""

from __future__ import annotations

import math
import shutil

import pytest

import analog
import bench
import ngspice
from bench import Bench, Phase, Supplies
from interface import N_BITS
from sar import ideal_units, top_plate_voltage
from settling import c_seen_by_reference, residual, settle_time
from sweep import (
    EDGE_OFFSET_LSB,
    VDD,
    VREF,
    carry_codes,
    convert,
    either_side,
    lsb,
    mismatches,
    model,
)

pytestmark = pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not on PATH")

UNIT = analog.DEFAULT_UNIT.farads
C_TOTAL = 2**N_BITS * UNIT

#: Every path's time constant in these tests. Ten times the bench's edge, so an
#: edge is a sliver of any phase a measurement uses.
TAU = 10 * bench.EDGE

C_REFERENCE = c_seen_by_reference(C_TOTAL / 2, C_TOTAL)

R_VIN = TAU / C_TOTAL
R_VREF = TAU / C_REFERENCE
R_TOP = TAU / C_TOTAL
R_UNIT_SWITCH = TAU / UNIT

#: Two phase lengths, in multiples of the expected time constant, for reading
#: tau off the ratio of what is left. Far enough apart that the ratio is large,
#: short enough that what is left is still far above the solver's floor.
SHORT, LONG = 2.0, 5.0

#: How closely a measured time constant or residual must match the law. What
#: the bench's timing takes out of each phase is accounted for exactly (see
#: `settled_for`), so this covers only the solver.
TAU_TOLERANCE = 0.01

#: The sweep with a phase this many times the law's settling time must pass,
#: and with this fraction of it must fail. The law is conservative -- it
#: assumes a full-reference step, and the worst real step is smaller -- so the
#: design holds from about two-thirds of it. Half of it fails with a comparator
#: that decides on the strobe's edge, and passes with one that keeps looking
#: through the evaluate phase and so gets twice the settling: the failure is
#: what proves the decision is taken on the edge.
PASS_MARGIN = 1.0
FAIL_FRACTION = 0.5

VIN_FROM, VIN_TO = 0.2 * VREF, 0.7 * VREF


def settled_for(phase: float) -> float:
    """How long a node has settled when a phase's read is taken.

    Less than the phase: the read comes a fraction of it early, and the step
    that started the settling ramps over an edge, which on average starts it
    half an edge late.
    """
    return phase * (1 - bench.READ_BEFORE_END) - bench.EDGE / 2


def tau_from_gaps(gap_short: float, gap_long: float, phase_short: float, phase_long: float):
    """Time constant from what is left after two phase lengths."""
    return (settled_for(phase_long) - settled_for(phase_short)) / math.log(gap_short / gap_long)


def read(b: Bench, probe: str, tmp_path) -> list[float]:
    b.probes = {"m_x": probe}
    return ngspice.run(bench.deck(b), tmp_path)["m_x"]


def sampling_gap(tmp_path, phase: float, node: str, **bench_args) -> float:
    """Gap to Vin at the end of a sample that follows a sample of another level."""
    phases = [Phase(sample=1, vin=VIN_FROM), Phase(sample=1, vin=VIN_TO)]
    b = Bench(phases, Supplies(vdd=VDD, vref=VREF), N_BITS, phase=phase, **bench_args)
    return abs(read(b, node, tmp_path)[-1] - VIN_TO)


def test_sampling_through_the_pin_charges_the_whole_array(tmp_path):
    gaps = [sampling_gap(tmp_path, k * TAU, "v(xdut.vs)", r_vin=R_VIN) for k in (SHORT, LONG)]
    measured = tau_from_gaps(*gaps, SHORT * TAU, LONG * TAU)
    assert measured == pytest.approx(R_VIN * C_TOTAL, rel=TAU_TOLERANCE)


def test_the_top_plate_switch_charges_the_whole_array_too(tmp_path):
    """While sampling, the top plate returns to Vcm through its own switch
    after every bottom-plate step, carrying the same charge as the pin."""
    vcm = analog.VCM_FRACTION * VREF
    gaps = []
    for k in (SHORT, LONG):
        phases = [Phase(sample=1, vin=VIN_FROM), Phase(sample=1, vin=VIN_TO)]
        b = Bench(phases, Supplies(vdd=VDD, vref=VREF), N_BITS, phase=k * TAU, ron_top=R_TOP)
        gaps.append(abs(read(b, "v(xdut.top)", tmp_path)[-1] - vcm))
    measured = tau_from_gaps(*gaps, SHORT * TAU, LONG * TAU)
    assert measured == pytest.approx(R_TOP * C_TOTAL, rel=TAU_TOLERANCE)


def test_binary_sized_switches_settle_every_branch_together(tmp_path):
    """Branch k's switch is 2^k units wide for its 2^k units of capacitance,
    so the smallest and the largest branch lag Vin by the same amount -- and
    by the amount one unit's time constant leaves."""
    lsb_node, msb_node = "v(xdut.b0)", f"v(xdut.b{N_BITS - 1})"
    gaps = [
        sampling_gap(tmp_path, SHORT * TAU, node, ron_unit=R_UNIT_SWITCH)
        for node in (lsb_node, msb_node)
    ]
    assert gaps[0] == pytest.approx(gaps[1], rel=TAU_TOLERANCE)
    law = residual(settled_for(SHORT * TAU), R_UNIT_SWITCH * UNIT, VIN_TO - VIN_FROM)
    assert gaps[1] == pytest.approx(law, rel=TAU_TOLERANCE)


def reference_gap(tmp_path, phase: float, vin: float) -> float:
    """Gap to the model's top plate at the end of the first trial."""
    msb = 1 << (N_BITS - 1)
    phases = [Phase(sample=1), Phase(dac_b=msb)]
    b = Bench(phases, Supplies(vdd=VDD, vref=VREF, vin=vin), N_BITS, phase=phase, r_vref=R_VREF)
    final = top_plate_voltage(vin, msb, ideal_units(N_BITS), VREF)
    return abs(read(b, "v(xdut.top)", tmp_path)[-1] - final)


def test_the_first_trial_loads_the_reference_with_a_quarter_of_the_array(tmp_path):
    """Half the array switches to the reference against the other half: the
    reference's pin charges the two in series."""
    gaps = [reference_gap(tmp_path, k * TAU, VIN_FROM) for k in (SHORT, LONG)]
    measured = tau_from_gaps(*gaps, SHORT * TAU, LONG * TAU)
    assert measured == pytest.approx(R_VREF * C_REFERENCE, rel=TAU_TOLERANCE)


def sweep_holds(tmp_path, phase: float, **bench_args) -> bool:
    inputs = either_side(carry_codes(N_BITS), N_BITS)
    got = convert(inputs, N_BITS, tmp_path, phase=phase, **bench_args)
    return not mismatches(inputs, got, model(inputs, N_BITS), N_BITS)


def needed(tau: float) -> float:
    """The law's phase length: a full-reference step closed to the sweep's
    own criterion, the distance its inputs sit from a threshold."""
    return settle_time(tau, VREF, EDGE_OFFSET_LSB * lsb(N_BITS))


def test_a_phase_the_reference_law_allows_converts_and_a_short_one_does_not(tmp_path):
    tau = R_VREF * C_REFERENCE
    assert sweep_holds(tmp_path, PASS_MARGIN * needed(tau), r_vref=R_VREF)
    assert not sweep_holds(tmp_path, FAIL_FRACTION * needed(tau), r_vref=R_VREF)


def test_a_sample_the_pin_law_allows_converts_and_a_short_one_does_not(tmp_path):
    """Too short a sample leaves part of the previous conversion on the array:
    the code depends on the input before."""
    tau = R_VIN * C_TOTAL
    assert sweep_holds(tmp_path, PASS_MARGIN * needed(tau), r_vin=R_VIN)
    assert not sweep_holds(tmp_path, FAIL_FRACTION * needed(tau), r_vin=R_VIN)
