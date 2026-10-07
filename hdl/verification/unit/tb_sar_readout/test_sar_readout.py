"""The result register, against the model that defines what the pins show.

Expectations come from the model: every cycle the bench drives, the model says
what the pins must read afterwards, and the comparison is made on every one of
them rather than at the end.

Pins are read on the falling edge. Registered outputs settle on the rising one,
so reading there races the update being checked.
"""

import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

from interface import N_BITS
from readout import EDGE_CAPTURE, INITIAL_CODE, LEVEL_HOLD, MODES, Readout
from tb_common import rtl, run

DUT = "sar_readout"

CLK_PERIOD_NS = 10
RESET_CYCLES = 2

#: Codes distinct from each other and from the register's reset value, so a
#: result that failed to land is never mistaken for one that did.
CODES = (3, 7, 11, 21)

#: Contact bounces before a button's level settles.
BOUNCES = 3

#: Cycles with nothing happening, where the flag must stay down.
QUIET_CYCLES = 3

#: Random cycles per mode. Long enough that a request left pending, an edge
#: missed, or a flag that sticks shows up instead of being stepped over.
SOAK_CYCLES = 2000

#: How often a soak cycle ends a conversion, and how often it holds the pin.
LOAD_CHANCE = 0.15
HOLD_CHANCE = 0.3

#: Fixed so a failing soak replays.
SOAK_SEED = 7


def pins(dut):
    return int(dut.code_o.value), bool(int(dut.done_o.value))


async def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk_i, CLK_PERIOD_NS, unit="ns").start())


async def reset(dut, mode) -> Readout:
    """Hold the DUT in reset, release it, and return a model beside it."""
    dut.load_i.value = 0
    dut.code_i.value = 0
    dut.hold_i.value = 0
    dut.edge_capture_i.value = 1 if mode == EDGE_CAPTURE else 0
    dut.rst_ni.value = 0
    await ClockCycles(dut.clk_i, RESET_CYCLES)
    await RisingEdge(dut.clk_i)
    dut.rst_ni.value = 1
    await FallingEdge(dut.clk_i)
    return Readout(mode=mode)


async def step(dut, model, *, load=False, code=0, hold=False):
    """One clock: drive the cycle's inputs, then check the pins against the
    model that was stepped with the same ones."""
    dut.load_i.value = 1 if load else 0
    dut.code_i.value = code
    dut.hold_i.value = 1 if hold else 0

    model.pin(hold)
    if load:
        model.finished(code)
    else:
        model.idle()

    await RisingEdge(dut.clk_i)
    await FallingEdge(dut.clk_i)
    assert pins(dut) == (model.code, model.done)


@cocotb.test()
async def nothing_shows_before_a_conversion(dut):
    """Out of reset the pins read the register's own value, and the flag is
    down: a reader must not take an untouched register for a result."""
    await start_clock(dut)
    for mode in MODES:
        model = await reset(dut, mode)
        for _ in range(QUIET_CYCLES):
            await step(dut, model)
        code, done = pins(dut)
        assert code == INITIAL_CODE
        assert not done


@cocotb.test()
async def every_conversion_reaches_the_pins_while_the_pin_is_low(dut):
    """The default. A part with nothing on the pin converts and shows it."""
    await start_clock(dut)
    model = await reset(dut, LEVEL_HOLD)
    for code in CODES:
        await step(dut, model, load=True, code=code)
        assert pins(dut) == (code, True)
        await step(dut, model)


@cocotb.test()
async def a_held_pin_freezes_the_pins(dut):
    """The converter keeps running; only the register stops taking results."""
    await start_clock(dut)
    model = await reset(dut, LEVEL_HOLD)
    await step(dut, model, load=True, code=CODES[0])
    for code in CODES[1:]:
        await step(dut, model, load=True, code=code, hold=True)
        assert pins(dut) == (CODES[0], False)
    await step(dut, model, load=True, code=CODES[-1])
    assert pins(dut) == (CODES[-1], True)


@cocotb.test()
async def edge_capture_waits_to_be_asked(dut):
    """Conversions pass without reaching the pins until one is asked for."""
    await start_clock(dut)
    model = await reset(dut, EDGE_CAPTURE)
    for code in CODES:
        await step(dut, model, load=True, code=code)
        assert pins(dut) == (INITIAL_CODE, False)

    await step(dut, model, hold=True)
    await step(dut, model, load=True, code=CODES[0], hold=True)
    assert pins(dut) == (CODES[0], True)

    await step(dut, model, load=True, code=CODES[1], hold=True)
    assert pins(dut) == (CODES[0], False)


@cocotb.test()
async def a_request_outlives_the_edge_that_made_it(dut):
    """The edge lands on whatever cycle the button closes, which is almost never
    the cycle a conversion ends."""
    await start_clock(dut)
    model = await reset(dut, EDGE_CAPTURE)
    await step(dut, model, hold=False)
    await step(dut, model, hold=True)
    for _ in range(QUIET_CYCLES):
        await step(dut, model, hold=True)
    await step(dut, model, load=True, code=CODES[0], hold=True)
    assert pins(dut) == (CODES[0], True)


@cocotb.test()
async def a_bouncing_button_captures_once(dut):
    """Several edges before a conversion ask for the same one result, so the
    pin needs no debounce: a request is not a count."""
    await start_clock(dut)
    model = await reset(dut, EDGE_CAPTURE)
    for _ in range(BOUNCES):
        await step(dut, model, hold=False)
        await step(dut, model, hold=True)
    await step(dut, model, load=True, code=CODES[0], hold=True)
    assert pins(dut) == (CODES[0], True)
    await step(dut, model, load=True, code=CODES[1], hold=True)
    assert pins(dut) == (CODES[0], False)


@cocotb.test()
async def a_soak_matches_the_model_every_cycle(dut):
    """Loads and pin movement in every combination the modes can see, including
    an edge and a conversion ending on the same cycle."""
    await start_clock(dut)
    rng = random.Random(SOAK_SEED)
    for mode in MODES:
        model = await reset(dut, mode)
        for _ in range(SOAK_CYCLES):
            await step(
                dut,
                model,
                load=rng.random() < LOAD_CHANCE,
                code=rng.randrange(1, 1 << N_BITS),
                hold=rng.random() < HOLD_CHANCE,
            )


def test_sar_readout():
    run(DUT, sources=rtl(DUT), parameters={"N_BITS": N_BITS}, test_dir=Path(__file__).parent)
