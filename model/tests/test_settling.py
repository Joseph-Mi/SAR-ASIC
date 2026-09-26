"""The settling law every phase length is sized by."""

import math

import numpy as np
import pytest

from settling import c_seen_by_reference, residual, settle_time

TAU = 1e-9
STEP = 1.0


def test_a_settled_node_has_no_residual_left_at_infinity():
    assert residual(math.inf, TAU, STEP) == 0.0


def test_one_time_constant_leaves_one_over_e():
    assert residual(TAU, TAU, STEP) == pytest.approx(STEP / math.e)


def test_settle_time_is_the_inverse_of_the_residual():
    tolerance = STEP / 2**11
    assert residual(settle_time(TAU, STEP, tolerance), TAU, STEP) == pytest.approx(tolerance)


def test_half_an_lsb_of_a_full_scale_step_takes_n_plus_one_ln2_time_constants():
    """The textbook bound, (N+1) ln 2 tau, is this law at one particular step
    and tolerance -- which is why it is not a constant to be written down."""
    n_bits = 10
    lsb = STEP / 2**n_bits
    assert settle_time(TAU, STEP, lsb / 2) == pytest.approx((n_bits + 1) * math.log(2) * TAU)


def test_halving_the_step_saves_only_ln2_time_constants():
    tolerance = STEP / 2**11
    saved = settle_time(TAU, STEP, tolerance) - settle_time(TAU, STEP / 2, tolerance)
    assert saved == pytest.approx(math.log(2) * TAU)


def test_the_reference_sees_the_selected_branches_in_series_with_the_rest():
    """Switching branches to the reference moves a floating top plate, so the
    reference charges the selected capacitance through the unselected."""
    assert c_seen_by_reference(3.0, 8.0) == pytest.approx(3.0 * 5.0 / 8.0)


def test_the_reference_sees_most_at_the_msb_trial():
    """Worst case is half the array against the other half: a quarter of it."""
    total = 1.0
    selected = np.linspace(0.0, total, 1001)
    seen = [c_seen_by_reference(c, total) for c in selected]
    assert max(seen) == pytest.approx(total / 4)
    assert selected[int(np.argmax(seen))] == pytest.approx(total / 2)


def test_nothing_selected_or_everything_selected_loads_nothing():
    assert c_seen_by_reference(0.0, 1.0) == 0.0
    assert c_seen_by_reference(1.0, 1.0) == 0.0
