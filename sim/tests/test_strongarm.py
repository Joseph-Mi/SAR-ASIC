"""The latch as built: that the netlist is the circuit it claims, and that
the bench asks it a fair question.

The structural half runs anywhere, because a crossed pair of outputs or an
input that moves during evaluation is a defect no amount of simulator time
reveals -- it just quietly answers a different question. The circuit half
needs a simulator, and the generic models where it only needs a transistor.
"""

from __future__ import annotations

import dataclasses
import shutil

import numpy as np
import pytest

import ngspice
import sky130
import strongarm
from bench import SKY130_CORNERS
from comparator import noise_for_margin, worst_margin
from devices import Generic, Sky130, pdk_library
from interface import N_BITS
from latch import EXCESS_NOISE
from noise import BOLTZMANN, ROOM
from sar import VCM_FRACTION
from strongarm import (
    DESIGNED_FLAVOUR,
    EVALUATE,
    FIRST_STROBE,
    MOVE_AT,
    READ_AT,
    Drive,
    Sizes,
    around,
)

needs_simulator = pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not on PATH")
needs_pdk = pytest.mark.skipif(not pdk_library().exists(), reason="sky130 model library not found")

VREF, VDD = 1.0, 1.8

#: The common mode this converter holds its top plate to.
VCM = VCM_FRACTION * VREF

#: Half an LSB: the smallest difference the converter ever presents.
HALF_LSB = VREF / 2 ** (N_BITS + 1)

#: A first sizing. Not a result -- it is the geometry every measurement here
#: is taken at, named once so a figure and a test cannot disagree about what
#: was simulated. The input pair is long for matching and the latch short for
#: speed, which is the usual split.
SIZES = Sizes(
    w_in=4.0,
    l_in=0.5,
    w_tail=8.0,
    l_tail=0.5,
    w_latch_n=1.0,
    w_latch_p=2.0,
    l_latch=0.15,
    w_pre=2.0,
    l_pre=0.15,
    c_load=10e-15,
)

#: A strobe period comfortably longer than regeneration and far shorter than
#: the conversion clock, so a decision here is the latch's own speed and not
#: the bench's patience.
PERIOD = 2e-9

#: Differences spanning several LSB either side of a tie, and an even count
#: so none of them *is* the tie. A latch at an exact tie is metastable, so its
#: answer there is whatever asymmetry the solver carries; interpolating a
#: boundary through that point reads the solver rather than the circuit.
SPAN = np.linspace(-4 * HALF_LSB, 4 * HALF_LSB, 16)

#: What counts as separated: most of the way to a rail. A latch that has only
#: begun to diverge has not decided, and reading it as a decision is how a
#: metastable part passes a test.
SEPARATED = 0.9


def test_the_terminals_are_declared_in_the_documented_order():
    header = strongarm.subckt(SIZES, Generic()).splitlines()[0].split()
    assert header[1] == strongarm.NAME
    assert tuple(header[2:]) == strongarm.TERMINALS


def test_the_output_that_rises_is_the_one_whose_input_won():
    """The crossing that makes `outp` mean what it says. The input device that
    conducts harder discharges the node on the other side, so a netlist
    without this reports every decision backwards -- and still looks like a
    working comparator."""
    text = strongarm.subckt(SIZES, Generic())
    pulled = {
        line.split()[2]: line.split()[1] for line in text.splitlines() if line.startswith("Minp")
    }
    assert pulled["inp"] == "xn"


def test_the_integration_nodes_are_precharged_with_the_outputs():
    """Left floating they carry charge from the previous decision into the
    next one, which inside a binary search walks the code rather than adding
    noise to it."""
    text = strongarm.subckt(SIZES, Generic())
    reset = [line.split() for line in text.splitlines() if line.startswith("Mpr")]
    assert {fields[1] for fields in reset} == {"outp", "outn", *strongarm.INTEGRATION}
    assert {fields[2] for fields in reset} == {"clk"}


def test_a_pmos_pair_keeps_the_strobe_sense_the_digital_half_was_given():
    """It needs the opposite gate sense, and pays for it inside rather than
    asking the interface to change with an analog decision."""
    mirrored = strongarm.subckt(dataclasses.replace(SIZES, flavour="p"), Generic())
    assert "Minvp" in mirrored and "Minvn" in mirrored
    tail = next(line for line in mirrored.splitlines() if line.startswith("Mtail"))
    assert tail.split()[2] != "clk"
    assert strongarm.subckt(SIZES, Generic()).count("clk_i") == 0


def test_the_inputs_move_while_the_latch_is_precharging():
    """A latch whose input moves during evaluation decides on a blend of two
    questions, and the blend is indistinguishable from offset."""
    assert 1 + MOVE_AT < FIRST_STROBE


def test_the_decision_is_read_inside_the_evaluate_phase():
    assert FIRST_STROBE < 1 + READ_AT < FIRST_STROBE + EVALUATE


def test_every_strobe_gets_its_own_read():
    drive = Drive(VDD, PERIOD)
    moments = strongarm.read_moments(len(SPAN), drive)
    assert len(moments) == len(SPAN)
    assert np.all(np.diff(moments) == pytest.approx(PERIOD))


def test_a_boundary_is_interpolated_and_not_rounded_to_a_step():
    """Otherwise the finest offset the bench can report is one step of the
    staircase, and a sweep wide enough to bracket a bad part is too coarse to
    measure a good one."""
    steps = np.array([-2e-3, -1e-3, 0.0, 1e-3, 2e-3])
    assert strongarm.boundary(steps, steps - 0.5e-3) == pytest.approx(0.5e-3)


def test_a_staircase_that_never_crosses_is_refused():
    """A boundary reported as the edge of the range it was looked for in is
    indistinguishable from a real one."""
    steps = np.array([-2e-3, -1e-3, 0.0, 1e-3, 2e-3])
    with pytest.raises(ValueError):
        strongarm.boundary(steps, np.ones_like(steps))


@pytest.mark.parametrize(
    "call",
    [
        lambda: dataclasses.replace(SIZES, flavour="x"),
        lambda: dataclasses.replace(SIZES, w_in=0.0),
        lambda: dataclasses.replace(SIZES, l_latch=0.0),
        lambda: dataclasses.replace(SIZES, c_node=-1e-15),
        lambda: Drive(0.0, PERIOD),
        lambda: Drive(VDD, 0.0),
        lambda: strongarm.deck(SIZES, Generic(), [], Drive(VDD, PERIOD)),
        lambda: strongarm.deck(SIZES, Generic(), around(VDD, [VDD]), Drive(VDD, PERIOD)),
        lambda: strongarm.deck(SIZES, Generic(), around(VCM, [0.0]), Drive(VDD, PERIOD), draws=0),
    ],
)
def test_an_impossible_bench_is_refused(call):
    with pytest.raises(ValueError):
        call()


@needs_simulator
def test_a_matched_latch_has_no_offset_at_all(tmp_path):
    """Which is the test of the netlist, not of the circuit: with identical
    devices on both sides the only thing that can displace the boundary is an
    asymmetry someone wrote in."""
    drive = Drive(VDD, PERIOD)
    found = strongarm.separations(tmp_path, SIZES, Generic(), around(VDD / 2, SPAN), drive)[0]
    assert strongarm.boundary(SPAN, found) == pytest.approx(0.0, abs=HALF_LSB / 100)
    assert np.all(np.abs(found) > SEPARATED * VDD)


@needs_simulator
def test_it_separates_a_difference_the_converter_will_present(tmp_path):
    """Half an LSB is the hardest question a binary search asks. Regeneration
    is exponential, so a latch that resolves it at all resolves it to the
    rails."""
    drive = Drive(VDD, PERIOD)
    probe = np.array([-HALF_LSB, HALF_LSB])
    found = strongarm.separations(tmp_path, SIZES, Generic(), around(VDD / 2, probe), drive)[0]
    assert found[0] < -SEPARATED * VDD
    assert found[1] > SEPARATED * VDD


@needs_simulator
def test_the_decision_follows_the_input_and_not_the_previous_decision(tmp_path):
    """The precharge's job, checked the way it fails: ask the latch a run of
    one answer and then the other, and the switch must be clean. Hysteresis
    here is not noise, it is a code that walks."""
    drive = Drive(VDD, PERIOD)
    run = np.array([HALF_LSB] * 3 + [-HALF_LSB] * 3)
    found = strongarm.separations(tmp_path, SIZES, Generic(), around(VDD / 2, run), drive)[0]
    assert np.all(found[:3] > SEPARATED * VDD)
    assert np.all(found[3:] < -SEPARATED * VDD)


@needs_simulator
@needs_pdk
def test_mismatch_moves_the_boundary_and_matched_devices_do_not(tmp_path):
    """What a Monte Carlo pass is for. The PDK's matching terms default to off,
    so a run that forgets to switch them on reports a spread of exactly zero
    and invites the conclusion that the design matches perfectly."""
    drive = Drive(VDD, PERIOD)
    wide = np.linspace(-40e-3, 40e-3, 41)
    asked = around(VDD / 2, wide)
    matched = strongarm.separations(tmp_path, SIZES, Sky130(), asked, drive, draws=2)
    assert strongarm.boundary(wide, matched[0]) == pytest.approx(
        strongarm.boundary(wide, matched[1])
    )
    drawn = strongarm.separations(tmp_path, SIZES, Sky130(), asked, drive, draws=2, mismatch=True)
    assert strongarm.boundary(wide, drawn[0]) != strongarm.boundary(wide, drawn[1])


#: The top plate's whole excursion: the common mode either side of half the
#: reference, which is where the first trial puts it. One comparator input
#: sits at the common mode throughout a conversion and the other is this, so
#: a bias study sweeps one input and pins the other -- sweeping both together
#: asks a question the array never asks.
EXCURSION = np.linspace(VCM - VREF / 2, VCM + VREF / 2, 11)

#: Questions the last trial asks, either side of a tie. The tie itself is left
#: out: no comparator defines it, and including it would be asking for the one
#: answer that is allowed to be either.
PRECISION = VCM + np.array([-8, -4, -2, -1, 1, 2, 4, 8]) * HALF_LSB

#: A strobe short against the conversion clock the settling laws set, so a
#: flavour that decides within it has an order of margin in the real part.
SHORT_PERIOD = 20e-9

#: A strobe about as long as the whole evaluate phase a conversion allows.
#: An assumption rather than a derived figure -- the clock comes from a
#: settling measurement, not from a constant -- and it is deliberately
#: generous: a flavour that still cannot decide given the entire phase is not
#: failing on patience.
LONG_PERIOD = 270e-9


def _decides(found, asked) -> bool:
    return bool((found > 0) == (asked > 0) and abs(found) > SEPARATED * VDD)


@needs_simulator
@needs_pdk
def test_the_flavour_this_design_rejected_cannot_resolve_it(tmp_path):
    """An NMOS pair needs its gates a threshold and a tail's headroom above
    ground, and this design's common mode is well under that, so the pair sits
    in subthreshold and the tail passes almost nothing. It integrates the
    right way -- the sign of the separation is right -- but it never
    regenerates to a logic level, and an output stuck partway is the
    metastable condition the interface carries two wires to detect.

    Sizing does not fix it. The shortfall is gate drive the common mode never
    supplies, so a wider pair and a wider tail are a wider subthreshold
    device. The fixes are a different flavour, a higher common mode, or gain
    ahead of the latch, which is why this is a decision and not a sizing
    sweep."""
    drive = Drive(VDD, LONG_PERIOD)
    levels = [(float(v), VCM) for v in PRECISION]
    found = strongarm.separations(tmp_path, SIZES, Sky130(), levels, drive)[0]
    assert not any(_decides(sep, v - VCM) for sep, v in zip(found, PRECISION, strict=True))


@needs_simulator
@needs_pdk
def test_a_pmos_pair_resolves_half_an_lsb_everywhere_the_top_plate_goes(tmp_path):
    """The other flavour, asked the same way: every precision question either
    side of a tie, and the whole large-signal excursion the early trials put on
    the top plate. Both matter and they are different questions -- the early
    trials ask for hundreds of millivolts from a badly biased input, and the
    last one asks for half an LSB from a comfortable one."""
    drive = Drive(VDD, SHORT_PERIOD)
    sizes = dataclasses.replace(SIZES, flavour=DESIGNED_FLAVOUR)
    for plate in (PRECISION, EXCURSION):
        asked = [v - VCM for v in plate]
        levels = [(float(v), VCM) for v in plate]
        found = strongarm.separations(tmp_path, sizes, Sky130(), levels, drive)[0]
        for sep, want in zip(found, asked, strict=True):
            if want == 0.0:
                continue
            assert _decides(sep, want), f"{want * 1e3:+.3f} mV read as {sep:+.3f} V"


def test_the_flavour_the_measurements_chose_is_the_one_declared():
    """So that the reasoning above and the circuit the rest of the project
    builds cannot drift apart: the pair that passes is the pair declared."""
    assert DESIGNED_FLAVOUR == "p"
    assert DESIGNED_FLAVOUR in strongarm.FLAVOURS


#: Sigmas of comparator noise the converter's worst margin must hold.
SIGMAS = 4.0

#: The noise this converter asks of its comparator, and the product of
#: transconductance and time that delivers it. A measurement of this circuit
#: yields the product; the volts follow from it only once an excess noise
#: factor is assumed, so the assertion is made where the measurement is.
TARGET = noise_for_margin(worst_margin(N_BITS, VREF), SIGMAS)
REQUIRED_CHARGE = 4.0 * BOLTZMANN * ROOM * EXCESS_NOISE / TARGET**2

#: A strobe no corner's integration outlives. Slow cold silicon turns over at
#: nearly 300 ns against tens of nanoseconds everywhere else, because the
#: tail's gate drive is the reference less a threshold and a cold slow
#: threshold takes most of it. One constant rather than a strobe per corner,
#: for two reasons: the strobe belongs to the measurement and not to the
#: corner, so a table of them is a second place for a corner fact to be
#: wrong; and a strobe longer than it needs to be cannot move the answer,
#: because the integration ends where the cross-coupled pair takes over,
#: which is the circuit's moment rather than the window's. It costs solver
#: time at the four corners that do not need it, and that is the trade.
CORNER_STROBE = 1e-6


@needs_simulator
@needs_pdk
@pytest.mark.parametrize("corner", SKY130_CORNERS, ids=lambda c: f"{c[0]}{c[2]:g}")
def test_the_noise_the_converter_asked_for_survives_every_corner(corner, tmp_path):
    """The latch converts a difference to charge on its integration nodes,
    and what it costs in noise is set by how much charge: transconductance
    times integration time is a capacitance, and the input noise is that
    capacitance's kT/C. So the corner that matters is wherever that product
    is smallest, which is not the corner the sampling is slowest at -- a
    slower process lowers the transconductance and lengthens the integration
    at once, and the two do not cancel by arrangement.
    """
    process, supply, temp = corner.process, corner.vdd, corner.temp
    measured = strongarm.integration(
        tmp_path,
        strongarm.DESIGNED,
        Sky130(process),
        Drive(supply, CORNER_STROBE, temp),
        VCM,
    )
    assert measured.charge > REQUIRED_CHARGE, (
        f"{process} {supply:g} V {temp:g} C: gm*t_int {measured.charge * 1e12:.3f} pF "
        f"against the {REQUIRED_CHARGE * 1e12:.3f} pF this converter needs"
    )


#: The evaluate phase a conversion gives the latch. The same assumption
#: `LONG_PERIOD` makes and for the same reason -- the clock comes from a
#: settling measurement rather than from a constant -- and deliberately the
#: generous end of it, so a corner that misses it is not failing on patience.
DECISION_PHASE = LONG_PERIOD

#: The corner whose decision does not fit that phase: slow silicon at -40 C,
#: outside the range this part is specified over. Named so the expectation
#: below is a pinned finding and not a corner quietly left out of a loop.
UNRESOLVED = ("ss", -40)


def _resolved(separation: float, asked: float, supply: float) -> bool:
    """Whether a strobe ended with an answer, at this corner's own supply.

    `_decides` asks the same question against the nominal supply, which at a
    low-supply corner is the whole of that corner's swing: a latch there
    cannot pass it however well it resolves.
    """
    return bool((separation > 0) == (asked > 0) and abs(separation) > SEPARATED * supply)


@needs_simulator
@needs_pdk
@pytest.mark.parametrize("corner", SKY130_CORNERS, ids=lambda c: f"{c[0]}{c[2]:g}")
def test_the_decision_arrives_inside_the_phase_except_where_it_is_known_not_to(corner, tmp_path):
    """The other axis of the corner question, and the one the noise
    measurement above cannot see: it hands the latch a strobe several times
    the conversion clock, so it says how quiet a decision is and nothing
    about whether it arrives in time. Asked inside the phase a conversion
    actually allows, the answer is the opposite way round -- the corner with
    the most noise margin is the one that does not answer, because both
    figures are the same tail current read twice.

    Slow cold silicon is pinned as failing rather than left out. It is a
    documented limit of a tail biased from the reference, the reason the part
    is specified at room temperature, and if it ever stops being a limit the
    decision that accepted it is the thing to revisit -- which a test that
    skipped the corner would never say.
    """
    process, supply, temp = corner.process, corner.vdd, corner.temp
    asked = (HALF_LSB, -HALF_LSB)
    found = strongarm.separations(
        tmp_path,
        strongarm.DESIGNED,
        Sky130(process),
        around(VCM, asked),
        Drive(supply, DECISION_PHASE, temp),
    )[0]
    decided = [_resolved(sep, want, supply) for sep, want in zip(found, asked, strict=True)]
    where = f"{process} {supply:g} V {temp:g} C"
    if (process, temp) == UNRESOLVED:
        assert not any(decided), (
            f"{where} now resolves inside the phase: the part is specified at room "
            f"temperature because it did not, so that decision is now the stale one"
        )
    else:
        assert all(decided), f"{where}: {found[0]:+.3f} V and {found[1]:+.3f} V, not resolved"


#: Gate parameters of one input device, which is what the top plate sees of
#: the comparator: the whole gate, and the two halves a datasheet would split
#: it into. Read from the device the simulator builds rather than computed,
#: for the reason every other process number here is.
GATE = ("cgg", "cgs", "cgd")

#: How much of the array's swing the comparator must be left. The parasitic
#: on the top plate divides the excursion down and multiplies every
#: input-referred figure -- offset, noise, hysteresis -- by the inverse, so
#: this is a comparator-budget bound and not a linearity one (M3 Step 1).
SWING_FLOOR = 0.99


def _input_capacitance(workdir, clk: float) -> float:
    """What one input device's gate presents, farads, at that strobe level.

    An operating point and not a transient: the question is what sits on the
    node while the array settles, and the latch is at rest for all of that.
    """
    sizes, devices = strongarm.DESIGNED, Sky130()
    probes = [devices.probe(f"x{strongarm.NAME}", "inn", p, sizes.flavour) for p in GATE]
    deck = "\n".join(
        [
            f"* {strongarm.NAME}: what the top plate sees of the comparator",
            *devices.header(),
            *devices.models(),
            strongarm.subckt(sizes, devices),
            f"Vdd vdd 0 {VDD:g}",
            f"Vref vref 0 {VREF:g}",
            f"Vclk clk 0 {clk:g}",
            f"Vinp inp 0 {VCM:g}",
            f"Vinn inn 0 {VCM:g}",
            f"X{strongarm.NAME} vdd 0 vref clk inp inn outp outn {strongarm.NAME}",
            f".save {' '.join(probes)}",
            ".control",
            "set nomodcheck",
            "op",
            # Named before it is printed: a probe is spelled with brackets and
            # dots, and what reads a run's output here keys results by a
            # plain word, so printing the probe directly produces a line it
            # cannot see and a run that looks like it returned nothing.
            *(f"let {name} = {probe}" for name, probe in zip(GATE, probes, strict=True)),
            *(f"print {name}" for name in GATE),
            ".endc",
            ".end",
            "",
        ]
    )
    return ngspice.run(deck, workdir)[GATE[0]][0]


@needs_simulator
@needs_pdk
@pytest.mark.parametrize("clk", (0.0, VDD))
def test_the_comparator_leaves_the_array_its_swing_at_any_unit_size(clk, tmp_path):
    """What `studies/unit_study.py` does not count, counted here.

    That study reports the top plate's parasitic as the top switch's own
    diffusion, because that is the part which moves with the size being
    chosen. The comparator's input does not move with it -- so as the array
    shrinks it becomes a larger fraction of it, and it is the one thing that
    could argue against drawing a smaller unit. It does not: at the smallest
    unit the process will draw, the input still leaves the comparator
    essentially the whole swing.

    Measured at both strobe levels because the gate a latch presents is not
    the same while it precharges as while it regenerates, and the array
    settles against whichever is larger.
    """
    gate = _input_capacitance(tmp_path, clk)
    assert gate > 0.0, "the input device presents no gate at all, which is a broken probe"
    smallest = 2**N_BITS * sky130.mim_capacitance(sky130.MIM_WIDTH_MIN, sky130.MIM_WIDTH_MIN)
    assert smallest / (smallest + gate) > SWING_FLOOR, (
        f"{gate * 1e15:.3f} fF of gate on a {smallest * 1e12:.3f} pF array"
    )
