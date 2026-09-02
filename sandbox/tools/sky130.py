"""Instance parameters for sky130 devices."""

from __future__ import annotations

MOSFET = r"sky130_fd_pr__[np]fet_01v8"

#: Diffusion extension past the gate, micrometres, as the PDK's own symbol
#: expressions spend it.
DIFF_EXT = 0.29


def mosfet(w: float, length: float, mult: int = 1, nf: int = 1) -> dict[str, float]:
    """Core FET parameters, with junction geometry derived from the width.

    Stale junction area and perimeter would carry the wrong capacitance into a
    transient, so both are recomputed rather than carried over.

    Width and length go on the subcircuit call where the PDK wrapper sees them:
    its mismatch terms are drawn against the geometry it was called with.
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
