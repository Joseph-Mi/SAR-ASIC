"""Checkpoints for the golden model. These define correct; nothing else does."""

import numpy as np
import pytest

from sar import branch_weights, dac_voltage, ideal_units, n_bits_of, sar_convert

# Checked at more than one resolution, because nothing in the model may be
# specific to the target: the mismatch study weighs resolutions against each
# other, and a model that quietly worked at only one would turn that comparison
# into noise. The smallest here is small enough to check by hand.
RESOLUTIONS = (4, 8, 10)
VREF = 1.0

#: An input for tests about the conversion's shape rather than its answer:
#: off every threshold at every resolution tested.
VIN = 0.3 * VREF

#: Points in the monotonicity sweep: more than the largest resolution has
#: codes, so every code boundary is crossed.
DENSE_SWEEP = 2000

#: A comparator offset, and the inputs it is checked over: inside the range,
#: with room for the offset to move them without leaving it.
OFFSET = 0.01 * VREF
OFFSET_SWEEP = (0.05 * VREF, 0.85 * VREF, 64)

#: An input below mid-scale, so the true MSB is 0 and a forced 1 is visible.
BELOW_MID = 0.25 * VREF

#: Any non-zero noise: the decision under test comes from the rng's kick, not
#: from the noise's size.
ANY_NOISE = 1e-9

#: An array length that is not a power of two.
NOT_BINARY = 100


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
    sweep = np.linspace(0.0, VREF, DENSE_SWEEP)
    codes = np.array([sar_convert(v, units, VREF)[0] for v in sweep])
    assert np.all(np.diff(codes) >= 0)


def test_bit_trace_has_one_entry_per_bit(units):
    """cocotb compares the trace, so its length is part of the contract."""
    _, trace = sar_convert(VIN, units, VREF)
    assert len(trace) == n_bits_of(units)


def test_bit_trace_is_msb_first(units):
    """The trace read as a binary number must be the code it produced.

    This pins the ordering cocotb will compare against. Getting it backwards
    would leave the model and the RTL agreeing with each other and both wrong.
    """
    code, trace = sar_convert(VIN, units, VREF)
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
    offset = OFFSET
    for vin in np.linspace(*OFFSET_SWEEP):
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
    vin = BELOW_MID
    truth, _ = sar_convert(vin, units, VREF)
    msb = 1 << (n_bits - 1)
    assert not truth & msb

    rng = OneKick(VREF)
    code, trace = sar_convert(vin, units, VREF, cmp_noise_rms=ANY_NOISE, rng=rng)
    assert trace[0] == 1
    assert code & msb
    assert rng.draws == n_bits


def test_noise_without_an_rng_is_refused(units):
    """Reproducibility is a contract, not a convention."""
    with pytest.raises(ValueError):
        sar_convert(VIN, units, VREF, cmp_noise_rms=ANY_NOISE)


def test_a_non_binary_array_is_refused():
    """Resolution is inferred from the array length, so the length has to mean
    something. A wrong-sized array would otherwise convert at a silently
    wrong resolution."""
    with pytest.raises(ValueError):
        sar_convert(VIN, np.ones(NOT_BINARY), VREF)
