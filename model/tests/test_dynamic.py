"""ENOB is the claim a resolution makes. These pin what it is measured against."""

import numpy as np
import pytest

from dynamic import CYCLES, codes_from_curve, coherent_sine, enob, enob_of, sndr_db
from metrics import has_missing_codes
from mismatch import random_units
from sar import ideal_units, sar_convert

RESOLUTIONS = (4, 8, 10)
VREF = 1.0


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_a_perfect_array_is_worth_its_nominal_bits(n_bits):
    """The end-to-end check. A perfect N-bit array must measure N effective
    bits, because quantisation is the only error left in it.

    The tolerance is not measurement slop. The ideal-SNDR constants assume
    quantisation error is uniform and uncorrelated with the input, which a
    coarse quantiser driven by a pure tone only approximately obeys. The
    residual grows at both ends of the resolution range.
    """
    assert np.isclose(enob_of(ideal_units(n_bits)), n_bits, atol=0.1)


def test_the_stimulus_lands_in_exactly_one_bin():
    """Coherence, before any converter is involved. An incoherent record would
    smear the tone and be scored as distortion the array never produced."""
    spectrum = np.abs(np.fft.rfft(coherent_sine() - coherent_sine().mean())) ** 2
    assert spectrum[CYCLES] / spectrum.sum() > 1 - 1e-12


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_the_lookup_agrees_with_the_search_on_an_ideal_array(n_bits):
    """The fast path exists to avoid one binary search per sample, so it has
    to give what those searches would."""
    units = ideal_units(n_bits)
    vin = coherent_sine(n_samples=256, cycles=31, vref=VREF)
    fast = codes_from_curve(vin, units, VREF)
    slow = [sar_convert(v, units, VREF)[0] for v in vin]
    assert list(fast) == slow


def test_the_lookup_agrees_with_the_search_under_mismatch():
    """Mismatch moves the transitions. Both routes have to move with them."""
    units = random_units(8, 0.02, np.random.default_rng(11))
    vin = coherent_sine(n_samples=256, cycles=31, vref=VREF)
    fast = codes_from_curve(vin, units, VREF)
    slow = [sar_convert(v, units, VREF)[0] for v in vin]
    assert list(fast) == slow


def test_a_non_monotonic_array_is_refused():
    """A missing code makes the lookup ambiguous, and the part is scrap anyway.
    Returning a number here would be inventing one."""
    units = ideal_units(8)
    units[2**7 - 1 :] *= 0.9
    with pytest.raises(ValueError):
        codes_from_curve(coherent_sine(), units, VREF)


def test_backing_off_the_rails_does_not_change_the_verdict():
    """The full-scale correction is what makes two records comparable. Without
    it, a smaller stimulus would look like a worse converter."""
    units = ideal_units(8)
    loud = enob_of(units, amplitude_frac=0.49)
    quiet = enob_of(units, amplitude_frac=0.35)
    assert np.isclose(loud, quiet, atol=0.1)


def test_mismatch_costs_effective_bits():
    """The connection the static metrics cannot make: matching is not just a
    yield question, it is resolution you paid for and did not get."""
    rng = np.random.default_rng(2)
    means = []
    for sigma in (0.0, 0.01, 0.02, 0.04):
        arrays = random_units(8, sigma, rng, trials=24)
        # Arrays with a missing code are scrap and have no defined ENOB, so
        # this is the resolution surviving parts have -- the optimistic view,
        # and it degrades anyway.
        working = arrays[~has_missing_codes(arrays)]
        means.append(float(np.mean([enob_of(u) for u in working])))
    assert means == sorted(means, reverse=True)
    assert means[0] - means[-1] > 0.1


def test_sndr_and_enob_are_the_same_statement():
    """One is a restatement of the other. If they ever disagree, one of them
    has picked up a stray constant."""
    assert np.isclose(
        enob(sndr_db(codes_from_curve(coherent_sine(), ideal_units(8)))), enob_of(ideal_units(8))
    )
