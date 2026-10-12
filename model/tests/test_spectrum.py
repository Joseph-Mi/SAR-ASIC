"""The spectral figures, held to what each one is supposed to isolate.

A single SNDR number can be right while the decomposition behind it is wrong,
and the decomposition is the part that says what to fix. So each figure is
driven with a record built to contain exactly one thing.
"""

from __future__ import annotations

import numpy as np
import pytest

from spectrum import (
    AMPLITUDE_FRACTION,
    CYCLES,
    DB_PER_BIT,
    HARMONIC_ORDER,
    PERFECT_DB,
    RECORD,
    SINE_HEADROOM_DB,
    coherent_sine,
    enob,
    harmonic_bins,
    harmonic_power,
    power_spectrum,
    sfdr_db,
    sndr_db,
    snr_db,
    thd_db,
    worst_spur,
)

VREF = 1.0

#: Harmonic amplitudes to inject, as a fraction of the tone. Large enough to
#: stand clear of a double-precision floor, small enough not to clip.
STRONG, WEAK = 1e-2, 1e-4

#: A bin that is neither the tone nor any harmonic of it: a spur SNDR counts
#: and THD must not.
SPUR_BIN = 7
SPUR_FRACTION = 1e-3

#: dB of agreement demanded where two routes compute the same ratio.
CLOSE_DB = 1e-6

#: dB a figure must clear to count as "nothing there". A record of exact
#: doubles has a floor many orders below any converter's.
EMPTY_DB = 200.0

#: Bits to round a record to when a test needs a real broadband floor under
#: the thing it injected. Quantisation is the floor a converter actually has.
FLOOR_BITS = 8


def tone(cycles: int = CYCLES, amplitude: float = AMPLITUDE_FRACTION) -> np.ndarray:
    return coherent_sine(RECORD, cycles, VREF, amplitude)


def with_harmonic(order: int, fraction: float, cycles: int = CYCLES) -> np.ndarray:
    """A tone plus one harmonic of a known size. Not quantised: the point is to
    put a known amount of energy in a known bin and read it back."""
    n = np.arange(RECORD)
    base = np.sin(2 * np.pi * cycles * n / RECORD)
    added = np.sin(2 * np.pi * order * cycles * n / RECORD)
    return AMPLITUDE_FRACTION * (base + fraction * added)


def test_the_default_record_keeps_every_harmonic_separable():
    """The one way a changed cycle count breaks every distortion figure at
    once: a harmonic folding onto the tone or onto DC."""
    bins = harmonic_bins(CYCLES, RECORD, HARMONIC_ORDER)
    assert len(bins) == HARMONIC_ORDER - 1
    assert len(set(bins.values())) == len(bins)
    assert CYCLES not in bins.values()
    assert 0 not in bins.values()


def test_a_cycle_count_that_folds_a_harmonic_onto_the_tone_is_refused():
    """A third of the record puts the third harmonic back on the fundamental.
    Reported against, every distortion figure would read as perfect."""
    with pytest.raises(ValueError, match="folds onto"):
        harmonic_bins(RECORD // 4, RECORD, HARMONIC_ORDER)


def test_a_harmonic_lands_in_the_bin_the_aliasing_rule_names():
    """Above Nyquist a harmonic folds back, so its bin is not its order times
    the tone's -- and reading it at the unfolded bin would find nothing."""
    bins = harmonic_bins(CYCLES, RECORD, HARMONIC_ORDER)
    for order, where in bins.items():
        spectrum = power_spectrum(with_harmonic(order, STRONG))
        loudest = int(np.argmax(np.delete(spectrum, CYCLES)))
        loudest += 1 if loudest >= CYCLES else 0
        assert loudest == where, order


def test_a_pure_tone_has_nothing_in_it_to_report():
    """Every figure's denominator is empty, so each is infinite rather than a
    large number that depends on the arithmetic's floor."""
    record = tone()
    assert sndr_db(record) > EMPTY_DB
    assert thd_db(record) < -EMPTY_DB
    assert sfdr_db(record) > EMPTY_DB


def test_total_harmonic_distortion_reads_back_the_harmonic_put_in():
    """One harmonic at a known fraction of the tone is a known THD, which is
    what makes the figure a measurement rather than a number."""
    for fraction in (STRONG, WEAK):
        record = with_harmonic(3, fraction)
        assert np.isclose(thd_db(record), 20 * np.log10(fraction), atol=1e-3)


def test_distortion_counts_harmonics_and_noise_does_not():
    """The split that makes the pair worth reporting: a record whose only
    defect is a harmonic has to show up in one and not the other."""
    record = with_harmonic(3, STRONG)
    assert thd_db(record) < -EMPTY_DB / 10
    assert snr_db(record) > EMPTY_DB
    assert sndr_db(record) < snr_db(record)


def test_a_spur_that_is_not_a_harmonic_is_counted_by_everything_but_distortion():
    """Coupling is not distortion of the signal path, and a figure set that
    cannot tell them apart cannot point at the cause."""
    n = np.arange(RECORD)
    spur = AMPLITUDE_FRACTION * SPUR_FRACTION
    record = tone() + spur * np.sin(2 * np.pi * SPUR_BIN * n / RECORD)
    assert thd_db(record) < -EMPTY_DB
    assert snr_db(record) < EMPTY_DB
    where, _ = worst_spur(record)
    assert where == SPUR_BIN
    assert np.isclose(sfdr_db(record), -20 * np.log10(SPUR_FRACTION), atol=1e-3)


def test_the_worst_spur_is_what_sets_the_spur_free_range():
    """Two defects of different sizes: the figure reports the larger, because
    a dynamic range is limited by the worst thing in it."""
    record = with_harmonic(3, STRONG) + 0.0
    louder = with_harmonic(3, STRONG)
    quieter = with_harmonic(3, WEAK)
    assert sfdr_db(quieter) > sfdr_db(louder)
    assert np.isclose(sfdr_db(record), sfdr_db(louder), atol=CLOSE_DB)


def test_signal_to_noise_and_distortion_is_the_whole_of_the_rest():
    """SNDR counts everything that is not the tone. Adding the harmonic power
    back to the noise power has to reconstruct it, or the two figures are
    measuring overlapping or disjoint sets of bins."""
    quantised = np.round(with_harmonic(3, STRONG) * 2**FLOOR_BITS)
    record = quantised
    spectrum = power_spectrum(record)
    signal = spectrum[CYCLES]
    harmonics = sum(harmonic_power(record).values())
    rest = spectrum[1:].sum() - signal
    assert np.isclose(10 * np.log10(signal / rest), sndr_db(record), atol=CLOSE_DB)
    assert np.isclose(10 * np.log10(signal / (rest - harmonics)), snr_db(record), atol=CLOSE_DB)


def test_effective_bits_inverts_the_ideal_quantiser():
    """The constant that connects dB to bits, checked in the direction it is
    used: an SNDR equal to an N-bit quantiser's reports N bits."""
    for n_bits in (8, 10, 12):
        ideal = DB_PER_BIT * n_bits + SINE_HEADROOM_DB
        assert np.isclose(enob(ideal, amplitude_frac=0.5), n_bits)


def test_a_figure_with_an_empty_denominator_is_infinite_not_large():
    assert sndr_db(tone()) == PERFECT_DB or sndr_db(tone()) > EMPTY_DB
