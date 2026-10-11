"""What asks for a conversion, against the model that declares the two modes.

Every cycle is compared, not the outcome: the question is a level the search
reads on an edge of its own, so a module that asks on the right cycles but
drops the level in between would convert correctly here and not on a chip.

The request pin is a mechanical button in the mode that reads it, so the
sequences driven here are the ones a button produces -- held down, released,
already down when the power came up, pressed while the part was busy.

Pins are read on the falling edge. start_o is combinational on the request
latch, so it belongs to the cycle it is read in.
"""

import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

from start import CONTINUOUS, MODES, SINGLE_SHOT, Start
from tb_common import rtl, run
from tick import MAX_DIVISOR, period

DUT = "sar_start"

CLK_PERIOD_NS = 10
RESET_CYCLES = 2

#: Cycles a request has to survive to be heard: one interval of the slowest
#: conversion clock the field can ask for, which is the longest the search can
#: go without listening.
WAITING = period(MAX_DIVISOR)

#: Contact bounces before a button's level settles.
BOUNCES = 3

LOW, HIGH = False, True

#: Steps per soak, and the seed. Enough to reach every combination of mode,
#: level and step several times.
SOAK_STEPS = 400
SOAK_SEED = 11


async def step(dut, model: Start, level: bool, ready: bool = True, stepping: bool = True) -> bool:
    """One system-clock cycle: the pins during it, both asked the same question
    about it, and the edge that ends it taken by both."""
    dut.request_i.value = int(level)
    dut.single_shot_i.value = int(model.mode == SINGLE_SHOT)
    dut.ready_i.value = int(ready)
    dut.tick_i.value = int(stepping)
    await FallingEdge(dut.clk_i)
    want = model.asking(ready)
    got = bool(int(dut.start_o.value))
    assert got == want, f"start is {got}, model says {want}"
    await RisingEdge(dut.clk_i)
    model.cycle(level, ready, stepping)
    return want


async def cycles(dut, model: Start, count: int, level: bool, **kwargs) -> list[bool]:
    return [await step(dut, model, level, **kwargs) for _ in range(count)]


async def press(dut, model: Start, **kwargs) -> None:
    """The pin low for a cycle and then high, which is one press."""
    await cycles(dut, model, 1, LOW, **kwargs)
    await cycles(dut, model, 1, HIGH, **kwargs)


async def begin(dut, mode: str = CONTINUOUS) -> Start:
    cocotb.start_soon(Clock(dut.clk_i, CLK_PERIOD_NS, unit="ns").start())
    dut.request_i.value = 0
    dut.single_shot_i.value = int(mode == SINGLE_SHOT)
    dut.ready_i.value = 0
    dut.tick_i.value = 0
    dut.rst_ni.value = 0
    await ClockCycles(dut.clk_i, RESET_CYCLES)
    await RisingEdge(dut.clk_i)
    dut.rst_ni.value = 1
    return Start(mode=mode)


@cocotb.test()
async def the_default_mode_converts_without_being_asked(dut):
    """The platform leaves an unconnected input low, so this is the mode a part
    with nothing wired to it is in. Waiting to be asked would read as a dead
    chip on a bench."""
    model = await begin(dut)
    assert all(await cycles(dut, model, WAITING, LOW))


@cocotb.test()
async def continuous_reads_no_pin(dut):
    """So a board can leave the request pin floating and still convert."""
    model = await begin(dut)
    for level in (LOW, HIGH):
        assert all(await cycles(dut, model, WAITING, level))


@cocotb.test()
async def nothing_is_asked_while_the_search_is_busy(dut):
    """An ask that reached a running search would restart it part way, and the
    code that came out would belong to neither conversion."""
    for mode in MODES:
        model = await begin(dut, mode)
        await press(dut, model, ready=False)
        assert not any(await cycles(dut, model, WAITING, HIGH, ready=False))


@cocotb.test()
async def single_shot_waits_to_be_asked(dut):
    model = await begin(dut, SINGLE_SHOT)
    assert not any(await cycles(dut, model, WAITING, LOW))


@cocotb.test()
async def a_press_asks_for_one_conversion(dut):
    model = await begin(dut, SINGLE_SHOT)
    await press(dut, model)
    assert sum(await cycles(dut, model, WAITING, HIGH)) == 1


@cocotb.test()
async def a_request_outlives_the_wait_for_a_step(dut):
    """The search hears a request only on a step of the conversion clock, and
    at the slowest rate those are a whole interval apart."""
    model = await begin(dut, SINGLE_SHOT)
    await press(dut, model, stepping=False)
    assert all(await cycles(dut, model, WAITING, HIGH, stepping=False))


@cocotb.test()
async def a_request_outlives_a_conversion_in_flight(dut):
    """Pressing while the part is busy asks for the next conversion; it is not
    a mistake to be thrown away."""
    model = await begin(dut, SINGLE_SHOT)
    await press(dut, model, ready=False)
    await cycles(dut, model, WAITING, HIGH, ready=False)
    assert await step(dut, model, HIGH)


@cocotb.test()
async def a_press_landing_on_the_cycle_a_request_is_served_is_not_lost(dut):
    """Two asks are two conversions. Dropping the second loses a press that was
    really made, and the part then looks like it missed one."""
    model = await begin(dut, SINGLE_SHOT)
    await press(dut, model, stepping=False)
    await cycles(dut, model, 1, LOW, stepping=False)
    # The second press lands on the very cycle a step serves the first.
    assert await step(dut, model, HIGH)
    assert await step(dut, model, HIGH), "the second press was dropped"


@cocotb.test()
async def a_pin_already_high_out_of_reset_is_not_a_press(dut):
    """There was no edge. A part whose button is wired the other way up would
    otherwise convert once at every power-up."""
    model = await begin(dut, SINGLE_SHOT)
    assert not any(await cycles(dut, model, WAITING, HIGH))


@cocotb.test()
async def a_press_in_continuous_mode_is_not_remembered(dut):
    """Moving the jumper is not a request, so a part converting continuously
    does not fire one more conversion the moment it is made single-shot."""
    model = await begin(dut)
    for _ in range(BOUNCES):
        await press(dut, model)
    model.mode = SINGLE_SHOT
    assert not any(await cycles(dut, model, WAITING, HIGH))


@cocotb.test()
async def every_sequence_matches_the_model(dut):
    """Modes, presses, releases and steps in any order, including the jumper
    moving mid-conversion -- which nothing is allowed to disturb."""
    model = await begin(dut)
    rng = random.Random(SOAK_SEED)
    level, ready, stepping = LOW, True, True
    for _ in range(SOAK_STEPS):
        choice = rng.randrange(5)
        if choice == 0:
            model.mode = rng.choice(MODES)
        elif choice == 1:
            level = not level
        elif choice == 2:
            ready = not ready
        elif choice == 3:
            stepping = not stepping
        await step(dut, model, level, ready=ready, stepping=stepping)


def test_sar_start():
    run(DUT, sources=rtl(DUT), test_dir=Path(__file__).parent)
