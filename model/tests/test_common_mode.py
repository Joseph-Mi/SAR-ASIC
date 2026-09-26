"""Where the common mode can come from, and what its movement costs."""

import math

import pytest

from common_mode import divider, drift_within_conversion, loaded_reference, threshold_shift

VREF = 1.0
C_TOTAL = 1e-12
TAU = 1e-9


def test_a_common_mode_that_does_not_move_shifts_nothing():
    """Accuracy is irrelevant: the same wrong value at sampling and at the
    decision cancels."""
    assert threshold_shift(0.45, 0.45) == 0.0


def test_a_common_mode_that_moves_shifts_every_threshold_by_the_move():
    assert threshold_shift(0.50, 0.49) == pytest.approx(0.01)


def test_a_divider_is_a_thevenin_source_of_its_two_halves_in_parallel():
    r_th, current = divider(4e3, VREF, 0.5)
    assert r_th == pytest.approx(1e3)
    assert current == pytest.approx(VREF / 4e3)


def test_an_off_centre_divider_is_stiffer_for_the_same_string():
    r_mid, _ = divider(4e3, VREF, 0.5)
    r_off, _ = divider(4e3, VREF, 0.3)
    assert r_off < r_mid


def test_without_decoupling_the_whole_residual_drifts_away():
    """With nothing to hold it, the node finishes recovering during the
    conversion, so the shift is everything sampling left."""
    step, t_sample = 0.5, 3 * TAU
    shift = drift_within_conversion(step, C_TOTAL, 0.0, TAU / C_TOTAL, t_sample, 100 * TAU)
    assert shift == pytest.approx(step * math.exp(-3), rel=1e-6)


def test_decoupling_trades_accuracy_for_slowness_and_wins():
    """A large capacitor makes the jump small and the recovery slow. The node
    ends sampling far from settled -- and barely moves in one conversion,
    which is the only thing a threshold sees."""
    step, r_th, t_sample, t_conversion = 0.5, TAU / C_TOTAL, 3 * TAU, 20 * TAU
    bare = drift_within_conversion(step, C_TOTAL, 0.0, r_th, t_sample, t_conversion)
    decoupled = drift_within_conversion(step, C_TOTAL, 100 * C_TOTAL, r_th, t_sample, t_conversion)
    assert decoupled < bare / 10


def test_drift_never_exceeds_the_jump():
    step = 0.5
    for c_dec in (0.0, C_TOTAL, 10 * C_TOTAL):
        jump = step * C_TOTAL / (C_TOTAL + c_dec)
        assert drift_within_conversion(step, C_TOTAL, c_dec, 1e3, 0.0, math.inf) <= jump + 1e-15


def test_a_divider_on_the_reference_pin_sags_the_reference_it_feeds():
    """The string's current crosses the pin: the array's reference is the
    source divided down by the pin against the string."""
    r_total, r_pin = 4e3, 100.0
    assert loaded_reference(VREF, r_total, r_pin) == pytest.approx(
        VREF * r_total / (r_total + r_pin)
    )


def test_the_sag_is_the_string_current_times_the_pin():
    r_total, r_pin = 4e3, 1.0
    _, current = divider(r_total, VREF, 0.5)
    assert VREF - loaded_reference(VREF, r_total, r_pin) == pytest.approx(current * r_pin, rel=1e-3)
