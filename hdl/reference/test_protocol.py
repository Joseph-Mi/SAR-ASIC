"""The wire-level contract. cocotb will assert exactly these things against RTL."""

import numpy as np
import pytest

from protocol import DONE, SAMPLE, TRIAL, code_of, conversion_sequence, trace_of
from sar import ideal_units, n_bits_of, sar_convert

RESOLUTIONS = (4, 8, 10)
VREF = 1.0


@pytest.fixture(params=RESOLUTIONS)
def units(request):
    return ideal_units(request.param)


def test_a_conversion_takes_n_plus_two_cycles(units):
    """The FSM's termination bound. A conversion that needs more has hung."""
    steps = conversion_sequence(0.3 * VREF, units, VREF)
    assert len(steps) == n_bits_of(units) + 2


def test_the_phases_run_sample_then_trials_then_done(units):
    steps = conversion_sequence(0.3 * VREF, units, VREF)
    phases = [s.phase for s in steps]
    assert phases[0] == SAMPLE
    assert phases[-1] == DONE
    assert set(phases[1:-1]) == {TRIAL}


def test_sample_and_strobe_never_overlap(units):
    """Strobing the comparator while the array is still tracking the input
    would latch a voltage that is not the sampled one."""
    for step in conversion_sequence(0.3 * VREF, units, VREF):
        assert not (step.sample and step.cmp_clk)


def test_the_comparator_is_strobed_once_per_bit(units):
    steps = conversion_sequence(0.3 * VREF, units, VREF)
    assert sum(s.cmp_clk for s in steps) == n_bits_of(units)


def test_trials_walk_the_bits_msb_first(units):
    steps = conversion_sequence(0.3 * VREF, units, VREF)
    trials = [s for s in steps if s.phase == TRIAL]
    assert [s.bit_index for s in trials] == list(range(n_bits_of(units) - 1, -1, -1))


def test_each_trial_word_is_the_settled_bits_plus_the_one_under_test(units):
    """This is the array's actual drive word, so a wrong one converges to a
    wrong answer without ever looking wrong at the top level."""
    steps = conversion_sequence(0.3 * VREF, units, VREF)
    settled = 0
    for step in steps:
        if step.phase != TRIAL:
            continue
        assert step.dac_b == settled | (1 << step.bit_index)
        if step.decision:
            settled = step.dac_b


def test_the_sequence_and_the_conversion_cannot_disagree(units):
    """Two views of one conversion. The trace is reconstructed from the same
    decisions, so a divergence means the reconstruction is wrong."""
    for vin in np.linspace(0.0, VREF, 37):
        code, trace = sar_convert(vin, units, VREF)
        steps = conversion_sequence(vin, units, VREF)
        assert trace_of(steps) == trace
        assert code_of(steps) == code


def test_the_settled_word_is_left_driving_the_array(units):
    """The array holds the result after the last trial; the FSM does not have
    to re-drive it, and the top plate must not move while it is read out."""
    steps = conversion_sequence(0.3 * VREF, units, VREF)
    assert steps[-1].dac_b == code_of(steps)
    assert steps[-1].cmp_clk == 0


def test_comparator_imperfections_reach_the_sequence(units):
    """Offset has to move the waveform, not just the return value, or the
    testbench cannot exercise a comparator that is off."""
    clean = conversion_sequence(0.3 * VREF, units, VREF)
    offset = conversion_sequence(0.3 * VREF, units, VREF, cmp_offset=0.05 * VREF)
    assert code_of(offset) != code_of(clean)
