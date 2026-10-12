"""Sampling noise, and whether this array has to care about it."""

from __future__ import annotations

import math

import pytest

import sky130
from interface import N_BITS
from noise import (
    BOLTZMANN,
    ROOM,
    capacitance_for_noise,
    sampled_noise,
    sampled_noise_lsb,
)

VREF = 1.0

#: The array this design builds, farads: the smallest unit the process draws,
#: one per code.
ARRAY = 2**N_BITS * sky130.mim_unit()

#: Fraction of an LSB a sampling term has to stay under to be ignorable
#: beside quantisation, which contributes a twelfth of an LSB squared.
IGNORABLE = 0.1

#: Resolutions far enough apart that the quadratic cost is unmistakable.
COARSE, FINE = 10, 14


def test_the_array_this_design_builds_is_not_noise_limited():
    """The question worth asking of it. The array is set by matching and by
    settling; this says whether sampling noise also has a claim on it, and at
    this resolution it does not."""
    assert sampled_noise_lsb(ARRAY, N_BITS, VREF) < IGNORABLE


def test_the_same_array_is_noisier_at_a_finer_resolution():
    """Which is how a converter becomes noise limited without anything about
    it changing: the volts are fixed by the array and the LSB is not."""
    coarse = sampled_noise_lsb(ARRAY, COARSE, VREF)
    fine = sampled_noise_lsb(ARRAY, FINE, VREF)
    assert fine == pytest.approx(coarse * 2 ** (FINE - COARSE))


def test_the_noise_is_the_law_and_not_an_approximation_of_it():
    assert sampled_noise(ARRAY) == pytest.approx(math.sqrt(BOLTZMANN * ROOM / ARRAY))
    assert sampled_noise(4 * ARRAY) == pytest.approx(sampled_noise(ARRAY) / 2)


def test_buying_quiet_costs_capacitance_quadratically():
    """And why a noise-limited converter gets expensive two bits at a time."""
    budget = capacitance_for_noise(IGNORABLE, N_BITS, VREF)
    assert sampled_noise_lsb(budget, N_BITS, VREF) == pytest.approx(IGNORABLE)
    assert capacitance_for_noise(IGNORABLE / 2, N_BITS, VREF) == pytest.approx(4 * budget)
    assert capacitance_for_noise(IGNORABLE, N_BITS + 1, VREF) == pytest.approx(4 * budget)


def test_the_hot_corner_barely_moves_it():
    """A noise figure goes as the root of absolute temperature, so the span a
    part is specified over is worth a few percent and is not what decides an
    array."""
    hot = sampled_noise(ARRAY, ROOM + 100.0)
    assert hot / sampled_noise(ARRAY) < 1.2


@pytest.mark.parametrize(
    "call",
    [
        lambda: sampled_noise(0.0),
        lambda: sampled_noise(ARRAY, 0.0),
        lambda: capacitance_for_noise(0.0, N_BITS),
    ],
)
def test_an_impossible_budget_is_refused(call):
    with pytest.raises(ValueError):
        call()
