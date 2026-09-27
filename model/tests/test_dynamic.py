"""ENOB is the claim a resolution makes. These pin what it is measured against."""

import numpy as np
import pytest

from dynamic import (
    AMPLITUDE_FRACTION,
    CYCLES,
    codes_from_curve,
    coherent_sine,
    enob,
    enob_of,
    sndr_db,
)
from metrics import has_missing_codes
from mismatch import random_units
from sar import ideal_units, sar_convert

RESOLUTIONS = (4, 8, 10)
VREF = 1.0

#: The resolution the single-array tests use.
N_BITS = 8

#: How close a measured ENOB must come to what it is compared against, in
#: bits. Not measurement slop: the ideal-SNDR constants assume quantisation
#: error uniform and uncorrelated with the input, which a coarse quantiser
#: driven by a pure tone only approximately obeys.
ENOB_TOLERANCE = 0.1

#: The share of a coherent tone's power allowed outside its own bin.
LEAKAGE = 1e-12

#: A shorter record for the tests that run one search per sample: a power of
#: two, and a prime cycle count below its Nyquist bin.
SHORT_RECORD, SHORT_CYCLES = 256, 31

#: A mismatch large enough to move transitions, from a fixed seed.
SIGMA = 0.02
SEED = 11

#: How much smaller a unit a non-monotonic array's upper half is.
SHRINK = 0.9

#: A stimulus backed well off the rails.
BACKED_OFF = 0.35

#: Mismatch levels in rising order, arrays drawn at each, a fixed seed, and
#: the smallest ENOB loss the largest must cost against none.
SIGMAS = (0.0, 0.01, 0.02, 0.04)
TRIALS = 24
LOSS_SEED = 2
MIN_LOSS = 0.1


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_a_perfect_array_is_worth_its_nominal_bits(n_bits):
    """The end-to-end check. A perfect N-bit array must measure N effective
    bits, because quantisation is the only error left in it."""
    assert np.isclose(enob_of(ideal_units(n_bits)), n_bits, atol=ENOB_TOLERANCE)


def test_the_stimulus_lands_in_exactly_one_bin():
    """Coherence, before any converter is involved. An incoherent record would
    smear the tone and be scored as distortion the array never produced."""
    spectrum = np.abs(np.fft.rfft(coherent_sine() - coherent_sine().mean())) ** 2
    assert spectrum[CYCLES] / spectrum.sum() > 1 - LEAKAGE


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_the_lookup_agrees_with_the_search_on_an_ideal_array(n_bits):
    """The fast path exists to avoid one binary search per sample, so it has
    to give what those searches would."""
    units = ideal_units(n_bits)
    vin = coherent_sine(n_samples=SHORT_RECORD, cycles=SHORT_CYCLES, vref=VREF)
    fast = codes_from_curve(vin, units, VREF)
    slow = [sar_convert(v, units, VREF)[0] for v in vin]
    assert list(fast) == slow


def test_the_lookup_agrees_with_the_search_under_mismatch():
    """Mismatch moves the transitions. Both routes have to move with them."""
    units = random_units(N_BITS, SIGMA, np.random.default_rng(SEED))
    vin = coherent_sine(n_samples=SHORT_RECORD, cycles=SHORT_CYCLES, vref=VREF)
    fast = codes_from_curve(vin, units, VREF)
    slow = [sar_convert(v, units, VREF)[0] for v in vin]
    assert list(fast) == slow


def test_a_non_monotonic_array_is_refused():
    """A missing code makes the lookup ambiguous, and the part is scrap anyway.
    Returning a number here would be inventing one."""
    units = ideal_units(N_BITS)
    units[2 ** (N_BITS - 1) - 1 :] *= SHRINK
    with pytest.raises(ValueError):
        codes_from_curve(coherent_sine(), units, VREF)


def test_backing_off_the_rails_does_not_change_the_verdict():
    """The full-scale correction is what makes two records comparable. Without
    it, a smaller stimulus would look like a worse converter."""
    units = ideal_units(N_BITS)
    loud = enob_of(units, amplitude_frac=AMPLITUDE_FRACTION)
    quiet = enob_of(units, amplitude_frac=BACKED_OFF)
    assert np.isclose(loud, quiet, atol=ENOB_TOLERANCE)


def test_mismatch_costs_effective_bits():
    """The connection the static metrics cannot make: matching is not just a
    yield question, it is resolution you paid for and did not get."""
    rng = np.random.default_rng(LOSS_SEED)
    means = []
    for sigma in SIGMAS:
        arrays = random_units(N_BITS, sigma, rng, trials=TRIALS)
        # Arrays with a missing code are scrap and have no defined ENOB, so
        # this is the resolution surviving parts have -- the optimistic view,
        # and it degrades anyway.
        working = arrays[~has_missing_codes(arrays)]
        means.append(float(np.mean([enob_of(u) for u in working])))
    assert means == sorted(means, reverse=True)
    assert means[0] - means[-1] > MIN_LOSS


def test_sndr_and_enob_are_the_same_statement():
    """One is a restatement of the other. If they ever disagree, one of them
    has picked up a stray constant."""
    units = ideal_units(N_BITS)
    assert np.isclose(enob(sndr_db(codes_from_curve(coherent_sine(), units))), enob_of(units))
