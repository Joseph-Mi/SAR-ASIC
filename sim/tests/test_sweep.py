"""M3's pass criterion: over a sweep of inputs, the circuit converts what the
golden model converts, with every input a small distance either side of a
threshold."""

from __future__ import annotations

import shutil

import numpy as np
import pytest

from interface import N_BITS
from sweep import (
    EDGE_OFFSET_LSB,
    VREF,
    carry_codes,
    code_of,
    convert,
    either_side,
    lsb,
    mismatches,
    model,
)

pytestmark = pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not on PATH")

#: Small enough to sweep every threshold both sides in one run.
EXHAUSTIVE_BITS = 6

#: At the target resolution every threshold would be slow, so the sweep takes
#: the ones where the most branches change at once -- each bit's carry, where
#: every lower branch switches out and one switches in -- plus a spread of
#: arbitrary ones.
ARBITRARY_CODES = 64
SEED = 20260927

#: A pin level far from the sampled one, applied after sampling. The array
#: must not see it.
DISTURBANCE = 0.9


def test_every_threshold_both_sides_at_a_small_resolution(tmp_path):
    inputs = either_side(range(2**EXHAUSTIVE_BITS), EXHAUSTIVE_BITS)
    got = convert(inputs, EXHAUSTIVE_BITS, tmp_path)
    assert not mismatches(inputs, got, model(inputs, EXHAUSTIVE_BITS), EXHAUSTIVE_BITS)


def test_carries_and_a_spread_both_sides_at_the_target_resolution(tmp_path):
    rng = np.random.default_rng(SEED)
    arbitrary = rng.choice(np.arange(1, 2**N_BITS), ARBITRARY_CODES, replace=False)
    codes = sorted(set(carry_codes(N_BITS)) | {int(c) for c in arbitrary})
    inputs = either_side(codes, N_BITS)
    got = convert(inputs, N_BITS, tmp_path)
    assert not mismatches(inputs, got, model(inputs, N_BITS), N_BITS)


def test_the_codes_step_by_one_across_each_threshold(tmp_path):
    """Read as codes rather than decisions: just below a threshold is the code
    under it, just above is the code itself -- no missing and no repeated
    codes where the model has none."""
    codes = carry_codes(N_BITS)
    inputs = either_side(codes, N_BITS)
    got = [code_of(t) for t in convert(inputs, N_BITS, tmp_path)]
    pairs = dict(zip(inputs, got, strict=True))
    step = lsb(N_BITS)
    for k in codes:
        below = pairs[k * step - EDGE_OFFSET_LSB * step]
        above = pairs[k * step + EDGE_OFFSET_LSB * step]
        assert (below, above) == (k - 1, k), f"threshold {k}"


def test_the_held_sample_ignores_the_pin_after_sampling(tmp_path):
    """The comparator never sees the pin. Once sampling ends the input is
    charge on the array, so moving the pin mid-conversion changes nothing."""
    inputs = either_side(carry_codes(N_BITS), N_BITS)
    got = convert(inputs, N_BITS, tmp_path, after_sampling=DISTURBANCE * VREF)
    assert not mismatches(inputs, got, model(inputs, N_BITS), N_BITS)
