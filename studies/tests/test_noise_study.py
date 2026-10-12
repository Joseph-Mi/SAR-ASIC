"""The comparator specification, checked.

These assert the shape of the result rather than its digits, so a re-seeded or
lengthened run stays valid while a broken model does not.
"""

from __future__ import annotations

import numpy as np
import pytest

from noise_study import (
    BASELINE,
    GROSS_ERROR_ONSET_LSB,
    QUANTISATION_RMS_LSB,
    NoiseStudy,
    effective_bits,
    format_table,
    run_point,
    sweep,
)

#: How far apart the resolutions may land before the claim is in doubt. The
#: spread is a sampling artefact and narrows as the root of the conversion
#: count, so the allowance is derived from that rather than fixed: a shorter
#: run then loosens the test instead of failing it.
SPREAD_ALLOWANCE = 3.0

#: Conversions per point: enough for the claims below, few enough to run in
#: seconds.
CONVERSIONS = 400

#: Noise levels either side of the gross-error onset: well under it, and well
#: over it.
QUIET, LOUD = 0.5, 4.0

#: The largest error a noisy decision below the onset makes: a neighbouring
#: code.
NEIGHBOUR = 1.0

#: The rms of an error spread evenly across one LSB: the square root of that
#: uniform distribution's variance, a twelfth.
UNIFORM_RMS = 1 / np.sqrt(12)

#: Slack for counting noise, derived rather than chosen: the rms of n samples
#: has a relative spread of 1/sqrt(2n), and three of those is a bound a run
#: crosses once in a few hundred. Both forms loosen on their own when a run is
#: shortened, so a faster study does not start failing.
SIGMAS = 3.0
DITHER_AGREEMENT = SIGMAS / np.sqrt(2 * CONVERSIONS)
SAMPLING_BITS = DITHER_AGREEMENT / np.log(2)

#: A comparator worth designing to, in LSB, and what it may cost.
QUIET_COMPARATOR = 0.25
HALF_A_BIT = 0.5


@pytest.fixture(scope="module")
def study() -> NoiseStudy:
    return NoiseStudy(conversions=CONVERSIONS)


def test_committed_baseline_still_reproduces():
    """The whole point of committing the artifact, and the one check the other
    tests here cannot make: they assert the shape of the result, which a model
    can keep while every digit in it moves. A diff here means either the model
    changed or the seeding did, and both are things to look at.

    Run at the study's own settings, not the fast ones the shape tests use --
    the committed table is a particular run, and only that run reproduces it.
    """
    full = NoiseStudy()
    assert format_table(full, sweep(full)) == BASELINE.read_text()


def test_a_silent_comparator_costs_nothing(study):
    """The floor. Any drift here is the harness, not the physics."""
    for n_bits in study.resolutions:
        point = run_point(study, n_bits, 0.0)
        assert point["rms_err"] == 0.0
        assert point["p_wrong"] == 0.0
        # Not exact: the resolution is read off a finite run's own quantisation
        # error, which lands near the uniform rms rather than on it.
        assert point["enob_rms"] == pytest.approx(n_bits, abs=SAMPLING_BITS)


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
        uv = {n: run_point(study, n, noise)["noise_uv"] for n in study.resolutions}
        for coarse, fine in zip(study.resolutions, study.resolutions[1:], strict=False):
            assert uv[fine] == pytest.approx(uv[coarse] / 2 ** (fine - coarse))


def test_gross_errors_only_appear_once_noise_is_large(study):
    """Below the onset every mistake is a neighbouring code; above it an early
    decision goes wrong and costs a power of two."""
    for n_bits in study.resolutions:
        quiet = run_point(study, n_bits, GROSS_ERROR_ONSET_LSB * QUIET)
        loud = run_point(study, n_bits, GROSS_ERROR_ONSET_LSB * LOUD)
        assert quiet["p_gross"] == 0.0
        assert loud["p_gross"] > 0.0
        assert quiet["max_err"] <= NEIGHBOUR


def test_the_dithered_quantiser_is_what_a_quiet_comparator_costs(study):
    """The result the independent sum got wrong. Below the onset of gross
    errors a noisy comparator in front of a quantiser is a dithered
    quantiser, and its total error is the two in quadrature *at the input* --
    not the quantiser's error added to the code displacement, which counts
    the volts near a threshold twice.

    The onset itself is excluded: there the search starts losing early bits,
    which no quantiser model describes, and the measured error falls below
    the dithered one because a binary search corrects some of its own noise
    on the trials that follow."""
    for n_bits in study.resolutions:
        for noise in study.noises_lsb:
            if noise == 0.0 or noise >= GROSS_ERROR_ONSET_LSB:
                continue
            point = run_point(study, n_bits, noise)
            dithered = np.sqrt(QUANTISATION_RMS_LSB**2 + noise**2)
            assert point["rms_total"] == pytest.approx(dithered, rel=DITHER_AGREEMENT)


def test_a_quarter_lsb_comparator_costs_under_half_a_bit(study):
    """The number M5 designs against, and the one the independent sum
    overstated by about a factor of two."""
    for n_bits in study.resolutions:
        point = run_point(study, n_bits, QUIET_COMPARATOR)
        assert n_bits - point["enob_rms"] < HALF_A_BIT


def test_effective_bits_is_exact_when_only_the_quantiser_contributes(study):
    """The definition, independent of any sweep."""
    for n_bits in study.resolutions:
        assert effective_bits(n_bits, QUANTISATION_RMS_LSB) == pytest.approx(n_bits)
    assert QUANTISATION_RMS_LSB == pytest.approx(UNIFORM_RMS)


def test_a_converter_with_no_error_at_all_is_refused():
    """Infinite resolution is not a number, and returning one would make a
    broken measurement look like a perfect converter."""
    with pytest.raises(ValueError):
        effective_bits(10, 0.0)
