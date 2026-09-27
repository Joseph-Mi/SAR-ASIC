"""Bottom-plate sampling: which switch opens first decides whether charge
injection is an offset or a distortion, and the phase generator guarantees the
order by construction.

The injection tests measure at the decision point -- holding the word the
conversion would end on, where the top plate sits within an LSB of Vcm. That
is where an error changes a code. Away from it the top plate can swing below
ground, where an off switch conducts again (DD-08's contract, confirmed with
real devices); a measurement held there measures that instead.

The unit capacitor here is a realistic size, because injection is switch
charge over array capacitance: with an array too light for its switches every
effect is exaggerated.

Devices are the simulator's own charge-based model, so these run anywhere.
The sky130 corner test needs the PDK.
"""

from __future__ import annotations

import shutil
from dataclasses import replace

import pytest

import analog
import bench
import ngspice
from bench import Bench, Block, Phase, Supplies
from devices import Sky130, pdk_library
from injection import beyond_a_line, referred_to_input
from interface import N_BITS
from measure import first_trial_error
from sar import VCM_FRACTION, ideal_units, sar_convert, top_plate_voltage

pytestmark = pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not on PATH")

VDD = 1.8
VREF = 1.0
LSB = VREF / 2**N_BITS

UNIT = analog.MIM_SIZED

#: Inputs across the range: what varies across these is what no offset
#: correction removes.
INPUTS = tuple(f * VREF for f in (0.1, 0.3, 0.5, 0.7, 0.9))

#: How far each phase is set apart in the experiment, either way.
GAP = 300e-12

#: The order experiment's input switches: one NMOS each. What it shows is one
#: channel's charge landing where the order puts it; a transmission gate's two
#: channels carry opposite charges that partly cancel, which is a separate
#: effect with its own test.
SINGLE = analog.MosSwitches(w_unit_p=0.0)

#: What may vary with the input and still count as an offset, and what a
#: scheme must exceed to count as distortion, in LSB.
OFFSET_LIKE = 0.25
DISTORTING = 0.5

#: How little the top switch's step may vary with the input under the
#: generator, in LSB: it is the same switch at the same voltage every time.
ONE_STEP = 0.01

#: Doubling the top switch doubles its channel, so its offset: this close.
SCALING_TOLERANCE = 0.2

#: The supply and temperature range the generator's order must survive.
SUPPLIES = (0.9 * VDD, VDD, 1.1 * VDD)
NOMINAL_TEMP = 27
TEMPERATURES = (-40, NOMINAL_TEMP, 125)

#: A load on a switch's line -- a long gate wire, say -- far past anything
#: the generator's buffer for that line is sized for, and how much slower that
#: must make the line for the test to be about slowness. The input switches'
#: lines each drive every input switch, so they take a larger load to slow.
SLOWING_LOAD = {"top": 20e-12, "bottom": 200e-12, "bottom_n": 200e-12}
SLOWED_BY = 5.0

#: Phases long enough for a line that slow to finish moving within one.
SLOW_PHASE = 20 * bench.PHASE

#: When the sample edge falls in the order test, and the fractions of the
#: supply at which a line counts as off and as having started to move from
#: high. Off sits just above the off-detector's switching point at its worst
#: sky130 corner, and well below where the top switch, passing Vcm, stops
#: conducting -- the order accuracy depends on. An input switch passing a Vin
#: near ground may still conduct faintly there when conversion begins; the top
#: plate is sealed by then, so that costs the Vin pin a small current, not a
#: code.
EDGE_AT = bench.PHASE
OFF_LEVEL = 0.4
MOVING_LEVEL = 0.9

#: The input switches' PMOS line, mirrored: off above this fraction of the
#: supply, which keeps its gate above the highest input the reference allows
#: at the lowest supply tested, and started moving once it has left ground.
P_OFF_LEVEL = 1 - OFF_LEVEL
P_MOVING_LEVEL = 1 - MOVING_LEVEL

#: Where the conversion switches let go: they read their line as a fraction of
#: the supply and switch on their own hysteresis.
CONVERSION_OFF = analog.SWITCH_VT - analog.SWITCH_VH


def errors(tmp_path, sampling) -> list[float]:
    """The top plate against the model, at the decision point, per input."""
    units = ideal_units(N_BITS)
    out = []
    for vin in INPUTS:
        code, _ = sar_convert(vin, units, VREF)
        b = Bench(
            [Phase(sample=1), Phase(dac_b=code)],
            Block(Supplies(vdd=VDD, vref=VREF, vin=vin), N_BITS, unit=UNIT, sampling=sampling),
            probes={"m_top": "v(xdut.top)"},
        )
        got = ngspice.run(bench.deck(b), tmp_path)["m_top"][-1]
        out.append(got - top_plate_voltage(vin, code, units, VREF))
    return out


def varies(tmp_path, sampling) -> float:
    return referred_to_input(errors(tmp_path, sampling))[1] / LSB


def test_opening_the_top_switch_first_leaves_an_offset(tmp_path):
    assert varies(tmp_path, analog.Gapped(+GAP, switches=SINGLE)) < OFFSET_LIKE


@pytest.mark.parametrize("gap", [0.0, -GAP], ids=["together", "bottoms_first"])
def test_any_other_order_leaves_a_distortion(gap, tmp_path):
    assert varies(tmp_path, analog.Gapped(gap, switches=SINGLE)) > DISTORTING


def test_the_offset_is_the_top_switch_channel(tmp_path):
    """Twice the width, twice the channel, twice the offset: the step that
    stays is the top switch's own."""
    narrow = analog.Gapped(+GAP, switches=SINGLE)
    wide = analog.Gapped(+GAP, switches=replace(SINGLE, w_top=2 * SINGLE.w_top))
    offset = referred_to_input(errors(tmp_path, narrow))[0]
    doubled = referred_to_input(errors(tmp_path, wide))[0]
    assert doubled / offset == pytest.approx(2.0, rel=SCALING_TOLERANCE)


def test_under_the_generator_the_top_switch_leaves_one_step_for_every_input(tmp_path):
    """The generator's whole job for injection: when the top plate seals, the
    only switch that has let go of it is the top switch, at Vcm -- so its step
    is the same whatever the input. Read after the top switch is off and
    before the input switches begin to open."""
    t = crossings(tmp_path, VDD, NOMINAL_TEMP)
    sealed = (t["top_off"] + t["bot_moving"]) / 2
    steps = []
    for vin in INPUTS:
        b = Bench(
            [Phase(sample=1), Phase()],
            Block(
                Supplies(vdd=VDD, vref=VREF, vin=vin),
                N_BITS,
                unit=UNIT,
                sampling=analog.NonOverlap(),
            ),
            probes={},
            read=[],
            extra_control=[f"meas tran step find v(xdut.top) at={sealed:.12g}"],
        )
        steps.append(ngspice.run(bench.deck(b), tmp_path)["step"][0] - VCM_FRACTION * VREF)
    assert referred_to_input(steps)[1] / LSB < ONE_STEP


#: Inputs across the whole range for the linearity test, closer together at
#: the top, where an input switch has the least gate drive.
RANGE = tuple(f * VREF for f in (0.05, 0.1, 0.3, 0.5, 0.7, 0.9, 0.95))

#: How far the sampling error may stray from a straight line across the
#: input range, in LSB: an offset and a gain are calibrated away, a bend is
#: not.
STRAIGHT = 0.1


def first_trial_errors(tmp_path, switches: analog.MosSwitches) -> list[float]:
    """The top plate against the model at the first trial, per input, in LSB."""
    block = Block(
        Supplies(vdd=VDD, vref=VREF),
        N_BITS,
        unit=UNIT,
        sampling=analog.NonOverlap(switches=switches),
    )
    return [first_trial_error(tmp_path, block, vin) / LSB for vin in RANGE]


def test_transmission_gates_leave_the_sampling_error_a_straight_line(tmp_path):
    """What the input switches leave across the whole range is an offset and
    a gain, which calibration removes, and no bend, which it cannot."""
    errors = first_trial_errors(tmp_path, analog.MosSwitches())
    assert beyond_a_line(RANGE, errors) < STRAIGHT


def crossings(
    tmp_path, vdd: float, temp: float, scheme=None, phase=bench.PHASE
) -> dict[str, float]:
    """When each phase line crosses its levels, around one sample-and-back."""
    off, moving = OFF_LEVEL * vdd, MOVING_LEVEL * vdd
    levels = [
        ("top_off", "phi_top", off, "fall", 1),
        ("bot_moving", "phi_bot", moving, "fall", 1),
        ("bot_off", "phi_bot", off, "fall", 1),
        ("cnv_moving", "phi_conv", off, "rise", 1),
        ("cnv_off", "phi_conv", CONVERSION_OFF * vdd, "fall", 1),
        ("bot_on_moving", "phi_bot", off, "rise", 1),
        ("botn_moving", "phi_bot_n", P_MOVING_LEVEL * vdd, "rise", 1),
        ("botn_off", "phi_bot_n", P_OFF_LEVEL * vdd, "rise", 1),
        ("botn_on_moving", "phi_bot_n", P_OFF_LEVEL * vdd, "fall", 1),
    ]
    control = [
        f"meas tran {name} when v(xdut.{node})={level:.6g} {edge}={n}"
        for name, node, level, edge, n in levels
    ]
    scheme = analog.NonOverlap() if scheme is None else scheme
    b = Bench(
        [Phase(sample=1), Phase(), Phase(sample=1)],
        Block(Supplies(vdd=vdd, vref=VREF, vin=0.5 * VREF), N_BITS, unit=UNIT, sampling=scheme),
        probes={},
        read=[],
        phase=phase,
        extra_control=control,
    )
    deck = bench.deck(b)
    if temp != NOMINAL_TEMP:
        deck = deck.replace(".control", f".temp {temp:g}\n.control", 1)
    return {k: v[0] for k, v in ngspice.run(deck, tmp_path).items()}


def assert_ordered(t: dict[str, float]):
    """Each line starts to move only once the one it follows has finished."""
    assert t["top_off"] < t["bot_moving"], "input switches began opening before the top was off"
    assert t["bot_off"] < t["cnv_moving"], "conversion began before the input switches were off"
    assert t["cnv_off"] < t["bot_on_moving"], "sampling began before conversion had stopped"
    assert t["top_off"] < t["botn_moving"], "input PMOS began opening before the top was off"
    assert t["botn_off"] < t["cnv_moving"], "conversion began before the input PMOS was off"
    assert t["cnv_off"] < t["botn_on_moving"], "input PMOS turned on before conversion stopped"


@pytest.mark.parametrize("vdd", SUPPLIES)
@pytest.mark.parametrize("temp", TEMPERATURES)
def test_the_generator_orders_every_edge_across_supply_and_temperature(vdd, temp, tmp_path):
    assert_ordered(crossings(tmp_path, vdd, temp))


@pytest.mark.skipif(not pdk_library().exists(), reason="sky130 model library not found")
@pytest.mark.parametrize("corner", ["tt", "ff", "ss", "fs", "sf"])
def test_the_generator_orders_every_edge_at_every_sky130_corner(corner, tmp_path):
    assert_ordered(
        crossings(tmp_path, VDD, NOMINAL_TEMP, analog.NonOverlap(devices=Sky130(corner)))
    )


@pytest.mark.parametrize("line", ["top", "bottom", "bottom_n"])
def test_the_order_is_kept_however_slow_a_line_is(line, tmp_path):
    """What makes the order hold by construction rather than by a tuned delay:
    load a switch's line until it is many times slower than everything else,
    and whatever must follow it still waits for it."""
    slowed = analog.NonOverlap(**{f"{line}_line_load": SLOWING_LOAD[line]})
    t = crossings(tmp_path, VDD, NOMINAL_TEMP, slowed, phase=SLOW_PHASE)
    nominal = crossings(tmp_path, VDD, NOMINAL_TEMP, phase=SLOW_PHASE)
    first = {"top": "top_off", "bottom": "bot_off", "bottom_n": "botn_off"}[line]
    assert t[first] - SLOW_PHASE > SLOWED_BY * (nominal[first] - SLOW_PHASE)
    assert_ordered(t)
