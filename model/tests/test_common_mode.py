"""Where the common mode can come from, and what its movement costs."""

import math

import pytest

from common_mode import divider, drift_within_conversion, loaded_reference, threshold_shift

VREF = 1.0
C_TOTAL = 1e-12
TAU = 1e-9

#: Illustrative levels: a common mode that stays, and one that moves by a
#: small amount between sampling and the decision.
VCM = 0.45 * VREF
MOVE = 0.01 * VREF

#: A resistor string across the reference, tapped at the middle or off it.
R_STRING = 4e3
MID, OFF_CENTRE = 0.5, 0.3

#: A step left on the node by sampling, and the times it has to recover: a
#: sample of a few time constants, a conversion of many.
STEP = 0.5 * VREF
T_SAMPLE = 3 * TAU
T_CONVERSION = 20 * TAU

#: Decoupling far larger than the array, and how much smaller that makes the
#: drift a threshold sees.
BIG_DECOUPLING = 100 * C_TOTAL
DRIFT_REDUCTION = 10

#: A pin resistance small against the string, and one negligible against it
#: -- where the sag is the string current times the pin to first order.
R_PIN = 100.0
R_PIN_SMALL = 1.0

#: Solver-free arithmetic agrees to this; a first-order estimate to the next.
EXACT = 1e-6
FIRST_ORDER = 1e-3
ROUNDING = 1e-15


def test_a_common_mode_that_does_not_move_shifts_nothing():
    """Accuracy is irrelevant: the same wrong value at sampling and at the
    decision cancels."""
    assert threshold_shift(VCM, VCM) == 0.0


def test_a_common_mode_that_moves_shifts_every_threshold_by_the_move():
    assert threshold_shift(VCM + MOVE, VCM) == pytest.approx(MOVE)


def test_a_divider_is_a_thevenin_source_of_its_two_halves_in_parallel():
    r_th, current = divider(R_STRING, VREF, MID)
    upper, lower = R_STRING * (1 - MID), R_STRING * MID
    assert r_th == pytest.approx(upper * lower / R_STRING)
    assert current == pytest.approx(VREF / R_STRING)


def test_an_off_centre_divider_is_stiffer_for_the_same_string():
    r_mid, _ = divider(R_STRING, VREF, MID)
    r_off, _ = divider(R_STRING, VREF, OFF_CENTRE)
    assert r_off < r_mid


def test_without_decoupling_the_whole_residual_drifts_away():
    """With nothing to hold it, the node finishes recovering during the
    conversion, so the shift is everything sampling left."""
    shift = drift_within_conversion(STEP, C_TOTAL, 0.0, TAU / C_TOTAL, T_SAMPLE, math.inf)
    assert shift == pytest.approx(STEP * math.exp(-T_SAMPLE / TAU), rel=EXACT)


def test_decoupling_trades_accuracy_for_slowness_and_wins():
    """A large capacitor makes the jump small and the recovery slow. The node
    ends sampling far from settled -- and barely moves in one conversion,
    which is the only thing a threshold sees."""
    r_th = TAU / C_TOTAL
    bare = drift_within_conversion(STEP, C_TOTAL, 0.0, r_th, T_SAMPLE, T_CONVERSION)
    decoupled = drift_within_conversion(STEP, C_TOTAL, BIG_DECOUPLING, r_th, T_SAMPLE, T_CONVERSION)
    assert decoupled < bare / DRIFT_REDUCTION


def test_drift_never_exceeds_the_jump():
    for c_dec in (0.0, C_TOTAL, BIG_DECOUPLING):
        jump = STEP * C_TOTAL / (C_TOTAL + c_dec)
        drift = drift_within_conversion(STEP, C_TOTAL, c_dec, R_STRING, 0.0, math.inf)
        assert drift <= jump + ROUNDING


def test_a_divider_on_the_reference_pin_sags_the_reference_it_feeds():
    """The string's current crosses the pin: the array's reference is the
    source divided down by the pin against the string."""
    assert loaded_reference(VREF, R_STRING, R_PIN) == pytest.approx(
        VREF * R_STRING / (R_STRING + R_PIN)
    )


def test_the_sag_is_the_string_current_times_the_pin():
    _, current = divider(R_STRING, VREF, MID)
    sag = VREF - loaded_reference(VREF, R_STRING, R_PIN_SMALL)
    assert sag == pytest.approx(current * R_PIN_SMALL, rel=FIRST_ORDER)
