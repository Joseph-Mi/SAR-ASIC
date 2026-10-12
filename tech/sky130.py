"""What the sky130 process is: the device names, the sizes it draws, and the
matching it gives.

Contract: every fact about the process that more than one layer needs is
declared here, once, and nothing here depends on anything else in the
repository. The model's statistics, the simulation's netlists and the
sandbox's experiments all take their process numbers from this module.
"""

from __future__ import annotations

import math

MOSFET = r"sky130_fd_pr__[np]fet_01v8"
NFET = "sky130_fd_pr__nfet_01v8"
PFET = "sky130_fd_pr__pfet_01v8"
MIM = "sky130_fd_pr__cap_mim_m3_1"

#: The narrowest core device the PDK draws and has a model for, in
#: micrometres. Below it the simulator finds no model at all.
W_MIN = 0.42

#: The widest single finger to ask the models for. Their size bins cover a
#: bounded range of widths; anything wider is drawn, and modelled, as parallel
#: fingers of equal width.
W_FINGER_MAX = 5.0

#: Capacitor matching coefficient, percent-micrometres.
CAP_A_C = 0.47

#: Corners the capacitance models carry, lowest first.
CAP_CORNERS = ("low", "typical", "high")

#: What a MiM plate gives per unit of area, farads per square micrometre, and
#: how far the plate runs past the edge that was drawn, micrometres.
#:
#: The bias is positive and far from small -- more than a tenth of a
#: micrometre at every corner -- so at the smallest unit the process draws it
#: is worth a sixth of the value. A unit computed from its drawn area alone is
#: wrong by that much, and wrong by a different amount at each corner, because
#: the bias moves further between corners than the density does.
CAP_MIM_AREA = {"low": 1.78e-15, "typical": 2.00e-15, "high": 2.23e-15}
CAP_MIM_BIAS = {"low": 0.055, "typical": 0.150, "high": 0.245}

#: Smallest unit the process will draw, square micrometres, per flavour.
#: Matching improves with area, so the smaller of these is the worst matching
#: an array can be built to have: no unit can be made small enough to do
#: worse.
CAP_MIN_AREA_MIM = 4.00
CAP_MIN_AREA_VPP = 3.24

DIFF_EXT = 0.29


def mim_capacitance(width: float, length: float, corner: str = "typical") -> float:
    """A MiM capacitor of this drawn size, in farads.

    The device's own expression, taken on the plate the process ends up with
    rather than the shape that was drawn.
    """
    if corner not in CAP_MIM_AREA:
        raise ValueError(f"{corner} is not one of {CAP_CORNERS}")
    bias = CAP_MIM_BIAS[corner]
    if width + bias <= 0.0 or length + bias <= 0.0:
        raise ValueError(f"{width} x {length} um leaves no plate once biased")
    return CAP_MIM_AREA[corner] * (width + bias) * (length + bias)


def mim_unit(corner: str = "typical") -> float:
    """The smallest unit capacitor the process will draw, in farads.

    Square, because a unit that differs from its neighbours in shape differs
    from them in value: the bias acts on both dimensions, so two shapes of
    equal drawn area do not end up with equal plates.
    """
    side = math.sqrt(CAP_MIN_AREA_MIM)
    return mim_capacitance(side, side, corner)


def mosfet(w: float, length: float, mult: int = 1, nf: int = 1) -> dict[str, float]:
    """Core FET parameters, with junction geometry derived from the width.

    The PDK wrapper draws its mismatch terms against the geometry it is called
    with, so width and length belong on the subcircuit call.
    """
    return {
        "L": length,
        "W": w,
        "nf": nf,
        "ad": int((nf + 1) / 2) * w / nf * DIFF_EXT,
        "as": int((nf + 2) / 2) * w / nf * DIFF_EXT,
        "pd": 2 * int((nf + 1) / 2) * (w / nf + DIFF_EXT),
        "ps": 2 * int((nf + 2) / 2) * (w / nf + DIFF_EXT),
        "nrd": DIFF_EXT / w,
        "nrs": DIFF_EXT / w,
        "sa": 0,
        "sb": 0,
        "sd": 0,
        "mult": mult,
    }
