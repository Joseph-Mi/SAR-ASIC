"""What the sky130 process is: the device names, the sizes it draws, and the
matching it gives.

Contract: every fact about the process that more than one layer needs is
declared here, once, and nothing here depends on anything else in the
repository. The model's statistics, the simulation's netlists and the
sandbox's experiments all take their process numbers from this module.
"""

from __future__ import annotations

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

#: Smallest unit the process will draw, square micrometres, per flavour.
#: Matching improves with area, so the smaller of these is the worst matching
#: an array can be built to have: no unit can be made small enough to do
#: worse.
CAP_MIN_AREA_MIM = 4.00
CAP_MIN_AREA_VPP = 3.24

DIFF_EXT = 0.29


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
