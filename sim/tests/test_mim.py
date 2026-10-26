"""The unit capacitor, against the process that has to draw it.

Every absolute number the project quotes -- settling time, charge off the
reference, kT/C -- is the array's capacitance times something, and the array
is the unit times a power of two. So the unit is the one number the whole
budget hangs from, and it is the one most easily written down from memory and
never checked again.

It is therefore not written down. The parameters are declared once from the
PDK and the closed form is the device's own expression; these hold both ends
to the process: the parameters to the files the simulator reads, and the
expression to the device the simulator actually builds.

Which files those are is not obvious. The PDK ships the MiM twice, and the two
do not agree: one carries an area term, a fringe term and a negative metal
bias, the other a larger area term, no fringe at all and a positive bias
several times the size. The library the simulator reads is the authority, and
these tests read the same tree it does.
"""

from __future__ import annotations

import math
import pathlib
import re
import shutil

import pytest

import ngspice
import sky130
from devices import pdk_library

pytestmark = [
    pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not on PATH"),
    pytest.mark.skipif(not pdk_library().exists(), reason="sky130 model library not found"),
]

#: Where the library keeps the parameters it includes, beside itself.
CONTINUOUS = "continuous"

#: The file each capacitance corner's parameters come from.
CORNER_FILES = {
    "low": "parameters_cap_low.spice",
    "typical": "parameters_cap_nom.spice",
    "high": "parameters_cap_high.spice",
}

#: A corner parameter: a nominal value plus a corner term, with the spread the
#: Monte Carlo switches add written after it and switched off by default.
CORNERED = (
    r"\.param\s+{name}\s*=\s*\{{\s*([-\d.eE+]+)\s*\+\s*corner_factor\s*\*\s*([-\d.eE+]+)\s*\}}"
)

#: A plain parameter, as the global model file writes it.
PLAIN = r"^\+?\s*{name}\s*=\s*([-\d.eE+]+)"

#: The device's parameters, and what this project calls each.
AREA, BIAS = "sw_cap_mim_ca", "sw_cap_mim_dw"

#: The matching coefficient, and the file that carries it.
MATCHING, GLOBALS = "sw_mm_cmim", "models_global.spice"

#: Metres per micrometre: the PDK keeps dimensions in metres and the device
#: converts, so the declared bias is converted here too.
PER_MICRON = 1e-6

#: Percent per unit: the matching coefficient is a ratio and the project
#: quotes it as a percentage.
PERCENT = 100.0

#: Library sections to measure, and the capacitance corner each selects. Only
#: the extreme device corners carry a capacitance corner with them; the
#: typical device is offered with the typical capacitance alone.
SECTIONS = {"tt": "typical", "ff_hh": "high", "ss_ll": "low"}

#: Drawn sides to measure, micrometres. The smallest the process draws, and
#: one ten times larger: the bias is a sixth of the first and a sixtieth of
#: the second, so an expression that matches both has the density and the bias
#: each right, rather than a product of two errors.
SMALL = math.sqrt(sky130.CAP_MIN_AREA_MIM)
LARGE = 20.0

#: How closely the closed form must track the device. It is the same
#: arithmetic on the same parameters, so the only difference allowed is the
#: digits the simulator prints.
AGREEMENT = 1e-5

#: Frequency the capacitance is read at. The device is linear, so one is the
#: whole measurement.
PROBE_HZ = 1e6


def continuous() -> pathlib.Path:
    return pdk_library().parent / CONTINUOUS


def cornered(name: str, corner: str) -> float:
    """A corner parameter's value with the corner selected, as the library's
    own sections select it."""
    text = (continuous() / CORNER_FILES[corner]).read_text()
    found = re.search(CORNERED.format(name=name), text)
    assert found, f"{name} is not declared at the {corner} corner"
    return float(found.group(1)) + float(found.group(2))


def measured(workdir: pathlib.Path, side: float, section: str) -> float:
    """What the simulator gives for the real device, farads.

    One volt across a capacitor draws a current of omega times its
    capacitance, and nothing here is nonlinear.
    """
    deck = "\n".join(
        [
            # The first line of a deck is its title, and ngspice reads it as
            # one whatever it says. A directive left there is a directive the
            # simulator never sees, and the record of a run names a deck by it.
            f"* one {side:g} um device, {section}",
            f".lib {pdk_library()} {section}",
            f"X1 a 0 {sky130.MIM} w={side:.6g} l={side:.6g}",
            "V1 a 0 dc 0 ac 1",
            ".control",
            "set nomodcheck",
            f"ac lin 1 {PROBE_HZ:g} {PROBE_HZ:g}",
            f"let c = abs(i(V1))/(2*pi*{PROBE_HZ:g})",
            "print c",
            ".endc",
            ".end",
            "",
        ]
    )
    return ngspice.run(deck, workdir)["c"][0]


@pytest.mark.parametrize("corner", sky130.CAP_CORNERS)
def test_the_declared_density_is_the_pdks(corner):
    assert sky130.CAP_MIM_AREA[corner] == pytest.approx(cornered(AREA, corner))


@pytest.mark.parametrize("corner", sky130.CAP_CORNERS)
def test_the_declared_bias_is_the_pdks(corner):
    """The plate runs past the shape that was drawn, and by enough to matter:
    this is the term that makes the smallest unit a sixth larger than its
    drawn area says."""
    assert sky130.CAP_MIM_BIAS[corner] == pytest.approx(cornered(BIAS, corner) / PER_MICRON)


def test_the_declared_matching_coefficient_is_the_pdks():
    """The coefficient every yield number rests on, read from the tree the
    simulator uses. The other tree in the PDK carries a different one, and a
    recipe that greps for the name alone finds whichever it reaches first."""
    text = (continuous() / GLOBALS).read_text()
    found = re.search(PLAIN.format(name=MATCHING), text, re.M)
    assert found, f"{MATCHING} is not declared in {GLOBALS}"
    assert sky130.CAP_A_C == pytest.approx(float(found.group(1)) * PERCENT)


@pytest.mark.parametrize("section,corner", sorted(SECTIONS.items()))
@pytest.mark.parametrize("side", (SMALL, LARGE))
def test_the_closed_form_is_the_device_the_simulator_builds(tmp_path, section, corner, side):
    """The check that matters. Every figure and every budget reads the closed
    form, because a figure cannot run a simulator -- so the closed form has to
    be the capacitor the simulator would have built."""
    want = sky130.mim_capacitance(side, side, corner)
    got = measured(tmp_path, side, section)
    assert got == pytest.approx(want, rel=AGREEMENT), (
        f"{side} um at {corner}: the closed form says {want:.6e} F, the device is {got:.6e} F"
    )


def test_the_drawn_area_alone_is_not_the_unit(tmp_path):
    """Why the bias is carried at all. At the smallest unit the process draws,
    area times density is wrong by more than a tenth -- an error that would
    land in every absolute figure the project quotes."""
    area_only = sky130.CAP_MIM_AREA["typical"] * sky130.CAP_MIN_AREA_MIM
    assert sky130.mim_unit() > area_only * 1.1
    assert measured(tmp_path, SMALL, "tt") > area_only * 1.1


def test_the_unit_spans_a_wide_band_across_the_corners():
    """And why the figures carrying absolute units draw a band rather than a
    line. The bias moves further between corners than the density does, and
    the two compound."""
    low, typical, high = (sky130.mim_unit(c) for c in sky130.CAP_CORNERS)
    assert low < typical < high
    assert high / low > 1.4


@pytest.mark.parametrize("corner", ("tt", "", "slow"))
def test_a_corner_the_capacitance_models_do_not_carry_is_refused(corner):
    """A device corner and a capacitance corner are different names for
    different things, and one passed where the other belongs would silently
    return the typical value."""
    with pytest.raises(ValueError):
        sky130.mim_capacitance(SMALL, SMALL, corner)


def test_a_plate_the_bias_cannot_survive_is_refused():
    with pytest.raises(ValueError):
        sky130.mim_capacitance(-2 * sky130.CAP_MIM_BIAS["typical"], 1.0)
