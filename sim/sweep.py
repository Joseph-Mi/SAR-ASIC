"""Convert many inputs through the circuit and compare against the model.

The inputs that matter are the ones next to a threshold, where a small error
in the circuit -- charge not conserved, a branch weighted wrong, a node not
settled -- flips a decision. So inputs sit a small, named distance either side
of a threshold, and the circuit agrees with the model only if its thresholds
are within that distance of the model's.

Conversions run back to back, many to a simulation, the pin changing between
them. The array only sees the pin while sampling, so a batch is as good as
separate runs, and far faster -- and it is also the only honest way to test
sampling that does not settle, whose error depends on the conversion before.
"""

from __future__ import annotations

import pathlib

import bench
import ngspice
from bench import Bench, Phase, Supplies
from protocol import EVALUATE, SAMPLE, conversion_sequence
from sar import ideal_units, sar_convert

VDD = 1.8
VREF = 1.0

#: How close to a threshold each input sits, in LSB. The criterion: the
#: circuit's thresholds are within this of the model's. Charge conservation in
#: the solver is good to about a thousandth of an LSB at the target resolution,
#: so this has a wide margin and still catches any real error.
EDGE_OFFSET_LSB = 0.05

#: Conversions per simulation. Each conversion is fine alone and in batches of
#: tens; a single run of a whole sweep -- thousands of ideal-switch edges over
#: tens of microseconds -- eventually wedges the solver's timestep control
#: ("timestep too small") on some edge that is harmless in a shorter run.
BATCH = 32

#: Phases after the sample before the pin may move. The sampling switch opens
#: on the edge that ends the sample phase, and a pin moving on that same edge
#: is sampled mid-move -- the aperture, a real constraint on whatever drives
#: the pin. One clear phase keeps the two apart.
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


def convert(
    inputs, n_bits: int, workdir: pathlib.Path, after_sampling=None, **bench_args
) -> list[list[int]]:
    """Every conversion's decisions, in order, run in batches.

    `after_sampling` moves the pin to that level once each sample is taken
    and the aperture guard has passed. `bench_args` go to every `Bench`:
    resistances, phase length, capacitor unit.
    """
    return [
        trace
        for start in range(0, len(inputs), BATCH)
        for trace in _batch(
            inputs[start : start + BATCH], n_bits, workdir, after_sampling, bench_args
        )
    ]


def _batch(inputs, n_bits, workdir, after_sampling, bench_args) -> list[list[int]]:
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
        **bench_args,
    )
    seen = [int(v > VDD / 2) for v in ngspice.run(bench.deck(b), workdir)["m_cmp"]]
    return [seen[i : i + n_bits] for i in range(0, len(seen), n_bits)]


def model(inputs, n_bits: int) -> list[list[int]]:
    units = ideal_units(n_bits)
    return [sar_convert(vin, units, VREF)[1] for vin in inputs]


def code_of(trace) -> int:
    return int("".join(map(str, trace)), 2)


def mismatches(inputs, got, want, n_bits: int) -> list[str]:
    return [
        f"vin={vin / lsb(n_bits):.3f} LSB: circuit {code_of(g)} model {code_of(w)}"
        for vin, g, w in zip(inputs, got, want, strict=True)
        if g != w
    ]
