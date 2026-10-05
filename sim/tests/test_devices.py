"""A transistor asked for as many copies, or as a width wider than one finger,
conducts as that many devices -- in every family.

The sky130 wrapper takes a `mult` that scales only its mismatch term; a netlist
that relies on it gets one device however many it asked for, and every
binary-sized switch silently becomes a unit-sized one.
"""

from __future__ import annotations

import shutil

import pytest

import ngspice
import sky130
from devices import Generic, Sky130, pdk_library

pytestmark = pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not on PATH")

#: Copies asked for: enough that one device and many cannot be confused.
COPIES = 8

#: A width that needs this many fingers.
FINGERS = 3

#: Bias: a switch fully on, passing a small drain voltage.
V_GATE = 1.8
V_DRAIN = 0.1

LENGTH = 0.15
UNIT_W = 1.0

#: How close a current ratio must come to the count asked for.
RATIO_TOLERANCE = 0.01

FAMILIES = [
    pytest.param(Generic(), id="generic"),
    pytest.param(
        Sky130(),
        id="sky130",
        marks=pytest.mark.skipif(
            not pdk_library().exists(), reason="sky130 model library not found"
        ),
    ),
]


def drain_currents(tmp_path, devices, sizes: list[tuple[float, int]]) -> list[float]:
    """The drain current of an NMOS of each (width, copies), all biased alike."""
    lines = [
        "* device multiplicity",
        *devices.header(),
        *devices.models(),
        f"Vd d 0 {V_DRAIN}",
        f"Vg g 0 {V_GATE}",
    ]
    for k, (w, copies) in enumerate(sizes):
        lines += [
            devices.nmos(f"n{k}", f"d{k}", "g", "0", "0", w, LENGTH, copies),
            f"Vm{k} d d{k} 0",
        ]
    lines += [".control", "op"]
    lines += [f"let i{k} = -i(vm{k})" for k in range(len(sizes))]
    lines += ["print " + " ".join(f"i{k}" for k in range(len(sizes))), ".endc", ".end"]
    found = ngspice.run("\n".join(lines) + "\n", tmp_path)
    return [found[f"i{k}"][0] for k in range(len(sizes))]


@pytest.mark.parametrize("devices", FAMILIES)
def test_copies_conduct_as_that_many_devices(devices, tmp_path):
    one, many = drain_currents(tmp_path, devices, [(UNIT_W, 1), (UNIT_W, COPIES)])
    assert many / one == pytest.approx(COPIES, rel=RATIO_TOLERANCE)


@pytest.mark.skipif(not pdk_library().exists(), reason="sky130 model library not found")
def test_a_fingered_device_conducts_as_its_whole_width(tmp_path):
    """Only sky130 splits a wide device into fingers; the generic model takes
    any width whole, and its own width effects keep that from exact scaling."""
    finger = sky130.W_FINGER_MAX
    one, wide = drain_currents(tmp_path, Sky130(), [(finger, 1), (FINGERS * finger, 1)])
    assert wide / one == pytest.approx(FINGERS, rel=RATIO_TOLERANCE)
