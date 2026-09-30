"""Transistors, for the parts of the block a test does not idealise.

Contract: `nmos` and `pmos` return one instance line each, and `models()` the
lines a netlist needs before those instances resolve. Widths and lengths are
in micrometres whichever family is used.

Two families, because the charge a switch holds and releases is what is under
test, and that needs a charge-conserving device model. The generic one is the
simulator's own: charge-based, runs anywhere, stands in for no process in
particular. sky130's is the real device, and needs the PDK.
"""

from __future__ import annotations

import math
import os
import pathlib
from dataclasses import dataclass

import sky130


@dataclass(frozen=True)
class Generic:
    """The simulator's built-in charge-based model, at its default parameters."""

    def models(self) -> list[str]:
        return [
            ".model gen_n nmos level=14 version=4.8",
            ".model gen_p pmos level=14 version=4.8",
        ]

    def header(self) -> list[str]:
        return []

    def nmos(self, name, d, g, s, b, w: float, length: float, mult: int = 1) -> str:
        return f"M{name} {d} {g} {s} {b} gen_n W={w:.6g}u L={length:.6g}u m={mult}"

    def pmos(self, name, d, g, s, b, w: float, length: float, mult: int = 1) -> str:
        return f"M{name} {d} {g} {s} {b} gen_p W={w:.6g}u L={length:.6g}u m={mult}"


def pdk_library() -> pathlib.Path:
    """The model library the PDK's own schematic setup selects."""
    root = pathlib.Path(os.environ.get("PDK_ROOT", "/nonexistent"))
    return root / os.environ.get("PDK", "sky130A") / "libs.tech/combined/sky130.lib.spice"


@dataclass(frozen=True)
class Sky130:
    """The PDK's core devices at one process corner.

    A wide device becomes equal parallel fingers inside the models' width
    range, the way it would be drawn; a device narrower than the process draws
    is refused, since there is no model to fall back on.
    """

    corner: str = "tt"

    def models(self) -> list[str]:
        return []

    def header(self) -> list[str]:
        return [f".lib {pdk_library()} {self.corner}"]

    def _instance(self, model, name, d, g, s, b, w, length, mult) -> str:
        """The wrapper's own `mult` only scales its mismatch term -- the
        device inside is one transistor whatever it says. The copies are made
        by the instance's `m`, and `mult` is kept equal to it so the mismatch
        is the whole device's."""
        if w < sky130.W_MIN:
            raise ValueError(f"{name}: W={w} um is below the {sky130.W_MIN} um sky130 draws")
        fingers = math.ceil(w / sky130.W_FINGER_MAX)
        copies = mult * fingers
        each = sky130.mosfet(w / fingers, length, copies)
        params = " ".join(f"{k}={v:.6g}" for k, v in each.items())
        return f"X{name} {d} {g} {s} {b} {model} {params} m={copies}"

    def nmos(self, name, d, g, s, b, w: float, length: float, mult: int = 1) -> str:
        return self._instance(sky130.NFET, name, d, g, s, b, w, length, mult)

    def pmos(self, name, d, g, s, b, w: float, length: float, mult: int = 1) -> str:
        return self._instance(sky130.PFET, name, d, g, s, b, w, length, mult)
