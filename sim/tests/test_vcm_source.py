"""The common mode's source: what its accuracy and its movement cost.

Vcm cancels out of every decision when it is the same at sampling and at the
comparison, so an inaccurate but steady Vcm must convert exactly as the model
does. A Vcm that sampling kicks and that is still recovering afterwards shifts
the thresholds by what it recovers -- and the kick is the array pushing charge
into it as the bottom plates move from the last conversion's code to the new
input, so it scales with how far the input moved, not with the reference.
"""

from __future__ import annotations

import math
import shutil

import pytest

import analog
import bench
import ngspice
from bench import Bench, Phase, Supplies
from common_mode import divider, drift_within_conversion, loaded_reference
from interface import N_BITS
from sar import VCM_FRACTION
from settling import settle_time
from sweep import EDGE_OFFSET_LSB, VDD, VREF, convert, lsb, mismatches, model

pytestmark = pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not on PATH")

UNIT = analog.DEFAULT_UNIT.farads
C_TOTAL = 2**N_BITS * UNIT

#: Vcm off its nominal fraction of the reference by this much, either way, and
#: held there. Small enough that the top plate stays in its range; the claim is
#: that it converts identically, so any error at all would show.
WRONG_BY = 0.05

#: The divider's time constant as a fraction of one sample phase. Sampling
#: leaves e^-5 of each kick: well under the sweep's tolerance for a kick of an
#: LSB or two, well over it for one of tens.
SAMPLE_OVER_TAU = 5.0
TAU = bench.PHASE / SAMPLE_OVER_TAU
FRACTION = VCM_FRACTION
R_TOTAL = TAU / (C_TOTAL * FRACTION * (1 - FRACTION))

#: A block of consecutive codes near mid-scale. In order, the input moves by
#: about an LSB per conversion; zig-zagged end to end, by about the block.
FIRST_CODE = 2 ** (N_BITS - 1) - 16
BLOCK = 32

#: The gain error to provoke by hanging the divider on a resistive reference
#: pin, in LSB at full scale: large enough that every threshold in the block
#: moves by a sizeable fraction of an LSB, so comparing against the unloaded
#: reference cannot pass.
SAG_LSB = 2.0

#: Two phase lengths, in multiples of TAU, for reading a time constant off the
#: ratio of what is left, and the tolerance on it; as in the settling tests.
SHORT, LONG = 2.0, 5.0
TAU_TOLERANCE = 0.01


def settled_for(phase: float) -> float:
    return phase * (1 - bench.READ_BEFORE_END) - bench.EDGE / 2


def in_order(vref: float = VREF) -> list[float]:
    """Just below and just above each threshold in the block, ascending, for
    thresholds set by `vref`."""
    step = lsb(N_BITS, vref)
    return [
        k * step + sign * EDGE_OFFSET_LSB * step
        for k in range(FIRST_CODE, FIRST_CODE + BLOCK)
        for sign in (-1, +1)
    ]


def zig_zag(values: list[float]) -> list[float]:
    """The same inputs, alternating from the two ends inward."""
    ordered = sorted(values)
    out = []
    while ordered:
        out.append(ordered.pop(0))
        if ordered:
            out.append(ordered.pop())
    return out


def largest_step(inputs: list[float]) -> float:
    return max(abs(b - a) for a, b in zip(inputs, inputs[1:], strict=False))


def holds(inputs, tmp_path, vref_model: float = VREF, **bench_args) -> bool:
    got = convert(inputs, N_BITS, tmp_path, model_vref=vref_model, **bench_args)
    return not mismatches(inputs, got, model(inputs, N_BITS, vref_model), N_BITS)


@pytest.mark.parametrize("sign", [-1, +1])
def test_a_steady_but_wrong_vcm_converts_exactly_as_the_model(sign, tmp_path):
    vcm = bench.IdealVcm(FRACTION + sign * WRONG_BY)
    assert holds(in_order(), tmp_path, vcm=vcm)


def test_the_divider_tap_recovers_through_its_halves_in_parallel(tmp_path):
    """One kick, read at two times: the tap recovers with its Thevenin
    resistance charging the whole array."""
    r_th, _ = divider(R_TOTAL, VREF, FRACTION)
    settled = FRACTION * VREF
    gaps = []
    for k in (SHORT, LONG):
        phases = [Phase(sample=1, vin=0.2 * VREF), Phase(sample=1, vin=0.7 * VREF)]
        b = Bench(
            phases,
            Supplies(vdd=VDD, vref=VREF),
            N_BITS,
            phase=k * TAU,
            vcm=bench.Divider(R_TOTAL, FRACTION),
            probes={"m_vcm": "v(vcm)"},
        )
        gaps.append(abs(ngspice.run(bench.deck(b), tmp_path)["m_vcm"][-1] - settled))
    measured = (settled_for(LONG * TAU) - settled_for(SHORT * TAU)) / math.log(gaps[0] / gaps[1])
    assert measured == pytest.approx(r_th * C_TOTAL, rel=TAU_TOLERANCE)


def predicted_shift(step: float, c_dec: float = 0.0) -> float:
    r_th, _ = divider(R_TOTAL, VREF, FRACTION)
    conversion = (2 * N_BITS + 1) * bench.PHASE
    return drift_within_conversion(step, C_TOTAL, c_dec, r_th, settled_for(bench.PHASE), conversion)


def test_the_kick_is_the_input_moving_not_the_reference(tmp_path):
    """The same inputs through the same divider: in order they convert, zig-
    zagged they do not -- and the model says so before the circuit does. The
    kick carries up to an LSB of the last code's rounding and the dummy's
    return from ground, on top of the input's own move. The reference is ideal
    here, so the string's current has no pin to sag across: the only thing
    under test is the kick."""
    tolerance = EDGE_OFFSET_LSB * lsb(N_BITS)
    ordered, jumping = in_order(), zig_zag(in_order())
    slack = 2 * lsb(N_BITS)
    assert predicted_shift(largest_step(ordered) + slack) < tolerance
    assert predicted_shift(largest_step(jumping)) > tolerance

    divided = bench.Divider(R_TOTAL, FRACTION)
    assert holds(ordered, tmp_path, vcm=divided)
    assert not holds(jumping, tmp_path, vcm=divided)


def test_a_divider_on_the_reference_pin_is_a_gain_error(tmp_path):
    """The string's current crosses the reference pin and the array's
    reference sags by it. The circuit then converts exactly as the model does
    against the sagged reference -- and not against the source's."""
    sagged = VREF - SAG_LSB * lsb(N_BITS)
    r_pin = R_TOTAL * (VREF / sagged - 1)
    assert loaded_reference(VREF, R_TOTAL, r_pin) == pytest.approx(sagged)

    inputs = in_order(sagged)
    divided = bench.Divider(R_TOTAL, FRACTION)
    assert holds(inputs, tmp_path, vref_model=sagged, vcm=divided, r_vref=r_pin)
    assert not holds(inputs, tmp_path, vref_model=VREF, vcm=divided, r_vref=r_pin)


def test_the_pin_converts_what_defeated_the_divider_given_the_sampling_law(tmp_path):
    """Driven off-chip and decoupled there, the pin's only cost is its own
    resistance: the kick settles through it with the whole array, the same
    law as sampling Vin. Given that law's phase, the zig-zag the divider could
    not convert converts; given half of it, it does not."""
    r_pin = TAU / C_TOTAL
    law = settle_time(r_pin * C_TOTAL, VREF, EDGE_OFFSET_LSB * lsb(N_BITS))
    jumping = zig_zag(in_order())
    pinned = bench.PinVcm(r_pin, FRACTION)
    assert holds(jumping, tmp_path, vcm=pinned, phase=law)
    assert not holds(jumping, tmp_path, vcm=pinned, phase=law / 2)
