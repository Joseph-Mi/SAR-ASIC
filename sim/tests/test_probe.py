"""Device properties the models do not state, measured and then declared.

Two numbers this project needs are emergent rather than declared: what an off
switch's diffusion presents to the node it sits on, and what a switch's
resistance is at the level it really passes. Both are fitted from the device
the simulator builds and then written into `tech`, so a figure or a budget can
read them without a simulator.

That makes them copies, and these are what stop the copies drifting. The
fitter itself is checked without a simulator at all: a law it cannot recover
from its own curve would make every measurement below meaningless.
"""

from __future__ import annotations

import math
import shutil

import numpy as np
import pytest

import analog
import probe
import sky130
from devices import Sky130, pdk_library
from interface import N_BITS
from metrics import lsb_ideal
from sar import VCM_FRACTION
from settling import sampling_loop_resistance, settle_time
from tinytapeout import R_PIN

pytestmark = [
    pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not on PATH"),
    pytest.mark.skipif(not pdk_library().exists(), reason="sky130 model library not found"),
]

#: The switch whose diffusion sits on the floating top plate.
TOP_WIDTH, LENGTH = sky130.TOP_SWITCH_WIDTH, 0.15

#: The design's reference and supply, volts, and the common mode the top
#: switch passes. The level matters: the gate drive left over and the body
#: effect against it both follow from it, so a resistance quoted at another
#: level is a different number.
VREF, VDD = 1.0, 1.8
VCM = VCM_FRACTION * VREF

#: How closely the declared resistances must hold. Wider than the capacitance
#: fit: a resistance is read at one operating point of a compact model, and
#: the point is set by a supply and a temperature that are themselves choices.
RESISTANCE_ERROR = 0.1

#: Reverse biases to measure across: the whole range the top plate visits,
#: which is the reference either side of the common mode.
BIASES = tuple(VREF * k / 10 for k in range(11))

#: How closely the declared law must follow the device over that range. Not
#: solver noise -- it is the error a three-parameter law leaves on a compact
#: model's curve, and it is quoted so that a worse fit is a failure rather
#: than a surprise.
LAW_ERROR = 0.01

#: How exactly the fitter must recover a law from a curve the law drew.
RECOVERY = 1e-3

#: Widths to check the per-micrometre scaling over. They straddle the width
#: at which the netlister starts splitting a device into fingers, which is
#: where a scaling assumption would break if it were going to.
SCALED_WIDTHS = (2.0, 4.0, 8.0, 16.0)
SCALING_ERROR = 0.03

#: Where an input switch is asked to pass nothing it cannot, and where it is
#: asked to pass the whole reference. The bottom half is the NMOS's work and
#: the top half the PMOS's, so the two ends answer different questions.
EASY_LEVEL, HARD_LEVEL = 0.5, 1.0

#: Fraction of a sampling phase a branch may spend settling. Each branch's
#: switch is scaled with its own capacitance, so every branch shares one time
#: constant and this is the whole of the budget it gets.
BRANCH_BUDGET = 0.5

#: Corners the switch has to work at, as (name, corner, supply, temperature).
#: The supply moves with the corner because a gate drive is what a supply
#: buys, and the slow corner is given the low one.
CORNERS = (
    ("tt", "tt", VDD, 27.0),
    ("ss hot", "ss", 0.9 * VDD, 125.0),
    ("ss cold", "ss", 0.9 * VDD, -40.0),
    ("ff hot", "ff", 1.1 * VDD, 125.0),
    ("ff cold", "ff", 1.1 * VDD, -40.0),
)


def test_the_fitter_recovers_a_law_it_is_given():
    """Checked without a simulator, because everything else here trusts it."""
    want = (3.4e-15, 0.72, 0.31)
    bias = np.linspace(0.0, 1.8, 19)
    curve = want[0] * (1.0 + bias / want[1]) ** -want[2]
    c_zero, potential, grading, error = probe.fit_depletion(bias, curve)
    assert error < RECOVERY
    assert (c_zero, potential, grading) == pytest.approx(want, rel=RECOVERY * 10)


def test_a_curve_through_zero_is_refused():
    with pytest.raises(ValueError):
        probe.fit_depletion([0.0, 1.0], [1e-15, 0.0])


def test_the_declared_diffusion_law_is_the_device(tmp_path):
    """The copy that lets a figure quote a junction without running a
    simulator, held to the device it was fitted to -- over the bias range the
    top plate actually visits, not the range that happened to be measured."""
    measured = probe.diffusion_curve(tmp_path, Sky130(), TOP_WIDTH, LENGTH, BIASES)
    for bias, got in zip(BIASES, measured, strict=True):
        want = sky130.diffusion_capacitance(TOP_WIDTH, bias)
        assert want == pytest.approx(got, rel=LAW_ERROR), f"at {bias:g} V"


def test_the_diffusion_scales_with_width(tmp_path):
    """Which is what makes a per-micrometre constant meaningful. A device wide
    enough to be drawn as fingers has to behave as the whole width, or the
    constant means one thing below the finger limit and another above it."""
    for width in SCALED_WIDTHS:
        got = probe.diffusion_curve(tmp_path, Sky130(), width, LENGTH, [0.0])[0]
        want = sky130.diffusion_capacitance(width)
        assert want == pytest.approx(got, rel=SCALING_ERROR), f"at {width} um"


def test_the_diffusion_on_the_top_plate_is_negligible(tmp_path):
    """The result, and the reason the parasitic study that swept it was asking
    the wrong question. Against the array it sits on, the switch's diffusion
    is a part in a thousand -- so the swing it divides and the settling it
    slows are both below anything the converter can resolve."""
    array = 2**10 * sky130.mim_unit()
    measured = probe.diffusion_curve(tmp_path, Sky130(), TOP_WIDTH, LENGTH, [0.0])[0]
    assert measured / array < 1e-3


def test_the_declared_switch_is_the_one_the_block_builds():
    """The width and the level the resistances are quoted at are a copy of the
    analog block's own, and a resistance quoted for a different switch than
    the one in the circuit is worse than no resistance at all."""
    switches = analog.MosSwitches()
    assert sky130.TOP_SWITCH_WIDTH == switches.w_top
    assert sky130.TOP_SWITCH_PASSES == pytest.approx(VCM)


def test_the_declared_switch_resistance_is_the_device(tmp_path):
    """The other copy a figure reads without a simulator."""
    typical = probe.on_resistance(tmp_path, Sky130("tt"), TOP_WIDTH, LENGTH, VCM, VDD, 27.0)
    assert typical == pytest.approx(sky130.TOP_SWITCH_OHMS["typical"], rel=RESISTANCE_ERROR)
    worst = max(
        probe.on_resistance(tmp_path, Sky130(corner), TOP_WIDTH, LENGTH, VCM, supply, temp)
        for _, corner, supply, temp in CORNERS
    )
    assert worst == pytest.approx(sky130.TOP_SWITCH_OHMS["worst"], rel=RESISTANCE_ERROR)


def test_the_switch_costs_less_than_the_pins_it_is_in_series_with(tmp_path):
    """Why a sampling budget that takes every resistance at the platform's pin
    bound is conservative rather than wrong: the on-chip switch is the
    smallest of the three, at every corner."""
    assert max(sky130.TOP_SWITCH_OHMS.values()) < R_PIN


def test_the_switch_is_slowest_hot_and_not_cold(tmp_path):
    """Which corner a sampling phase is sized at, and it is not the obvious one.

    Cold raises both the mobility and the threshold, and which of them wins
    depends on how much gate drive is left after the level the switch passes.
    This switch passes the common mode with most of a volt to spare, so it is
    not near threshold and mobility decides: the slow corner at the low supply
    and the high temperature is the worst of them.

    A switch passing a higher level would be near threshold and the answer
    would invert, which is why this is measured rather than reasoned about.
    """
    resistance = {
        name: probe.on_resistance(tmp_path, Sky130(corner), TOP_WIDTH, LENGTH, VCM, supply, temp)
        for name, corner, supply, temp in CORNERS
    }
    assert resistance["ss hot"] == max(resistance.values())
    assert resistance["ff cold"] == min(resistance.values())
    assert resistance["ss cold"] < resistance["ss hot"]
    assert all(math.isfinite(r) and r > 0 for r in resistance.values())


def sampling_phase() -> float:
    """How long the design gives a sample, seconds.

    From the settling law and the array, so it moves with the unit capacitor
    rather than being a number written beside it.
    """
    array = 2**N_BITS * sky130.mim_unit()
    tau = sampling_loop_resistance(R_PIN, R_PIN, R_PIN) * array
    return settle_time(tau, VREF, lsb_ideal(N_BITS, VREF) / 2)


def branch_settling(resistance: float) -> float:
    """What a per-unit switch of this resistance costs a branch, seconds.

    Every branch's switch is its unit width times its unit count, so every
    branch sees the same time constant: one unit switch against one unit
    capacitor.
    """
    tau = resistance * sky130.mim_unit()
    return settle_time(tau, VREF, lsb_ideal(N_BITS, VREF) / 2)


def test_the_gate_across_the_input_switch_does_nothing_in_the_bottom_half(tmp_path):
    """Which is the point of a transmission gate, not a defect in it. A PMOS
    whose gate is at ground and whose source is at half the reference has less
    than a threshold across it, so the NMOS is carrying the whole switch --
    and measuring there would say the gate is not needed."""
    switches = analog.MosSwitches()
    nmos, gate = (
        probe.on_resistance(
            tmp_path,
            Sky130("ss"),
            switches.w_unit,
            switches.length,
            EASY_LEVEL,
            0.9 * VDD,
            -40.0,
            width_p=width_p,
        )
        for width_p in (0.0, switches.w_unit_p)
    )
    assert gate == pytest.approx(nmos, rel=1e-3)


def test_an_nmos_alone_cannot_pass_the_top_of_the_range_at_the_slow_corner(tmp_path):
    """The measurement the transmission gate was waiting on.

    An NMOS passing the whole reference keeps barely a threshold of gate drive
    at the slow corner on a low supply, and the body effect takes the rest. It
    does not become slow: it stops conducting, by three orders. The gate
    across it is carrying the top of the range on its own.
    """
    switches = analog.MosSwitches()
    nmos, gate = (
        probe.on_resistance(
            tmp_path,
            Sky130("ss"),
            switches.w_unit,
            switches.length,
            HARD_LEVEL,
            0.9 * VDD,
            -40.0,
            width_p=width_p,
        )
        for width_p in (0.0, switches.w_unit_p)
    )
    assert nmos > 1e3 * gate
    budget = BRANCH_BUDGET * sampling_phase()
    assert branch_settling(nmos) > budget
    assert branch_settling(gate) < budget
