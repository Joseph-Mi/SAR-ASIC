"""Contacted bottom plates, row channels and binary-branch output trunks.

Contract: only the selected row track receives a via; crossing a different
branch's track on another metal layer does not create a connection.
"""

from __future__ import annotations

import sky130
from array_geometry import bottom_offset, metal1_width, metal2_width, track_pitch
from array_place import Placement


def branch_label(branch: int, n_bits: int) -> str:
    """Name the weighted bottom terminals and the terminating bottom terminal."""
    return "bd" if branch == n_bits else f"b{branch}"


def rectangle(cell, lower, upper, spec):
    import gdspy

    cell.add(gdspy.Rectangle(lower, upper, layer=spec[0], datatype=spec[1]))


def square(cell, x, y, side, spec):
    half = side / 2
    rectangle(cell, (x - half, y - half), (x + half, y + half), spec)


def add_bottom_contact(cell, side: float) -> None:
    """Reach metal2 outside capm without punching through the capacitor."""
    x, y = -bottom_offset(), side / 2
    half = sky130.VIA2_SIDE / 2 + sky130.VIA2_METAL3_ENCLOSURE
    rectangle(cell, (x - half, y - half), (0, y + half), sky130.MIM_GDS_BOTTOM)
    square(cell, x, y, sky130.VIA2_SIDE, sky130.VIA2_GDS)
    square(cell, x, y, metal2_width(), sky130.METAL2_GDS)


def route_bottom(top, drawn: Placement) -> None:
    """Collect branch tracks on metal1 and join rows through metal2 trunks."""
    import gdspy

    channels = {}
    for unit in drawn.units:
        if unit.slot is not None:
            channels.setdefault((unit.row, unit.branch), []).append(unit)
    far_edge = max(u.x for u in drawn.units) + drawn.side
    trunks = {}
    for (_, branch), units in channels.items():
        lane = units[0].y + drawn.side / 2 + (branch - drawn.n_bits / 2) * track_pitch()
        trunk = far_edge + sky130.MIM_METAL_SPACING + (branch + 1) * track_pitch()
        trunks.setdefault(branch, []).append(lane)
        half = metal2_width() / 2
        for unit in units:
            x, y = unit.x - bottom_offset(), unit.y + drawn.side / 2
            rectangle(
                top,
                (x - half, min(y, lane) - half),
                (x + half, max(y, lane) + half),
                sky130.METAL2_GDS,
            )
            square(top, x, lane, sky130.VIA1_SIDE, sky130.VIA1_GDS)
            square(top, x, lane, metal1_width(), sky130.METAL1_GDS)
        half = metal1_width() / 2
        left = min(u.x for u in units) - bottom_offset()
        rectangle(top, (left - half, lane - half), (trunk + half, lane + half), sky130.METAL1_GDS)
        square(top, trunk, lane, sky130.VIA1_SIDE, sky130.VIA1_GDS)
    for branch, lanes in trunks.items():
        x = far_edge + sky130.MIM_METAL_SPACING + (branch + 1) * track_pitch()
        half = metal2_width() / 2
        rectangle(
            top, (x - half, min(lanes) - half), (x + half, max(lanes) + half), sky130.METAL2_GDS
        )
        top.add(
            gdspy.Label(
                branch_label(branch, drawn.n_bits),
                (x, min(lanes)),
                layer=sky130.METAL2_LABEL_GDS[0],
                texttype=sky130.METAL2_LABEL_GDS[1],
            )
        )
