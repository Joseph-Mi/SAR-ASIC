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

#: Appended to the key of a negative coordinate, so it cannot collide with
#: the positive coordinate of the same magnitude.
NEGATIVE = 1

#: The narrowest column a table prints, in characters: wide enough for every
#: number the studies format.
COLUMN_WIDTH = 13


def rng_for(seed: int, n_bits: int, coordinate: float) -> np.random.Generator:
    """A stream determined by the point's coordinates, not by its index.

    A negative coordinate is carried as its magnitude plus a trailing marker
    rather than folded into one number, because `SeedSequence` takes only
    non-negative integers and every obvious encoding of a sign -- zigzag, an
    offset, a sign bit in the low position -- changes the key of the positive
    coordinates too. Those are the keys three committed baselines were
    measured at, so an encoding that moved them would silently rewrite every
    study in the repository and the diff would look like a result.

    So: non-negative coordinates keep exactly the key they have always had,
    and a negative one is a key of a different length, which no non-negative
    coordinate can collide with.
    """
    value = int(round(coordinate * COORDINATE_PARTS))
    key = (seed, n_bits, value) if value >= 0 else (seed, n_bits, -value, NEGATIVE)
    return np.random.default_rng(np.random.SeedSequence(key))


def column_widths(columns) -> dict[str, int]:
    return {c: max(len(c), COLUMN_WIDTH) for c in columns}
