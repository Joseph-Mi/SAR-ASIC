"""M3's pass criterion: over a sweep of inputs, the circuit converts what the
golden model converts.

The inputs that matter are the ones next to a threshold, where a small error
in the circuit -- charge not conserved, a branch weighted wrong, a comparator
reading the wrong side -- flips a decision. So every input sits a small,
named distance either side of a threshold: the circuit passes only if its
thresholds are within that distance of the model's.

Conversions run back to back, many to a simulation, the pin changing between
them. The array only sees the pin while sampling, so a batch is as good as
separate runs, and far faster.
"""

from __future__ import annotations

import shutil

import numpy as np
import pytest

import bench
import ngspice
from bench import Bench, Phase, Supplies
from interface import N_BITS
from protocol import EVALUATE, SAMPLE, conversion_sequence
from sar import ideal_units, sar_convert

pytestmark = pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not on PATH")

VDD = 1.8
VREF = 1.0

#: How close to a threshold each input sits, in LSB. The criterion: the
#: circuit's thresholds are within this of the model's. Charge conservation in
#: the solver is good to about a thousandth of an LSB at the target resolution,
#: so this has a wide margin and still catches any real error, all of which
#: are fractions of an LSB or more.
EDGE_OFFSET_LSB = 0.05

#: Small enough to sweep every threshold both sides in one run.
EXHAUSTIVE_BITS = 6

#: At the target resolution every threshold would be slow, so the sweep takes
#: the ones where the most branches change at once -- each bit's carry, where
#: every lower branch switches out and one switches in -- plus a spread of
#: arbitrary ones.
ARBITRARY_CODES = 64
SEED = 20260927

#: Conversions per simulation. Each conversion is fine alone and in batches of
#: tens; a single run of a whole sweep -- thousands of ideal-switch edges over
#: tens of microseconds -- eventually wedges the solver's timestep control
#: ("timestep too small") on some edge that is harmless in a shorter run.
BATCH = 32

#: A pin level far from the sampled one, applied after sampling. The array
#: must not see it.
DISTURBANCE = 0.9

#: Phases after the sample before the pin may move. The sampling switch opens
#: on the edge that ends the sample phase, and a pin moving on that same edge
#: is sampled mid-move -- the aperture, a real constraint on whatever drives
#: the pin, not something this test is about. One clear phase keeps the two
#: apart.
APERTURE_GUARD = 1


def lsb(n_bits: int) -> float:
    return VREF / 2**n_bits


def carry_codes(n_bits: int) -> list[int]:
    """Codes whose lower threshold is a carry: 2^k, and the top code."""
    return sorted({1 << k for k in range(n_bits)} | {2**n_bits - 1})


def either_side(codes, n_bits: int) -> list[float]:
    """An input just below and just above each code's lower threshold."""
    step = lsb(n_bits)
    return [
        k * step + sign * EDGE_OFFSET_LSB * step for k in codes for sign in (-1, +1) if k > 0
    ] + [EDGE_OFFSET_LSB * step]


def convert_all(inputs, n_bits, tmp_path, after_sampling=None) -> list[list[int]]:
    """Every conversion's decisions, in order, run in batches."""
    return [
        trace
        for start in range(0, len(inputs), BATCH)
        for trace in convert_batch(inputs[start : start + BATCH], n_bits, tmp_path, after_sampling)
    ]


def convert_batch(inputs, n_bits, tmp_path, after_sampling=None) -> list[list[int]]:
    """Run these conversions in one simulation; return each one's decisions.

    `after_sampling` moves the pin to that level once each sample is taken
    and the aperture guard has passed.
    """
    units = ideal_units(n_bits)
    phases, evaluate = [], []
    for vin in inputs:
        for i, step in enumerate(conversion_sequence(vin, units, VREF)):
            held = step.phase == SAMPLE or i <= APERTURE_GUARD
            pin = vin if held or after_sampling is None else after_sampling
            if step.phase == EVALUATE:
                evaluate.append(len(phases))
            phases.append(
                Phase(sample=step.sample, dac_b=step.dac_b, cmp_clk=step.cmp_clk, vin=pin)
            )
    b = Bench(
        phases,
        Supplies(vdd=VDD, vref=VREF),
        n_bits,
        read=evaluate,
        probes={"m_cmp": bench.PROBES["m_cmp"]},
    )
    seen = [int(v > VDD / 2) for v in ngspice.run(bench.deck(b), tmp_path)["m_cmp"]]
    return [seen[i : i + n_bits] for i in range(0, len(seen), n_bits)]


def model(inputs, n_bits) -> list[list[int]]:
    units = ideal_units(n_bits)
    return [sar_convert(vin, units, VREF)[1] for vin in inputs]


def code_of(trace) -> int:
    return int("".join(map(str, trace)), 2)


def mismatches(inputs, got, want, n_bits) -> list[str]:
    return [
        f"vin={vin / lsb(n_bits):.3f} LSB: circuit {code_of(g)} model {code_of(w)}"
        for vin, g, w in zip(inputs, got, want, strict=True)
        if g != w
    ]


def test_every_threshold_both_sides_at_a_small_resolution(tmp_path):
    inputs = either_side(range(2**EXHAUSTIVE_BITS), EXHAUSTIVE_BITS)
    got = convert_all(inputs, EXHAUSTIVE_BITS, tmp_path)
    assert not mismatches(inputs, got, model(inputs, EXHAUSTIVE_BITS), EXHAUSTIVE_BITS)


def test_carries_and_a_spread_both_sides_at_the_target_resolution(tmp_path):
    rng = np.random.default_rng(SEED)
    arbitrary = rng.choice(np.arange(1, 2**N_BITS), ARBITRARY_CODES, replace=False)
    codes = sorted(set(carry_codes(N_BITS)) | {int(c) for c in arbitrary})
    inputs = either_side(codes, N_BITS)
    got = convert_all(inputs, N_BITS, tmp_path)
    assert not mismatches(inputs, got, model(inputs, N_BITS), N_BITS)


def test_the_codes_step_by_one_across_each_threshold(tmp_path):
    """Read as codes rather than decisions: just below a threshold is the code
    under it, just above is the code itself -- no missing and no repeated
    codes where the model has none."""
    codes = carry_codes(N_BITS)
    inputs = either_side(codes, N_BITS)
    got = [code_of(t) for t in convert_all(inputs, N_BITS, tmp_path)]
    pairs = dict(zip(inputs, got, strict=True))
    step = lsb(N_BITS)
    for k in codes:
        below = pairs[k * step - EDGE_OFFSET_LSB * step]
        above = pairs[k * step + EDGE_OFFSET_LSB * step]
        assert (below, above) == (k - 1, k), f"threshold {k}"


def test_the_held_sample_ignores_the_pin_after_sampling(tmp_path):
    """The comparator never sees the pin. Once sampling ends the input is
    charge on the array, so moving the pin mid-conversion changes nothing."""
    inputs = either_side(carry_codes(N_BITS), N_BITS)
    got = convert_all(inputs, N_BITS, tmp_path, after_sampling=DISTURBANCE * VREF)
    assert not mismatches(inputs, got, model(inputs, N_BITS), N_BITS)
