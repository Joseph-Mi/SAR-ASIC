"""Interleaved capacitor coordinates within the tile's analog strip.

Contract: slots retain electrical branch order; sorting their coordinates by
row then column recovers physical order, including the terminating unit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import sky130
import template
from interface import N_BITS
from mismatch import interleaved
from sar import branch_slices

DUMMY_RING = 1


@dataclass(frozen=True)
class Unit:
    """A plate's lower-left corner in micrometres and its electrical owner.

    A missing slot denotes perimeter or filler, not the terminating capacitor.
    The terminating capacitor's branch equals the converter resolution.
    """

    x: float
    y: float
    column: int
    row: int
    slot: int | None
    branch: int | None


@dataclass(frozen=True)
class Placement:
    """A rectangular field, with every unused site filled by a dummy."""

    n_bits: int
    side: float
    columns: int
    rows: int
    units: tuple[Unit, ...]


def placement(
    n_bits: int = N_BITS,
    *,
    side: float | None = None,
    width: float | None = None,
    height: float | None = None,
) -> Placement:
    """Place the electrical permutation at the pitch of isolated bottom plates.

    Separate polygons cannot claim shared-plate spacing even when their owners
    match. Branch interconnect is outside this placement contract.
    """
    if not isinstance(n_bits, int) or n_bits < 1:
        raise ValueError("resolution must be a positive integer")
    strip_width, strip_height = template.analog_strip()
    width = strip_width if width is None else width
    height = strip_height if height is None else height
    side = sky130.mim_side() if side is None else side
    if not all(math.isfinite(v) and v > 0.0 for v in (width, height, side)):
        raise ValueError("strip dimensions and unit side must be finite and positive")
    count = 2**n_bits
    fit = sky130.mim_fit(count, side, height, ring=DUMMY_RING, shared=False)
    if fit is None or fit[2] > width:
        raise ValueError("the array and dummy ring do not fit the analog strip")
    rows, per_row, _ = fit
    columns = per_row + 2 * DUMMY_RING
    owners = [n_bits] * count
    for branch, slots in enumerate(branch_slices(n_bits)):
        owners[slots] = [branch] * (slots.stop - slots.start)
    order = interleaved(n_bits)
    physical_slots = [0] * count
    for slot, physical in enumerate(order):
        physical_slots[int(physical)] = slot
    pitch = sky130.mim_pitch(side, shared=False)
    units = []
    for row in range(rows):
        for column in range(columns):
            physical = (row - DUMMY_RING) * per_row + column - DUMMY_RING
            interior = (
                DUMMY_RING <= row < rows - DUMMY_RING
                and DUMMY_RING <= column < columns - DUMMY_RING
            )
            slot = physical_slots[physical] if interior and physical < count else None
            units.append(
                Unit(
                    x=sky130.MIM_METAL_SPACING + column * pitch,
                    y=sky130.MIM_METAL_SPACING + row * pitch,
                    column=column,
                    row=row,
                    slot=slot,
                    branch=None if slot is None else owners[slot],
                )
            )
    return Placement(n_bits, side, columns, rows, tuple(units))
