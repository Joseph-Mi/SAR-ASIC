"""Routing dimensions derived from process rules for contacted MiM units.

Contract: a bottom contact sits outside capm; channel spacing accounts for
via landings, not just the narrower minimum metal width.
"""

from __future__ import annotations

import math

import sky130

ROUNDING_TOLERANCE = 1e-9


def on_grid(value: float, multiple: int = 1) -> float:
    """Round upward, allowing for floating-point error at an exact grid point."""
    step = multiple * sky130.LAYOUT_GRID
    return math.ceil(value / step - ROUNDING_TOLERANCE) * step


def metal1_width() -> float:
    return on_grid(sky130.VIA1_SIDE + 2 * sky130.VIA_LANDING_ENCLOSURE, multiple=2)


def metal2_width() -> float:
    return on_grid(
        max(sky130.VIA1_SIDE, sky130.VIA2_SIDE) + 2 * sky130.VIA_LANDING_ENCLOSURE, multiple=2
    )


def track_pitch() -> float:
    return on_grid(
        max(metal1_width(), metal2_width()) + max(sky130.METAL1_SPACING, sky130.METAL2_SPACING),
        multiple=2,
    )


def bottom_offset() -> float:
    """Distance left of capm to the bottom contact centre."""
    return on_grid(sky130.MIM_VIA2_SPACING + sky130.VIA2_SIDE / 2)


def contact_reach() -> float:
    """How far the contacted bottom metal projects left of capm."""
    return on_grid(bottom_offset() + sky130.VIA2_SIDE / 2 + sky130.VIA2_METAL3_ENCLOSURE)


def pitch_x(side: float) -> float:
    return on_grid(
        max(sky130.mim_pitch(side), side + contact_reach() + sky130.MIM_METAL_SPACING), multiple=2
    )


def pitch_y(n_bits: int, side: float) -> float:
    return on_grid(max(sky130.mim_pitch(side), (n_bits + 1) * track_pitch()))


def output_margin(n_bits: int) -> float:
    return sky130.MIM_METAL_SPACING + (n_bits + 1) * track_pitch() + metal2_width()
