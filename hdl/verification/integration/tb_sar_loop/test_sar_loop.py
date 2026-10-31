"""The converter with its loop closed: the RTL controller running the analog
block, every trial word chosen from the block's own last answer.

Expectations come from the golden model. Most tests run the block ideal --
ideal switches, a behavioural comparator -- because what is under test is the
loop: the controller's decisions, the boundary between the halves, and the
timing the controller imposes on the block. The last run it as designed, with
transistor switches and the phase generator behind the platform's pins, and
hold it to the error budget a converter has to meet once its offset is
calibrated out: with the generic models, and with sky130's at every corner.
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
import strongarm
from bench import EDGE, SKY130_CORNERS, SLOWEST_SAMPLING, Block, Supplies, at_corner
from devices import Sky130, pdk_library
from interface import N_BITS
from measure import first_trial_error, law_clock
from protocol import SAMPLE, conversion_sequence
from sar import VCM_FRACTION, ideal_units, sar_convert, top_plate_voltage
from settling import settle_time
from sweep import EDGE_OFFSET_LSB, VDD, VREF, carry_codes, either_side, lsb
from tb_common import rtl
from tb_common.runner import BUILD_DIR
from threshold_study import locate

pytestmark = pytest.mark.skipif(
    shutil.which("ngspice") is None or not cosim.available(),
    reason="needs ngspice, verilator and the element glue ngspice installs",
)

DUT = "sar_fsm"

#: A resolution small enough to try every threshold it has.
SMALL = 4

SUPPLIES = Supplies(vdd=VDD, vref=VREF)

#: The block with ideal switches, at the target resolution.
IDEAL = Block(SUPPLIES)

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
    got = loop.convert(inputs, controller(N_BITS), tmp_path_factory.mktemp("carries"), IDEAL)
    return inputs, got


def test_every_threshold_converts_at_a_small_resolution(controller, tmp_path):
    inputs = either_side(range(1, 2**SMALL), SMALL)
    got = loop.convert(inputs, controller(SMALL), tmp_path, replace(IDEAL, n_bits=SMALL))
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


def test_the_controller_reads_nothing_from_the_rail_the_latch_rests_on(controller, tmp_path):
    """Which rail both outputs rest on between strobes is settled by the input
    pair's flavour, not by the interface: an NMOS pair rests them high and a
    PMOS pair rests them low. The controller strobes for a whole cycle and
    captures on the edge that ends it, so it only ever reads a resolved pair
    and converts the same either way. Both rails also read as metastable while
    they rest, which is why resting on one of them cannot raise the flag."""
    inputs = either_side(carry_codes(SMALL), SMALL)
    want = codes(inputs, SMALL)
    runs = {}
    for rail in (True, False):
        block = replace(IDEAL, n_bits=SMALL, precharge_high=rail)
        work = tmp_path / f"rest{rail:d}"
        work.mkdir()
        runs[rail] = loop.convert(inputs, controller(SMALL), work, block)
        assert not disagreements(inputs, runs[rail].codes, want, SMALL)
        assert not any(runs[rail].flags)
    assert runs[True].codes == runs[False].codes


#: A clock long enough for the transistor latch, which integrates for tens
#: of nanoseconds by design and is given one clock of strobe.
LATCH_CLOCK = 200e-9

#: The unit that gives a short array the farads the real one has. What the
#: latch puts back into the top plate is a charge, so what it costs a code is
#: that charge over the whole array: a short array built from the real unit
#: would hand the comparator a node small enough to make the kick tens of
#: times its own share, which is a harder converter than the one being built
#: rather than a smaller one.
SMALL_UNIT = analog.DEFAULT_UNIT.farads * 2 ** (N_BITS - SMALL)


def latch_block():
    """The short array with the designed latch on its floating top plate."""
    return replace(
        IDEAL,
        n_bits=SMALL,
        unit=analog.Ideal(SMALL_UNIT),
        sampling=analog.NonOverlap(devices=Sky130()),
        latch=strongarm.DESIGNED,
    )


def test_the_array_converts_with_the_comparator_it_will_be_built_with(controller, tmp_path):
    """The only arrangement in which the comparator's own input devices meet
    the floating top plate. Every other bench is half the system: an ideal
    source on a comparator input absorbs whatever the latch kicks back into
    it, and a comparator written as a function has nothing to kick with. So
    this is the first bench that can be wrong for a reason the others cannot
    show, which is why it converts the same codes or the pair of them is not
    the converter the model describes.

    Mid-code inputs, as every other run of the designed block uses, and for a
    reason this bench taught: with inputs `EDGE_OFFSET_LSB` from a threshold
    it asserted that the real latch has no offset. Measured, its offset is a
    constant one twentieth of an LSB -- the tolerance itself -- so the
    criterion turned on which side of its own measurement resolution the
    offset fell, and failed codes at one end of the range or the other
    depending on where it was calibrated. An offset is what the part
    calibrates out in the field, and what this bench is for is everything
    that is *not* an offset: a kick that depends on the code, a latch that
    cannot resolve against a floating node, a flag raised. Half an LSB of
    room leaves all three visible and the offset ten times inside.
    """
    block = latch_block()
    step = lsb(SMALL)
    inputs = [(k + side * MID_CODE) * step for k in carry_codes(SMALL) for side in (-1, +1)]
    got = loop.convert(inputs, controller(SMALL), tmp_path, block, LATCH_CLOCK)
    assert not disagreements(inputs, got.codes, codes(inputs, SMALL), SMALL)
    assert not any(got.flags)


#: How a threshold of that pair is located: how far either side of the
#: model's the search starts and how finely it ends, both in LSB. The
#: resolution is the floor under everything measured this way, which is why it
#: is named rather than inlined -- the error below moves by exactly one step
#: across the whole range, so a criterion finer than this reads the grid
#: instead of the circuit.
THRESHOLD_WINDOW = 0.4
THRESHOLD_RESOLUTION = 0.0125

#: What that error may spread by and still be an offset. Measured, it spreads
#: by one step -- which is what a grid contributes on its own, since the two
#: ends of the range can quantise to neighbouring points however constant the
#: error under them is. So the bound is three: one for the grid and room
#: either side of it, because a bound set at the resolution is the mistake
#: this whole measurement exists to document. It is still an order finer than
#: the mid-code bench above, so a gain or a curvature that bench cannot see
#: fails here.
OFFSET_SPREAD = 3 * THRESHOLD_RESOLUTION


def located_thresholds(controller, workdir, block: Block, n_bits: int) -> dict[int, float]:
    """Where every code transition of this block actually sits, in LSB.

    All of them are bisected at once, one conversion per round rather than per
    threshold: what this costs is ngspice runs, and advancing every search
    together makes that the number of rounds instead of their product.
    """
    step = lsb(n_bits)
    wanted = list(range(1, 2**n_bits))
    low = {k: (k - THRESHOLD_WINDOW) * step for k in wanted}
    high = {k: (k + THRESHOLD_WINDOW) * step for k in wanted}
    library = controller(n_bits)
    for _ in range(math.ceil(math.log2(2 * THRESHOLD_WINDOW / THRESHOLD_RESOLUTION))):
        mid = {k: (low[k] + high[k]) / 2 for k in wanted}
        got = loop.convert([mid[k] for k in wanted], library, workdir, block, LATCH_CLOCK)
        for k, code in zip(wanted, got.codes, strict=True):
            # At or above the code means the transition is at or below here.
            if code >= k:
                high[k] = mid[k]
            else:
                low[k] = mid[k]
    return {k: (low[k] + high[k]) / 2 / step for k in wanted}


def model_thresholds(n_bits: int) -> dict[int, float]:
    """Where the model puts the same transitions, in LSB, read the way the
    loop's are: the input at which its code first reaches each one."""
    units = ideal_units(n_bits)
    step = lsb(n_bits)
    fine = THRESHOLD_RESOLUTION / 10
    points = int(2 * THRESHOLD_WINDOW / fine) + 1
    found = {}
    for k in range(1, 2**n_bits):
        offsets = (-THRESHOLD_WINDOW + i * fine for i in range(points))
        found[k] = next(k + d for d in offsets if sar_convert((k + d) * step, units, VREF)[0] >= k)
    return found


def test_what_the_latch_adds_is_an_offset_and_not_a_shape(controller, tmp_path):
    """Why the bench above may judge codes at mid-code: what the real latch on
    a floating top plate adds is an offset, and an offset is what the part
    removes in the field.

    This is the measurement that licenses that criterion, kept apart from it
    because the two say different things. That one says the codes are right
    with half an LSB of room; this one says the error inside that room has no
    shape. It locates every threshold of the short loop and holds the spread
    of their errors to the measurement's own resolution -- and holds nothing
    finer, because a criterion under that grid is how the bench above once
    came to assert that this comparator has no offset at all, and then to
    fail on which side of a bisection step the offset it does have fell.
    """
    block = latch_block()
    measured = located_thresholds(controller, tmp_path, block, SMALL)
    model = model_thresholds(SMALL)
    errors = {k: measured[k] - model[k] for k in sorted(measured)}
    shown = " ".join(f"{k}:{e:+.4f}" for k, e in errors.items())
    spread = max(errors.values()) - min(errors.values())
    assert spread <= OFFSET_SPREAD, f"the error has a shape, not an offset: {shown}"
    worst = max(abs(e) for e in errors.values())
    assert worst < MID_CODE / 2, (
        f"the offset is {worst:.4f} LSB, over half the room the bench above leaves: {shown}"
    )


def converts_at(controller, workdir, clock: float) -> bool:
    inputs = either_side(carry_codes(N_BITS), N_BITS)
    got = loop.convert(inputs, controller(N_BITS), workdir, replace(IDEAL, r_vin=R_VIN), clock)
    return not disagreements(inputs, got.codes, codes(inputs, N_BITS), N_BITS)


def test_a_clock_the_pin_law_allows_converts_and_a_faster_one_does_not(controller, tmp_path):
    """The controller samples for one clock: the pin law, solved for the
    sweep's own criterion, is the shortest clock the loop may run at."""
    needed = settle_time(TAU, VREF, EDGE_OFFSET_LSB * lsb(N_BITS))
    assert converts_at(controller, tmp_path, PASS_MARGIN * needed)
    assert not converts_at(controller, tmp_path, FAIL_FRACTION * needed)


#: The designed block's sampling scheme.
DESIGNED = bench.DESIGNED.sampling


def designed(sampling) -> Block:
    """The designed block, sampling as `sampling` says."""
    return replace(bench.DESIGNED, supplies=SUPPLIES, sampling=sampling)


#: Where each designed-block input sits: mid-way between two thresholds, so a
#: code is right as long as everything the calibrated converter cannot remove
#: -- sampling error beyond the offset, settling -- stays within half an LSB.
#:
#: Mid-way between the *calibrated* thresholds, which is the whole subtlety
#: and was wrong here for a while. The inputs are placed off the ideal grid
#: and then graded against a model shifted by the offset the block was
#: measured to have. That shift is half an LSB at the slow corner, so it
#: moved the model's decision point onto the input: the bench believed it had
#: half an LSB of margin and had 0.02, while the error it grades is 0.055.
#: One code then disagreed, and the pin and the clock each appeared to fix it
#: because either one moves a threshold a few hundredths of an LSB across a
#: window the bench had drawn around itself. Measured thresholds, the same
#: corner: the loop's sit -0.574 to -0.481 LSB off the model's, a span of
#: 0.094, and 0.055 of that survives the calibration. Shifting the inputs by
#: the same offset the model is told about is what restores the margin the
#: constant above is named for.
#:
#: This is the third time this bench family has graded on a margin finer than
#: the thing it measures -- see the sampling open finding, where a criterion
#: of 0.05 LSB *was* the offset it was supposed to be blind to.
MID_CODE = 0.5


def sampling_offset(workdir, block: Block, clock: float) -> float:
    """The top plate's error at mid-scale, in volts, at the clock the loop
    runs at: the constant a calibration removes."""
    return first_trial_error(workdir, block, VCM_FRACTION * VREF, clock)


def straddles(carries, want) -> None:
    """Refuse a bench whose inputs do not sit either side of a threshold.

    Every pair here is meant to be half a code below a carry and half a code
    above it, so the model must answer `k - 1` then `k`. When it answers the
    same code twice the pair is not on a threshold at all and those two
    conversions cannot fail, whatever the circuit does -- and a bench that
    cannot fail still reports a pass.

    It is checked rather than trusted because it has already not been true.
    The generic designed block sits 3.4 LSB low, and at the top of the range
    the model, told that offset, saturated at the last code for every input
    the bench offered it: four conversions agreeing on 1023 because 1023 is
    as high as the number goes. That bench passed for two years of commits
    and passed for nothing.

    Pure arithmetic on the model, so it costs nothing and runs before the
    conversions rather than after -- there is no reason to spend twenty
    minutes of simulation to grade inputs that cannot grade anything.
    """
    pairs = {k: want[2 * i : 2 * i + 2] for i, k in enumerate(carries)}
    vacuous = {k: v for k, v in pairs.items() if len(v) == 2 and v[0] == v[1]}
    if vacuous:
        raise ValueError(
            f"inputs do not straddle their carries: {vacuous} -- the model gives one "
            "code on both sides, so these conversions cannot disagree with it. Either "
            "the pair has fallen off the end of the range (the code saturates) or the "
            "offset has moved the threshold outside the pair."
        )


def designed_block_disagreements(controller, workdir, block: Block, clock=None) -> list[str]:
    """Mid-code inputs on both sides of every carry, converted by the loop
    against the model given the block's measured offset -- at `clock`, or
    when none is given at the clock the block's own sampling loop allows."""
    if clock is None:
        clock = law_clock(workdir, block, EDGE_OFFSET_LSB * lsb(N_BITS))
    offset = sampling_offset(workdir, block, clock)
    step = lsb(N_BITS)
    # Shifted by the offset the model below is told about, so each input is
    # half a code from the threshold it is actually graded against rather
    # than from the ideal one the converter does not have.
    codes = [(k + side * MID_CODE) for k in carry_codes(N_BITS) for side in (-1, +1)]
    inputs = [c * step + offset for c in codes + [MID_CODE]]
    units = ideal_units(N_BITS)
    # A top plate that sits high reads as an input that sits low.
    want = [sar_convert(vin, units, VREF, cmp_offset=-offset)[0] for vin in inputs]
    straddles(carry_codes(N_BITS), want)
    got = loop.convert(inputs, controller(N_BITS), workdir, block, clock)
    return disagreements(inputs, got.codes, want, N_BITS) + [
        f"vin={vin / step:.3f} LSB: flag raised"
        for vin, f in zip(inputs, got.flags, strict=True)
        if f
    ]


#: Codes the generic block's thresholds are located at. None below this
#: lowest one: its offset is 3.4 LSB, so a threshold under about code 4 sits
#: at a negative input, which is outside the range the part is specified over
#: and not a measurement of anything.
GENERIC_CODES = (64, 256, 512, 896, 1023)

#: The highest code the generic block's error is still an offset at. Read off
#: the measurement rather than assumed -- it is flat to 0.03 LSB up to here
#: and bends above it.
GENERIC_LINEAR_TO = 896

#: What a converter's error may be once its offset is removed, in LSB. Half a
#: code, because that is what separates an input from the threshold it is
#: meant to be on the far side of. A budget, not a measurement.
CONVERTER_BUDGET = 0.5

#: Where a code stops existing, in LSB of error between two thresholds. At one
#: LSB the step from one code to the next has closed. Also a property of the
#: converter and not of this run.
CODE_LOST = 1.0


def test_what_the_designed_block_adds_is_an_offset_and_a_bend_at_full_scale(controller, tmp_path):
    """Transistor switches, the phase generator and the real controller, at
    the clock the sampling loop's settling law allows: what the block adds is
    an offset over the range it is linear on, and a bend in the top eighth.

    Shape rather than codes, because this block is a stand-in and not the
    design. Its devices are the simulator's generic models, which exist here
    so the designed-block path runs where the PDK does not; sky130 at every
    corner is what owns code correctness, and does. Holding a stand-in to the
    converter's budget asserts something about a circuit nobody is building.

    What it is, measured by locating its own thresholds: an offset of -3.43
    LSB, flat from code 64 to code 896 within 0.016 LSB either side of
    mid-scale (0.031 end to end), then bending to -2.73 by full scale --
    0.695 LSB that a mid-scale calibration does not remove. The two figures
    are both quoted because the assertion below uses the first and a reader
    comparing against a plot will measure the second. The
    bend is the transmission gate running out of PMOS at the top of the
    range, which Step 4d measured directly in sky130 and which the generic
    models exaggerate: at the slowest sky130 corner the same measurement
    gives 0.055 LSB, thirteen times less.

    Both bounds below are the converter's, not this run's, which is the point
    of writing them as constants with their own reasons. Over the linear
    range the block meets the budget a calibrated converter has to meet with
    thirty-two times the room. At full scale it does not meet that budget at
    all, and what is asserted there is the weaker claim that is nonetheless
    true -- that the bend has not closed a code. It fails if the bend grows
    by half again, which is what makes it a test rather than a note.

    This test used to grade codes, and passed at the top of the range because
    both the loop and the model saturated at 1023: four conversions agreeing
    because 1023 is as high as the number goes. `straddles` now refuses that.
    """
    block = designed(DESIGNED)
    clock = law_clock(tmp_path, block, EDGE_OFFSET_LSB * lsb(N_BITS))
    offset = sampling_offset(tmp_path, block, clock) / lsb(N_BITS)
    found = locate(
        tmp_path,
        block,
        controller(N_BITS),
        clock,
        codes=GENERIC_CODES,
        centre=offset,
    )
    errors = {k: found[k] - k for k in GENERIC_CODES}
    mid = errors[2 ** (N_BITS - 1)]
    shown = " ".join(f"{k}:{e:+.4f}" for k, e in errors.items())

    linear = {k: e - mid for k, e in errors.items() if k <= GENERIC_LINEAR_TO}
    worst = max(abs(e) for e in linear.values())
    assert worst < CONVERTER_BUDGET, (
        f"the block is not an offset where it is meant to be linear: {worst:.4f} LSB "
        f"over codes up to {GENERIC_LINEAR_TO}, against {CONVERTER_BUDGET}. {shown}"
    )

    bend = max(abs(e - mid) for k, e in errors.items() if k > GENERIC_LINEAR_TO)
    assert bend < CODE_LOST, (
        f"the bend at full scale has closed a code: {bend:.4f} LSB against {CODE_LOST}. {shown}"
    )


#: The supply's tolerance either side of nominal.


needs_pdk = pytest.mark.skipif(not pdk_library().exists(), reason="sky130 model library not found")


@pytest.fixture(scope="module")
def sky130_clock(tmp_path_factory):
    """One clock for every corner, as silicon has: the one the slowest
    sampling corner allows."""
    workdir = tmp_path_factory.mktemp("sky130_clock")
    return law_clock(workdir, at_corner(SLOWEST_SAMPLING), EDGE_OFFSET_LSB * lsb(N_BITS))


@needs_pdk
@pytest.mark.parametrize(
    "corner",
    [pytest.param(c) for c in SKY130_CORNERS],
    ids=lambda c: f"{c.process}-{c.vdd:g}V-{c.temp:g}C-{c.caps}C",
)
def test_sky130_devices_convert_within_budget_at_every_corner(
    controller, sky130_clock, corner, tmp_path
):
    """The gate for every switch size: the designed block with the real
    process's devices, behind the platform's pins, converts every carry at
    every corner at the one clock the slowest corner allows, once each
    corner's offset is removed."""
    assert not designed_block_disagreements(controller, tmp_path, at_corner(corner), sky130_clock)
