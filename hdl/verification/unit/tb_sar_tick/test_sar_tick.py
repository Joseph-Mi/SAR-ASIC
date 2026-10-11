"""The conversion clock, against the model that declares what its rate means.

Every cycle is compared, not every interval: a counter that reloads from the
wrong value keeps the right average rate and gets every individual interval
wrong, which is what the array would feel.

The rate the part comes up at is the only rate reset can leave behind -- the
counter reloads from the field's reset value, and the field holds it. So a
test at any other rate asks for it the way a host does, and waits out the
interval already in flight before measuring.

tick_o is combinational on the counter, so it is read on the falling edge: it
belongs to the cycle it is read in, and the rising edge is where it changes.
"""

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

from registers import BY_NAME
from tb_common import rtl, run
from tick import DIVISOR_FIELD, MAX_DIVISOR, RESET_DIVISOR, Tick, period

DUT = "sar_tick"

CLK_PERIOD_NS = 10
RESET_CYCLES = 2

#: Rates to check, both ends of the field and some of the middle. A power of two
#: and its neighbours, because an off-by-one in the reload shows up first where
#: the count rolls over.
DIVISORS = (0, 1, 2, 3, 7, 8, 9, MAX_DIVISOR)

#: Intervals to measure before believing they are all the same length.
INTERVALS = 4

#: Cycles into an interval that a rate change is made, so it lands mid-interval
#: rather than on the reload it would be indistinguishable from.
PART_WAY = 2

#: Rates the soak moves between, and how many changes it makes.
SOAK_DIVISORS = (0, 1, 4, 5)
SOAK_CHANGES = 8


async def step(dut, counter: Tick) -> bool:
    """One system-clock cycle, through the hardware and the model together.

    Both are asked about the cycle we are in, and both are left in the next."""
    want = counter.cycle()
    got = bool(int(dut.tick_o.value))
    assert got == want, f"tick is {got}, model says {want}"
    await RisingEdge(dut.clk_i)
    await FallingEdge(dut.clk_i)
    return want


async def start(dut) -> Tick:
    """Out of reset, at the rate the field comes up at."""
    cocotb.start_soon(Clock(dut.clk_i, CLK_PERIOD_NS, unit="ns").start())
    dut.divisor_i.value = RESET_DIVISOR
    dut.rst_ni.value = 0
    await ClockCycles(dut.clk_i, RESET_CYCLES)
    await RisingEdge(dut.clk_i)
    dut.rst_ni.value = 1
    await FallingEdge(dut.clk_i)
    return Tick()


async def intervals(dut, counter: Tick, count: int) -> list[int]:
    """The length of each of the next `count` intervals, the first measured
    from where we are now."""
    lengths = []
    cycles = 0
    while len(lengths) < count:
        cycles += 1
        if await step(dut, counter):
            lengths.append(cycles)
            cycles = 0
    return lengths


async def ask_for(dut, counter: Tick, divisor: int) -> None:
    """A new rate, then the interval in flight run out, so what follows is
    measured at the rate asked for."""
    dut.divisor_i.value = divisor
    counter.divide_by(divisor)
    await intervals(dut, counter, 1)


@cocotb.test()
async def it_comes_up_at_the_rate_the_field_comes_up_at(dut):
    """Nothing configures the part before its first conversion, so the rate it
    reaches for out of reset has to be one that converts: the slowest it has."""
    counter = await start(dut)
    assert await intervals(dut, counter, 1) == [period(RESET_DIVISOR)]


@cocotb.test()
async def every_interval_is_the_same_length(dut):
    """The sample phase is one interval and it is the slowest path in the
    design, so an interval short by a cycle is wrong there before anywhere."""
    counter = await start(dut)
    for divisor in DIVISORS:
        await ask_for(dut, counter, divisor)
        measured = await intervals(dut, counter, INTERVALS)
        assert measured == [period(divisor)] * INTERVALS, f"divisor {divisor}"


@cocotb.test()
async def the_fastest_rate_steps_every_cycle(dut):
    """The degenerate rate has to work like any other: it is what a part clocked
    at the conversion rate itself asks for, which is how the closed loop runs."""
    counter = await start(dut)
    await ask_for(dut, counter, 0)
    for _ in range(INTERVALS):
        assert await step(dut, counter)


@cocotb.test()
async def a_new_rate_does_not_shorten_the_interval_in_flight(dut):
    """Cutting short the interval the array is already settling in is how a
    rate changed by hand decides a bit the array had not finished moving for."""
    counter = await start(dut)
    await ask_for(dut, counter, MAX_DIVISOR)
    for _ in range(PART_WAY):
        assert not await step(dut, counter)
    dut.divisor_i.value = 0
    counter.divide_by(0)
    assert await intervals(dut, counter, 1) == [period(MAX_DIVISOR) - PART_WAY]


@cocotb.test()
async def a_rate_that_does_not_change_is_not_a_change(dut):
    """The field is presented every cycle by hardware that cannot tell whether
    it moved, so saying the same thing twice has to be saying nothing."""
    divisor = DIVISORS[-2]
    counter = await start(dut)
    await ask_for(dut, counter, divisor)
    for _ in range(PART_WAY):
        dut.divisor_i.value = divisor
        assert not await step(dut, counter)
    assert await intervals(dut, counter, 1) == [period(divisor) - PART_WAY]


@cocotb.test()
async def every_cycle_matches_the_model_across_a_change_of_rate(dut):
    """Rates moved under a running counter, each change landing part way
    through an interval, which is where a reload that happens early shows."""
    counter = await start(dut)
    for i in range(SOAK_CHANGES):
        divisor = SOAK_DIVISORS[i % len(SOAK_DIVISORS)]
        dut.divisor_i.value = divisor
        counter.divide_by(divisor)
        for _ in range(PART_WAY):
            await step(dut, counter)
        await intervals(dut, counter, INTERVALS)


def test_sar_tick():
    run(
        DUT,
        sources=rtl(DUT),
        parameters={"DIVISOR_WIDTH": BY_NAME[DIVISOR_FIELD].width},
        test_dir=Path(__file__).parent,
    )
