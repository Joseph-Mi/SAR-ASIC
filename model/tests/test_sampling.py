"""Sampling memory, separated into the part that is a filter and the part that
is distortion.

The distinction is the whole reason this module exists. An error proportional
to the input's change between conversions sounds like it should cost
resolution, and it does not: it is linear, so it costs gain. Only a
coefficient that varies with the signal costs resolution. Budgeting the first
as if it were the second buys decoupling that does nothing.
"""

from __future__ import annotations

import numpy as np
import pytest

from common_mode import drift_within_conversion
from sampling import (
    coherent_cycles,
    level_dependent,
    measure,
    sampled,
    step_coefficient,
    sweep,
)
from spectrum import AMPLITUDE_FRACTION, RECORD, coherent_sine

VREF = 1.0
BITS = 10

#: Fractions of Nyquist to sweep. The low end is where a converter is
#: characterised, the high end is where any memory effect is largest.
FRACTIONS = (0.01, 0.1, 0.3, 0.5, 0.9)

#: Step coefficient used where the effect has to be visible but not dominant:
#: a source that has recovered all but a few percent of the kick.
COEFFICIENT = 0.02

#: Fractional change in that coefficient across the input range, for the
#: nonlinear case. One means it doubles from one rail to the other, which no
#: real recovery path does -- the point is to make the mechanism unmistakable
#: before asking how small it has to be to ignore.
SLOPE = 1.0

#: An array whose decoupling, resistance and phase lengths put the source well
#: inside its recovery and well outside it. Illustrative, not design values.
C_TOTAL, C_DEC, R_TH = 8e-12, 1e-9, 820.0
T_SAMPLE, T_CONVERSION = 50e-9, 1e-6

#: dB the distortion must sit below the tone to count as absent, for a record
#: quantised at this resolution. The quantisation floor is well above it.
NO_DISTORTION_DB = 70.0

#: Amplitude the sweeps offer. Below the static figure's, because the memory
#: raises the amplitude the converter actually sees and a record that reaches
#: the rail is measuring saturation instead.
BACKED_OFF = 0.45

#: Bits of agreement for two routes to the same record.
EXACT = 1e-12


def test_no_memory_leaves_the_record_alone():
    """The coefficient enters one expression, so zero has to be the identity
    through it -- otherwise every result is measured against a shifted
    baseline."""
    offered = coherent_sine(RECORD, coherent_cycles(0.3), VREF, AMPLITUDE_FRACTION)
    assert np.allclose(sampled(offered, 0.0), offered, atol=EXACT)


def test_a_constant_coefficient_adds_no_distortion_at_any_frequency():
    """The headline result. A first difference of the input is a filter, and a
    filter moves no energy out of the signal bin, however large it is and
    however fast the input moves."""
    rows = sweep(FRACTIONS, COEFFICIENT, n_bits=BITS, vref=VREF, amplitude_frac=BACKED_OFF)
    for row in rows:
        assert row["thd"] < -NO_DISTORTION_DB, row


def test_a_constant_coefficient_is_a_gain_error_that_grows_with_frequency():
    """What it does cost instead. Said as the measurement that would find it:
    the amplitude the converter sees is not the amplitude offered, and the
    discrepancy rises with input frequency -- which is a bandwidth figure, not
    a resolution one."""
    gains = []
    for fraction in FRACTIONS:
        cycles = coherent_cycles(fraction)
        offered = coherent_sine(RECORD, cycles, VREF, AMPLITUDE_FRACTION)
        held = sampled(offered, COEFFICIENT)
        gains.append(np.ptp(held) / np.ptp(offered))
    assert gains == sorted(gains)
    assert gains[0] == pytest.approx(1.0, abs=1e-3)
    assert gains[-1] > 1.0


def test_a_level_dependent_coefficient_is_what_actually_costs_resolution():
    """And the mechanism that produces it: the error becomes a product of the
    step and the level, which is a second-order term and therefore a
    harmonic."""
    linear = sweep(FRACTIONS, COEFFICIENT, n_bits=BITS, vref=VREF, amplitude_frac=BACKED_OFF)
    curved = sweep(
        FRACTIONS,
        level_dependent(COEFFICIENT, SLOPE, VREF),
        n_bits=BITS,
        vref=VREF,
        amplitude_frac=BACKED_OFF,
    )
    for straight, bent in zip(linear, curved, strict=True):
        assert bent["thd"] > straight["thd"], (straight, bent)
    assert curved[-1]["thd"] > curved[0]["thd"]
    assert curved[-1]["sfdr"] < linear[-1]["sfdr"]


def test_a_level_dependent_coefficient_with_no_slope_is_the_constant_one():
    """One code path serves both cases, so the boundary between them has to be
    continuous -- or the comparison above is between two different models."""
    offered = coherent_sine(RECORD, coherent_cycles(0.3), VREF, AMPLITUDE_FRACTION)
    flat = sampled(offered, level_dependent(COEFFICIENT, 0.0, VREF))
    assert np.allclose(flat, sampled(offered, COEFFICIENT), atol=EXACT)


def test_the_distortion_it_costs_falls_away_as_the_slope_does():
    """Which is what makes the mechanism a budget rather than a verdict: the
    question a circuit measurement has to answer is how curved the recovery
    path is, and this says what each answer would cost."""
    worst = max(FRACTIONS)
    distortion = [
        sweep(
            [worst],
            level_dependent(COEFFICIENT, slope, VREF),
            n_bits=BITS,
            vref=VREF,
            amplitude_frac=BACKED_OFF,
        )[0]["thd"]
        for slope in (SLOPE, SLOPE / 4, SLOPE / 16)
    ]
    assert distortion == sorted(distortion, reverse=True)


def test_a_record_the_memory_pushes_into_the_rail_is_refused():
    """Saturation is distortion, and a figure that silently included it would
    be reported as the sampling result it is not. The amplitude the converter
    sees is not the amplitude offered, so the headroom has to be checked
    against the former."""
    with pytest.raises(ValueError, match="saturation"):
        sweep([0.9], COEFFICIENT, n_bits=BITS, vref=VREF, amplitude_frac=AMPLITUDE_FRACTION)


def test_the_step_coefficient_is_the_settling_law_and_not_a_second_one():
    """A coefficient derived here and a drift computed there would be two
    numbers for one physical recovery."""
    got = step_coefficient(C_TOTAL, C_DEC, R_TH, T_SAMPLE, T_CONVERSION)
    want = drift_within_conversion(1.0, C_TOTAL, C_DEC, R_TH, T_SAMPLE, T_CONVERSION)
    assert got == want
    assert 0.0 < got < 1.0


def test_a_source_given_long_enough_leaves_no_memory():
    """The limit the coefficient has to have, or it is not a recovery."""
    patient = step_coefficient(C_TOTAL, C_DEC, R_TH, 1.0, T_CONVERSION)
    assert patient < step_coefficient(C_TOTAL, C_DEC, R_TH, T_SAMPLE, T_CONVERSION)
    assert patient == pytest.approx(0.0, abs=EXACT)


def test_the_record_wraps_so_a_coherent_sweep_is_a_steady_state():
    """The sample before the first is the last one. Treating the first sample
    as having no predecessor puts a step at the start of every record, which
    is broadband and would be read as noise at every frequency."""
    offered = coherent_sine(RECORD, coherent_cycles(0.3), VREF, AMPLITUDE_FRACTION)
    held = sampled(offered, COEFFICIENT)
    rolled = sampled(np.roll(offered, 1), COEFFICIENT)
    assert np.allclose(np.roll(held, 1), rolled, atol=EXACT)


@pytest.mark.parametrize("fraction", FRACTIONS)
def test_every_swept_frequency_is_coherent(fraction):
    """A tone that does not close in the record leaks into its neighbours, and
    leakage reads as distortion -- so an incoherent sweep point would
    manufacture exactly the effect being measured."""
    cycles = coherent_cycles(fraction, RECORD)
    assert cycles % 2 == 1
    assert np.gcd(cycles, RECORD) == 1
    assert abs(cycles - fraction * RECORD / 2) <= 1


@pytest.mark.parametrize("fraction", (0.0, 1.0, -0.1, 1.5))
def test_a_frequency_outside_the_band_is_refused(fraction):
    with pytest.raises(ValueError):
        coherent_cycles(fraction)


def test_a_measurement_reports_every_figure_together():
    """The figures are read off one record, so they are reported as one row:
    an SNDR without the distortion beside it does not say what to fix."""
    rows = sweep([0.1], COEFFICIENT, n_bits=BITS, vref=VREF, amplitude_frac=BACKED_OFF)
    assert set(rows[0]) == {"fraction", "cycles", "sndr", "snr", "thd", "sfdr", "enob"}
    codes = np.round(coherent_sine(RECORD, coherent_cycles(0.1)) * 2**BITS)
    assert set(measure(codes, coherent_cycles(0.1))) < set(rows[0])
