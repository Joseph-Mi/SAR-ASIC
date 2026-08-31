"""Checkpoints for the golden model. These define correct; nothing else does."""

import numpy as np
import pytest

from sar import ideal_units, sar_convert

N_BITS = 8
VREF = 1.0


@pytest.fixture
def units():
    return ideal_units(N_BITS)


def test_zero_input_gives_code_zero(units):
    code, _ = sar_convert(0.0, units, VREF)
    assert code == 0


def test_half_scale_gives_midcode(units):
    code, _ = sar_convert(VREF / 2, units, VREF)
    assert code == 2 ** (N_BITS - 1)


def test_full_scale_gives_top_code(units):
    code, _ = sar_convert(VREF, units, VREF)
    assert code == 2**N_BITS - 1


def test_transfer_curve_is_monotonic(units):
    """With ideal units the code must never decrease as vin rises."""
    sweep = np.linspace(0.0, VREF, 2000)
    codes = np.array([sar_convert(v, units, VREF)[0] for v in sweep])
    assert np.all(np.diff(codes) >= 0)


def test_bit_trace_has_one_entry_per_bit(units):
    """cocotb compares the trace, so its length is part of the contract."""
    _, trace = sar_convert(0.3 * VREF, units, VREF)
    assert len(trace) == N_BITS
