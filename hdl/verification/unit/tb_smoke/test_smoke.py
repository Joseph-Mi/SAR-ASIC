"""Toolchain smoke test: proves Verilator, cocotb, and pytest are wired up.

Delete this directory once real RTL has its own unit tests.
"""

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

from tb_common import run

DUT = "smoke_dut"
DUT_SOURCE = Path(__file__).parent / f"{DUT}.v"

N_BITS = 8
CLK_PERIOD_NS = 10
RESET_CYCLES = 2
COUNT_RESET = 0

#: Arbitrary but named: how many cycles each directed test runs the counter.
ENABLED_CYCLES = 5
DISABLED_CYCLES = 4


async def reset(dut):
    """Hold the counter in reset, then release it on a clock edge.

    Leaves the DUT disabled so a caller sets en_i when it is ready to count.
    """
    dut.en_i.value = 0
    dut.rst_ni.value = 0
    await ClockCycles(dut.clk_i, RESET_CYCLES)
    await RisingEdge(dut.clk_i)
    dut.rst_ni.value = 1
    await RisingEdge(dut.clk_i)


async def start(dut):
    cocotb.start_soon(Clock(dut.clk_i, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)


@cocotb.test()
async def test_reset_clears_count(dut):
    await start(dut)
    got = int(dut.count_o.value)
    assert got == COUNT_RESET, f"count after reset: expected {COUNT_RESET}, got {got}"


@cocotb.test()
async def test_counts_when_enabled(dut):
    await start(dut)

    dut.en_i.value = 1
    await ClockCycles(dut.clk_i, ENABLED_CYCLES)
    await RisingEdge(dut.clk_i)

    got = int(dut.count_o.value)
    assert got == ENABLED_CYCLES, (
        f"count after {ENABLED_CYCLES} enabled cycles: expected {ENABLED_CYCLES}, got {got}"
    )


@cocotb.test()
async def test_holds_when_disabled(dut):
    await start(dut)

    dut.en_i.value = 1
    await ClockCycles(dut.clk_i, ENABLED_CYCLES)
    dut.en_i.value = 0
    await RisingEdge(dut.clk_i)
    held = int(dut.count_o.value)

    await ClockCycles(dut.clk_i, DISABLED_CYCLES)
    got = int(dut.count_o.value)
    assert got == held, f"count moved while disabled: expected {held}, got {got}"


def test_smoke():
    run(DUT, sources=[DUT_SOURCE], parameters={"N_BITS": N_BITS})
