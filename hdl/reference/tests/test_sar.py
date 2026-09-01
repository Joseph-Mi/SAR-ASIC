"""Checkpoints for the golden model. These define correct; nothing else does."""

import numpy as np
import pytest

from sar import branch_weights, dac_voltage, ideal_units, n_bits_of, sar_convert

# Every behaviour below is checked at three resolutions, because nothing in the
# model is allowed to be 8-bit-specific: 4 is small enough to check by hand, 8
# is the target, and 10 is the alternative the mismatch study has to weigh.
# A model that silently only works at 8 would turn that comparison into noise.
RESOLUTIONS = (4, 8, 10)
VREF = 1.0


@pytest.fixture(params=RESOLUTIONS)
def units(request):
    return ideal_units(request.param)


def test_zero_input_gives_code_zero(units):
    code, _ = sar_convert(0.0, units, VREF)
    assert code == 0


def test_half_scale_gives_midcode(units):
    code, _ = sar_convert(VREF / 2, units, VREF)
    assert code == 2 ** (n_bits_of(units) - 1)


def test_full_scale_gives_top_code(units):
    code, _ = sar_convert(VREF, units, VREF)
    assert code == 2 ** n_bits_of(units) - 1


def test_out_of_range_input_saturates(units):
    """The FSM has no error output, so over-range has to land on an end code."""
    top = 2 ** n_bits_of(units) - 1
    assert sar_convert(2 * VREF, units, VREF)[0] == top
    assert sar_convert(-VREF, units, VREF)[0] == 0


def test_transfer_curve_is_monotonic(units):
    """With ideal units the code must never decrease as vin rises."""
    sweep = np.linspace(0.0, VREF, 2000)
    codes = np.array([sar_convert(v, units, VREF)[0] for v in sweep])
    assert np.all(np.diff(codes) >= 0)


def test_bit_trace_has_one_entry_per_bit(units):
    """cocotb compares the trace, so its length is part of the contract."""
    _, trace = sar_convert(0.3 * VREF, units, VREF)
    assert len(trace) == n_bits_of(units)


def test_bit_trace_is_msb_first(units):
    """The trace read as a binary number must be the code it produced.

    This pins the ordering cocotb will compare against. Getting it backwards
    would leave the model and the RTL agreeing with each other and both wrong.
    """
    code, trace = sar_convert(0.3 * VREF, units, VREF)
    assert int("".join(str(b) for b in trace), 2) == code


def test_every_code_round_trips(units):
    """Exhaustive at each resolution. The code space is enumerable, so
    sampling it would be a choice to prove less than we can."""
    weights = branch_weights(units)
    total_cap = units.sum()
    for expected in range(2 ** n_bits_of(units)):
        vin = dac_voltage(expected, weights, total_cap, VREF)
        code, _ = sar_convert(vin, units, VREF)
        assert code == expected


def test_offset_shifts_the_curve_without_distorting_it(units):
    """Offset is input-referred and constant, so it can only move the curve.

    Converting vin with an offset must land on the same code as converting
    vin + offset without one. Any disagreement means offset is leaking into
    the bit weights, which would make it a source of DNL.
    """
    offset = 0.01 * VREF
    for vin in np.linspace(0.05 * VREF, 0.85 * VREF, 64):
        with_offset, _ = sar_convert(vin, units, VREF, cmp_offset=offset)
        shifted_input, _ = sar_convert(vin + offset, units, VREF)
        assert with_offset == shifted_input


class OneKick:
    """rng stub: one huge noise draw on the first trial, nothing after.

    A seeded generator cannot say *which* trial went wrong, and the claim
    under test is about a specific one.
    """

    def __init__(self, kick):
        self.kick = kick
        self.draws = 0

    def normal(self, loc, scale):
        self.draws += 1
        return self.kick if self.draws == 1 else 0.0


def test_a_wrong_msb_decision_is_never_corrected(units):
    """No redundancy: a bit decided wrong stays wrong for the whole conversion."""
    n_bits = n_bits_of(units)
    vin = 0.25 * VREF
    truth, _ = sar_convert(vin, units, VREF)
    msb = 1 << (n_bits - 1)
    assert not truth & msb

    rng = OneKick(VREF)
    code, trace = sar_convert(vin, units, VREF, cmp_noise_rms=1e-9, rng=rng)
    assert trace[0] == 1
    assert code & msb
    assert rng.draws == n_bits


def test_noise_without_an_rng_is_refused(units):
    """Reproducibility is a contract, not a convention."""
    with pytest.raises(ValueError):
        sar_convert(0.5 * VREF, units, VREF, cmp_noise_rms=1e-3)


def test_a_non_binary_array_is_refused():
    """Resolution is inferred from the array length, so the length has to mean
    something. A wrong-sized array would otherwise convert at a silently
    wrong resolution."""
    with pytest.raises(ValueError):
        sar_convert(0.5 * VREF, np.ones(100), VREF)
