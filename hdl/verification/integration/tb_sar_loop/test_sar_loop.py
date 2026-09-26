"""The converter with its loop closed: the RTL controller running the analog
block, every trial word chosen from the block's own last answer.

Expectations come from the golden model. Most tests run the block ideal --
ideal switches, a behavioural comparator -- because what is under test is the
loop: the controller's decisions, the boundary between the halves, and the
timing the controller imposes on the block. The last run it as designed, with
transistor switches and the phase generator, and hold it to the error budget
a converter has to meet once its offset is calibrated out.
"""

from __future__ import annotations

import math
import shutil
from dataclasses import replace

import pytest

import analog
import bench
import cosim
import loop
import ngspice
from bench import EDGE, READ_BEFORE_END, Bench, Phase, Supplies
from interface import N_BITS
from protocol import SAMPLE, conversion_sequence
from sar import VCM_FRACTION, ideal_units, sar_convert, top_plate_voltage
from settling import settle_time
from sweep import EDGE_OFFSET_LSB, VDD, VREF, carry_codes, either_side, lsb
from tb_common import rtl
from tb_common.runner import BUILD_DIR

pytestmark = pytest.mark.skipif(
    shutil.which("ngspice") is None or not cosim.available(),
    reason="needs ngspice, verilator and the element glue ngspice installs",
)

DUT = "sar_fsm"

#: A resolution small enough to try every threshold it has.
SMALL = 4

SUPPLIES = Supplies(vdd=VDD, vref=VREF)

#: How far below the model's lowest top-plate voltage a conversion's may dip,
#: in volts. It covers only the instant within an edge when some bottom plates
#: have switched and others not; a word that passes through all-ground on the
#: way from sampling to the first trial dips by the input itself.
LOW_TOLERANCE = 0.01 * VREF

#: The pin's time constant in the settling test, well above the edges, and
#: the resistance that gives it at the target resolution's array.
TAU = 10 * EDGE
C_TOTAL = 2**N_BITS * analog.DEFAULT_UNIT.farads
R_VIN = TAU / C_TOTAL

#: The loop must convert at a clock this many times the law's sampling time,
#: and must fail at this fraction of it -- the failure is what proves the
#: sample the controller gives is one clock long, and the test can see it.
PASS_MARGIN = 1.0
FAIL_FRACTION = 0.5


@pytest.fixture(scope="module")
def controller():
    """The controller compiled at a resolution, once per resolution."""
    built: dict[int, cosim.Library] = {}

    def at(n_bits: int) -> cosim.Library:
        if n_bits not in built:
            workdir = BUILD_DIR / "cosim" / f"{DUT}_{n_bits}"
            built[n_bits] = cosim.build(rtl(DUT)[0], workdir, {"N_BITS": n_bits})
        return built[n_bits]

    return at


def codes(inputs, n_bits: int) -> list[int]:
    units = ideal_units(n_bits)
    return [sar_convert(vin, units, VREF)[0] for vin in inputs]


def lowest(vin: float, n_bits: int) -> float:
    """The model's lowest top plate from the end of sampling to the result."""
    units = ideal_units(n_bits)
    return min(
        top_plate_voltage(vin, s.dac_b, units, VREF)
        for s in conversion_sequence(vin, units, VREF)
        if s.phase != SAMPLE
    )


def disagreements(inputs, got, want, n_bits: int) -> list[str]:
    return [
        f"vin={vin / lsb(n_bits):.3f} LSB: loop {g} model {w}"
        for vin, g, w in zip(inputs, got, want, strict=True)
        if g != w
    ]


@pytest.fixture(scope="module")
def carries(controller, tmp_path_factory):
    """Both sides of every carry at the target resolution, where the most
    bits change at once."""
    inputs = either_side(carry_codes(N_BITS), N_BITS)
    got = loop.convert(
        inputs, controller(N_BITS), tmp_path_factory.mktemp("carries"), supplies=SUPPLIES
    )
    return inputs, got


def test_every_threshold_converts_at_a_small_resolution(controller, tmp_path):
    inputs = either_side(range(1, 2**SMALL), SMALL)
    got = loop.convert(inputs, controller(SMALL), tmp_path, supplies=SUPPLIES, n_bits=SMALL)
    assert not disagreements(inputs, got.codes, codes(inputs, SMALL), SMALL)


def test_every_carry_converts_at_the_target_resolution(carries):
    inputs, got = carries
    assert not disagreements(inputs, got.codes, codes(inputs, N_BITS), N_BITS)


def test_a_resolved_latch_never_raises_the_flag(carries):
    _, got = carries
    assert not any(got.flags)


def test_sampling_hands_straight_over_to_the_first_trial(carries):
    """The controller's side of the top plate's contract: from sampling to the
    first trial word with nothing between. Through all-ground instead, the top
    plate would fall to Vcm minus the input, and on these inputs that is far
    below anywhere a conversion goes."""
    inputs, got = carries
    vcm = VCM_FRACTION * VREF
    floor = [lowest(vin, N_BITS) - LOW_TOLERANCE for vin in inputs]
    assert any(vcm - vin < f for vin, f in zip(inputs, floor, strict=True))
    below = [
        f"vin={vin / lsb(N_BITS):.3f} LSB: {low:.4f} V, model {f + LOW_TOLERANCE:.4f} V"
        for vin, low, f in zip(inputs, got.lows, floor, strict=True)
        if low < f
    ]
    assert not below


def converts_at(controller, workdir, clock: float) -> bool:
    inputs = either_side(carry_codes(N_BITS), N_BITS)
    got = loop.convert(
        inputs, controller(N_BITS), workdir, supplies=SUPPLIES, r_vin=R_VIN, clock=clock
    )
    return not disagreements(inputs, got.codes, codes(inputs, N_BITS), N_BITS)


def test_a_clock_the_pin_law_allows_converts_and_a_faster_one_does_not(controller, tmp_path):
    """The controller samples for one clock: the pin law, solved for the
    sweep's own criterion, is the shortest clock the loop may run at."""
    needed = settle_time(TAU, VREF, EDGE_OFFSET_LSB * lsb(N_BITS))
    assert converts_at(controller, tmp_path, PASS_MARGIN * needed)
    assert not converts_at(controller, tmp_path, FAIL_FRACTION * needed)


#: The block as designed: transistor switches, the phase generator, an array
#: of realistic size.
DESIGNED = analog.NonOverlap()
UNIT = analog.MIM_SIZED

#: Sample lengths at which the top plate's remaining gap is read, to find its
#: time constant from their ratio: past the generator's start-up, and short
#: enough that the gap is still far above the solver's floor.
GAP_SHORT, GAP_LONG = bench.PHASE, 2 * bench.PHASE

#: Inputs on either side of the kick that sets the top switch's time constant:
#: across most of the range, so the kick is nearly a full-scale one.
KICK_FROM, KICK_TO = 0.1 * VREF, 0.95 * VREF

#: Sampling phases long enough that nothing of the previous state is left, for
#: reading the offset the switches leave.
SETTLED_SAMPLE = 5

#: Where each designed-block input sits: mid-way between two thresholds, so a
#: code is right as long as everything the calibrated converter cannot remove
#: -- sampling error beyond the offset, settling -- stays within half an LSB.
MID_CODE = 0.5


def top_gap(workdir, phase: float, sampling) -> float:
    """What is left between the top plate and Vcm at the end of a sample
    that follows a conversion of another level."""
    b = Bench(
        [Phase(sample=1, vin=KICK_FROM), Phase(vin=KICK_FROM), Phase(sample=1, vin=KICK_TO)],
        SUPPLIES,
        N_BITS,
        unit=UNIT,
        sampling=sampling,
        phase=phase,
        read=[2],
        probes={"m_top": "v(xdut.top)"},
    )
    return abs(ngspice.run(bench.deck(b), workdir)["m_top"][0] - VCM_FRACTION * VREF)


def top_switch_tau(workdir, sampling) -> float:
    """The top switch's time constant against the whole array, from the gap
    it leaves after two sample lengths: their ratio is exp(-difference / tau),
    whatever delay each sample starts with."""
    short, long = (top_gap(workdir, p, sampling) for p in (GAP_SHORT, GAP_LONG))
    return (GAP_LONG - GAP_SHORT) * (1 - READ_BEFORE_END) / math.log(short / long)


def sampling_offset(workdir, sampling) -> float:
    """The top plate against the model at the first trial after a settled
    sample of mid-scale, in volts: the constant a calibration removes."""
    units = ideal_units(N_BITS)
    msb = 1 << (N_BITS - 1)
    vin = VCM_FRACTION * VREF
    b = Bench(
        [Phase(sample=1)] * SETTLED_SAMPLE + [Phase(dac_b=msb)],
        Supplies(vdd=VDD, vref=VREF, vin=vin),
        N_BITS,
        unit=UNIT,
        sampling=sampling,
        read=[SETTLED_SAMPLE],
        probes={"m_top": "v(xdut.top)"},
    )
    got = ngspice.run(bench.deck(b), workdir)["m_top"][0]
    return got - top_plate_voltage(vin, msb, units, VREF)


def designed_block_disagreements(controller, workdir, sampling) -> list[str]:
    """Mid-code inputs on both sides of every carry, converted by the loop at
    the clock the top switch's settling law allows, against the model given
    the block's measured offset."""
    clock = settle_time(top_switch_tau(workdir, sampling), VREF, EDGE_OFFSET_LSB * lsb(N_BITS))
    offset = sampling_offset(workdir, sampling)
    step = lsb(N_BITS)
    inputs = [(k + side * MID_CODE) * step for k in carry_codes(N_BITS) for side in (-1, +1)] + [
        MID_CODE * step
    ]
    got = loop.convert(
        inputs,
        controller(N_BITS),
        workdir,
        supplies=SUPPLIES,
        unit=UNIT,
        sampling=sampling,
        clock=clock,
    )
    units = ideal_units(N_BITS)
    # A top plate that sits high reads as an input that sits low.
    want = [sar_convert(vin, units, VREF, cmp_offset=-offset)[0] for vin in inputs]
    return disagreements(inputs, got.codes, want, N_BITS) + [
        f"vin={vin / step:.3f} LSB: flag raised"
        for vin, f in zip(inputs, got.flags, strict=True)
        if f
    ]


def test_the_designed_block_converts_within_budget_once_its_offset_is_removed(controller, tmp_path):
    """Transistor switches, the phase generator and the real controller,
    clocked as fast as the top switch's settling law allows: every code is the
    model's, the model told only the block's one constant offset."""
    assert not designed_block_disagreements(controller, tmp_path, DESIGNED)


def test_with_an_nmos_alone_for_input_switches_it_does_not(controller, tmp_path):
    """What makes the test above pass: an NMOS input switch bends the error
    near the top of the range, beyond what one offset removes."""
    single = replace(DESIGNED, switches=replace(DESIGNED.switches, w_unit_p=0.0))
    assert designed_block_disagreements(controller, tmp_path, single)
