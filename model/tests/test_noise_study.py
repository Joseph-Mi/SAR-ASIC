"""The comparator specification, checked.

These assert the shape of the result rather than its digits, so a re-seeded or
lengthened run stays valid while a broken model does not.
"""

from __future__ import annotations

import numpy as np
import pytest

from noise_study import (
    GROSS_ERROR_ONSET_LSB,
    QUANTISATION_RMS_LSB,
    NoiseStudy,
    effective_bits,
    run_point,
)

#: How far apart the resolutions may land before the claim is in doubt. The
#: spread is a sampling artefact and narrows as the root of the conversion
#: count, so the allowance is derived from that rather than fixed: a shorter
#: run then loosens the test instead of failing it.
SPREAD_ALLOWANCE = 3.0


@pytest.fixture(scope="module")
def study() -> NoiseStudy:
    return NoiseStudy(conversions=400)


def test_a_silent_comparator_costs_nothing(study):
    """The floor. Any drift here is the harness, not the physics."""
    for n_bits in study.resolutions:
        point = run_point(study, n_bits, 0.0)
        assert point["rms_err"] == 0.0
        assert point["p_wrong"] == 0.0
        assert point["enob_rms"] == pytest.approx(n_bits)


def test_error_grows_with_noise(study):
    """Monotonic in noise. A non-monotonic sweep is a seeding bug."""
    for n_bits in study.resolutions:
        rms = [run_point(study, n_bits, x)["rms_err"] for x in study.noises_lsb]
        assert rms == sorted(rms)


def test_the_same_noise_in_lsb_costs_the_same_at_every_resolution(study):
    """Which is what makes one sweep serve all of them: the LSB is the unit the
    converter actually cares about, so degradation tracks it and not volts."""
    for noise in study.noises_lsb:
        loss = [n - run_point(study, n, noise)["enob_rms"] for n in study.resolutions]
        assert np.allclose(loss, loss[0], atol=SPREAD_ALLOWANCE / np.sqrt(study.conversions))


def test_the_volts_that_buys_it_halves_with_every_bit(study):
    """And this is the cost of resolution: the same fraction of an LSB is a
    quieter comparator each time, by the factor the LSB itself shrank."""
    for noise in study.noises_lsb[1:]:
        uv = [run_point(study, n, noise)["noise_uv"] for n in study.resolutions]
        for coarse, fine in zip(uv, uv[1:], strict=False):
            assert fine == pytest.approx(coarse / 4.0)


def test_gross_errors_only_appear_once_noise_is_large(study):
    """Below the onset every mistake is a neighbouring code; above it an early
    decision goes wrong and costs a power of two."""
    for n_bits in study.resolutions:
        quiet = run_point(study, n_bits, GROSS_ERROR_ONSET_LSB / 2)
        loud = run_point(study, n_bits, GROSS_ERROR_ONSET_LSB * 4)
        assert quiet["p_gross"] == 0.0
        assert loud["p_gross"] > 0.0
        assert quiet["max_err"] <= 1.0


def test_effective_bits_is_exact_when_the_comparator_is_silent():
    """The definition, independent of any sweep."""
    for n_bits in (8, 10, 12):
        assert effective_bits(n_bits, 0.0) == pytest.approx(n_bits)
    assert QUANTISATION_RMS_LSB == pytest.approx(1 / np.sqrt(12))
