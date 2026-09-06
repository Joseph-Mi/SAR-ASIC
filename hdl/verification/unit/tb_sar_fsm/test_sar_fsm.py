"""The SAR control FSM, against the golden model's own cycle sequence.

Expectations come from the model, never from this file: a test that defines its
own is a second opinion, not a check. The whole waveform is compared, so an FSM
that reaches the right code by a different route still fails.

Pins are read on the falling edge. Registered outputs settle on the rising one,
so reading there races the update being checked.
"""

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

from interface import N_BITS
from protocol import SAMPLE, TRIAL, code_of, conversion_sequence
from sar import ideal_units
from tb_common import rtl, run

DUT = "sar_fsm"

CLK_PERIOD_NS = 10
RESET_CYCLES = 2
VREF = 1.0

#: Mid-scale is the one that matters: it is the tie the model resolves upward,
#: and resolving it the other way puts every code one low.
PROBE_INPUTS = (0.0, 0.5 * VREF, 0.999 * VREF, 0.123 * VREF, 0.876 * VREF)

STUCK_ANSWERS = (0, 1)


def pins(dut):
    return int(dut.sample_o.value), int(dut.dac_b_o.value), int(dut.cmp_clk_o.value)


def answer(dut, decision):
    """Drive the latch pair for one trial, as a real latch would present it."""
    dut.cmp_out_i.value = decision
    dut.cmp_out_n_i.value = 0 if decision else 1


async def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk_i, CLK_PERIOD_NS, unit="ns").start())
    dut.start_i.value = 0
    answer(dut, 0)
    dut.rst_ni.value = 0
    await ClockCycles(dut.clk_i, RESET_CYCLES)
    await RisingEdge(dut.clk_i)
    dut.rst_ni.value = 1
    await RisingEdge(dut.clk_i)


async def begin(dut):
    """Raise start for one cycle and settle inside the first cycle after it."""
    dut.start_i.value = 1
    await RisingEdge(dut.clk_i)
    dut.start_i.value = 0
    await FallingEdge(dut.clk_i)


async def run_conversion(dut, decisions):
    """One conversion, answering trial j during trial j. Returns every cycle."""
    await begin(dut)
    seen = [pins(dut)]
    for decision in decisions:
        await RisingEdge(dut.clk_i)
        await FallingEdge(dut.clk_i)
        seen.append(pins(dut))
        answer(dut, decision)
    await RisingEdge(dut.clk_i)
    await FallingEdge(dut.clk_i)
    seen.append(pins(dut))
    return seen


@cocotb.test()
async def every_cycle_matches_the_model(dut):
    """The whole waveform, not just the answer."""
    await start_clock(dut)
    units = ideal_units(N_BITS)

    for vin in PROBE_INPUTS:
        steps = conversion_sequence(vin, units, VREF)
        decisions = [s.decision for s in steps if s.phase == TRIAL]
        seen = await run_conversion(dut, decisions)

        expected = [(s.sample, s.dac_b, s.cmp_clk) for s in steps]
        assert seen == expected, f"vin={vin}: pin sequence diverged"
        assert int(dut.code_o.value) == code_of(steps), f"vin={vin}: wrong code"
        await RisingEdge(dut.clk_i)
        await FallingEdge(dut.clk_i)


@cocotb.test()
async def sampling_is_the_first_cycle_and_only_that_cycle(dut):
    """The array cannot be driven to a trial code while still connected to the
    input, so the phases may not overlap by even one cycle."""
    await start_clock(dut)
    steps = conversion_sequence(0.4 * VREF, ideal_units(N_BITS), VREF)
    assert steps[0].phase == SAMPLE

    await begin(dut)
    assert int(dut.sample_o.value) == 1
    assert int(dut.cmp_clk_o.value) == 0

    await RisingEdge(dut.clk_i)
    await FallingEdge(dut.clk_i)
    assert int(dut.sample_o.value) == 0


@cocotb.test()
async def a_conversion_takes_the_sequence_the_model_declares(dut):
    """Counted from the model's sequence, so the test cannot disagree with the
    contract about what the bound is."""
    await start_clock(dut)
    steps = conversion_sequence(0.3 * VREF, ideal_units(N_BITS), VREF)

    await begin(dut)
    cycles = 1
    while not int(dut.done_o.value):
        answer(dut, 1)
        await RisingEdge(dut.clk_i)
        await FallingEdge(dut.clk_i)
        cycles += 1
        assert cycles <= len(steps), "conversion did not finish"
    assert cycles == len(steps)


@cocotb.test()
async def a_stuck_comparator_still_terminates(dut):
    """Termination cannot depend on the answers."""
    await start_clock(dut)
    for stuck in STUCK_ANSWERS:
        await begin(dut)
        answer(dut, stuck)

        cycles = 1
        while not int(dut.done_o.value):
            await RisingEdge(dut.clk_i)
            await FallingEdge(dut.clk_i)
            cycles += 1
            assert cycles <= N_BITS + 2, f"stuck at {stuck} did not terminate"

        expected = (1 << N_BITS) - 1 if stuck else 0
        assert int(dut.code_o.value) == expected, f"stuck at {stuck}: wrong code"
        await RisingEdge(dut.clk_i)
        await FallingEdge(dut.clk_i)


@cocotb.test()
async def equal_latch_outputs_raise_metastable(dut):
    """A conversion that saw an unresolved latch completes but is not
    trustworthy, so it is flagged rather than suppressed."""
    await start_clock(dut)
    await begin(dut)
    assert int(dut.metastable_o.value) == 0

    dut.cmp_out_i.value = 1
    dut.cmp_out_n_i.value = 1
    await RisingEdge(dut.clk_i)
    await FallingEdge(dut.clk_i)
    await RisingEdge(dut.clk_i)
    await FallingEdge(dut.clk_i)
    assert int(dut.metastable_o.value) == 1


@cocotb.test()
async def reset_returns_it_to_ready(dut):
    """Reset is asserted mid-conversion, which is when it has to work."""
    await start_clock(dut)
    await begin(dut)
    await RisingEdge(dut.clk_i)

    dut.rst_ni.value = 0
    await RisingEdge(dut.clk_i)
    await FallingEdge(dut.clk_i)
    assert int(dut.ready_o.value) == 1
    assert int(dut.done_o.value) == 0
    assert int(dut.sample_o.value) == 0
    assert int(dut.dac_b_o.value) == 0


def test_sar_fsm():
    run(DUT, sources=rtl(DUT), parameters={"N_BITS": N_BITS}, test_dir=Path(__file__).parent)
