"""What every study shares: how a point gets its random stream, and how its
table is laid out.

Contract: a point's stream depends only on the study's seed and the point's
coordinates, so adding or reordering points never changes another point's
numbers, and a table written twice is byte-identical.
"""

from __future__ import annotations

import numpy as np

#: A float coordinate joins the seed as an integer count of this many parts per
#: unit: fine enough that no two points a study could ask for collide.
COORDINATE_PARTS = 1e12

#: The narrowest column a table prints, in characters: wide enough for every
#: number the studies format.
COLUMN_WIDTH = 13


def rng_for(seed: int, n_bits: int, coordinate: float) -> np.random.Generator:
    """A stream determined by the point's coordinates, not by its index."""
    key = (seed, n_bits, int(round(coordinate * COORDINATE_PARTS)))
    return np.random.default_rng(np.random.SeedSequence(key))


def column_widths(columns) -> dict[str, int]:
    return {c: max(len(c), COLUMN_WIDTH) for c in columns}
