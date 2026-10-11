"""The register file, against the model that declares what the map is.

The bench is the frame: it presents an address, hands over a byte, and says
whether a frame is open and whether a conversion is running. Python keeps the
same map alongside and is asked the same questions, so every test compares the
RTL against the model rather than against a number written here.

Two clocks of slack separate the two: the model settles a waiting write the
moment nothing is in its way, while the RTL settles it on the next edge. Every
comparison of what is in effect is therefore made after an edge has passed.

Every write here is delivered inside a frame, which is the only way one arrives:
the frame is what the model takes as its cue to let waiting writes through, so a
write handed over with no frame open settles a cycle earlier in hardware -- which
reads continuously -- than in the model, which is asked only when something
changes.
"""

import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

from interface import N_BITS
from registers import (
    ADDRESS,
    BY_NAME,
    COUNT,
    IDENTITY,
    IDENTITY_VALUE,
    REGISTER_WIDTH,
    RW,
    VIEWS,
    Registers,
    bits_for,
)
from tb_common import rtl, run

DUT = "sar_regfile"

CLK_PERIOD_NS = 10
RESET_CYCLES = 2

FULL = (1 << REGISTER_WIDTH) - 1

#: The first address the map does not answer to.
PAST_THE_END = COUNT

#: What the converter reports in the one register it shares, each on the input
#: named after it.
STATUS = ("ready", "done", "metastable", "cmp_out")

#: Every field the converter reports, the one that has a register to itself too.
REPORTED = STATUS + ("bit_index",)

#: Fields in effect, each on the output named after it.
IN_EFFECT = ("raw_dac", "force_en", "force_hi", "clk_div", "dac", "view")

#: A word with bits in both registers the widest field spans.
WIDE = 0b11_0000_0001

#: Steps per soak, and the seed. Enough to reach every address several times
#: with a frame opening and a conversion starting across them.
SOAK_STEPS = 300
SOAK_SEED = 5


async def start(dut) -> Registers:
    cocotb.start_soon(Clock(dut.clk_i, CLK_PERIOD_NS, unit="ns").start())
    dut.address_i.value = 0
    dut.wdata_i.value = 0
    dut.write_i.value = 0
    dut.selected_i.value = 0
    dut.converting_i.value = 0
    for name in REPORTED:
        getattr(dut, f"{name}_i").value = 0
    dut.rst_ni.value = 0
    await ClockCycles(dut.clk_i, RESET_CYCLES)
    await RisingEdge(dut.clk_i)
    dut.rst_ni.value = 1
    await FallingEdge(dut.clk_i)
    return Registers()


async def read(dut, address: int) -> int:
    """What the map answers for an address, which is combinational."""
    dut.address_i.value = address
    await FallingEdge(dut.clk_i)
    return int(dut.rdata_o.value)


async def write(dut, registers: Registers, address: int, value: int) -> None:
    """One byte of a frame, to the RTL and to the model together."""
    dut.address_i.value = address
    dut.wdata_i.value = value
    dut.write_i.value = 1
    await RisingEdge(dut.clk_i)
    dut.write_i.value = 0
    if address < COUNT:
        registers.write(address, value)
    await FallingEdge(dut.clk_i)


async def frame(dut, registers: Registers, open_frame: bool) -> None:
    dut.selected_i.value = int(open_frame)
    registers.selected(open_frame)
    await RisingEdge(dut.clk_i)
    await FallingEdge(dut.clk_i)


async def converting(dut, registers: Registers, busy: bool) -> None:
    dut.converting_i.value = int(busy)
    registers.converting(busy)
    await RisingEdge(dut.clk_i)
    await FallingEdge(dut.clk_i)


async def report(dut, registers: Registers, **values: int) -> None:
    for name, value in values.items():
        getattr(dut, f"{name}_i").value = value
    registers.observe(**values)
    await FallingEdge(dut.clk_i)


def effect(dut, name: str) -> int:
    return int(getattr(dut, f"{name}_o").value)


def agrees_on_effect(dut, registers: Registers, what: str) -> None:
    """Every field in effect, as the analog half would see it."""
    for name in IN_EFFECT:
        assert effect(dut, name) == registers[name], (
            f"{what}: {name} in effect is {effect(dut, name):#x}, model says {registers[name]:#x}"
        )


async def agrees_on_reads(dut, registers: Registers, what: str) -> None:
    for address in range(COUNT):
        got = await read(dut, address)
        assert got == registers.read(address), (
            f"{what}: {address:#04x} reads {got:#04x}, model says {registers.read(address):#04x}"
        )


@cocotb.test()
async def every_register_comes_up_as_the_map_says(dut):
    """A converter too slow out of reset still converts; one too fast returns
    codes that are wrong and plausible, so the reset values are not incidental."""
    registers = await start(dut)
    await agrees_on_reads(dut, registers, "out of reset")
    agrees_on_effect(dut, registers, "out of reset")


@cocotb.test()
async def the_identity_reads_the_value_the_map_derives(dut):
    registers = await start(dut)
    assert await read(dut, ADDRESS[IDENTITY]) == IDENTITY_VALUE
    assert registers.read(ADDRESS[IDENTITY]) == IDENTITY_VALUE


@cocotb.test()
async def a_write_reaches_the_register_it_names(dut):
    """Every address in the map, with every bit set, so a write that lands in
    the wrong place shows up wherever it lands."""
    registers = await start(dut)
    await frame(dut, registers, True)
    for address in range(COUNT):
        await write(dut, registers, address, FULL)
        assert await read(dut, address) == registers.read(address), f"{address:#04x}"
    await frame(dut, registers, False)
    await agrees_on_reads(dut, registers, "after writing every register")
    agrees_on_effect(dut, registers, "after writing every register")


@cocotb.test()
async def what_the_converter_reports_is_not_the_hosts_to_write(dut):
    """A write to a reported register cannot be refused, so what it must do is
    nothing at all."""
    registers = await start(dut)
    await report(dut, registers, ready=1, done=0, metastable=1, cmp_out=0, bit_index=N_BITS - 1)
    before = await read(dut, ADDRESS["status"])
    await frame(dut, registers, True)
    await write(dut, registers, ADDRESS["status"], FULL)
    await write(dut, registers, ADDRESS["search"], FULL)
    await frame(dut, registers, False)
    assert await read(dut, ADDRESS["status"]) == before
    await agrees_on_reads(dut, registers, "after writing what is reported")


@cocotb.test()
async def what_the_converter_reports_reads_through(dut):
    registers = await start(dut)
    for index in range(1 << bits_for(N_BITS)):
        await report(dut, registers, bit_index=index)
        assert await read(dut, ADDRESS["search"]) == registers.read(ADDRESS["search"])
    for bits in range(1 << len(STATUS)):
        await report(
            dut,
            registers,
            ready=bits & 1,
            done=bits >> 1 & 1,
            metastable=bits >> 2 & 1,
            cmp_out=bits >> 3 & 1,
        )
        assert await read(dut, ADDRESS["status"]) == registers.read(ADDRESS["status"])


@cocotb.test()
async def an_address_past_the_end_takes_no_write_and_reads_as_nothing(dut):
    """Wrapping instead would land the write on a register that exists."""
    registers = await start(dut)
    await frame(dut, registers, True)
    await write(dut, registers, PAST_THE_END, FULL)
    await write(dut, registers, (1 << (REGISTER_WIDTH - 1)) - 1, FULL)
    await frame(dut, registers, False)
    assert await read(dut, PAST_THE_END) == 0
    await agrees_on_reads(dut, registers, "after writing past the end")
    agrees_on_effect(dut, registers, "after writing past the end")


@cocotb.test()
async def a_held_write_waits_for_the_conversion_to_end(dut):
    """Changing the array's drive part-way through a search abandons the charge
    the sample put there, and the code that comes out belongs to neither
    setting."""
    registers = await start(dut)
    held = BY_NAME["clk_div"]
    assert held.held and held.access == RW
    before = effect(dut, "clk_div")

    await converting(dut, registers, True)
    await frame(dut, registers, True)
    await write(dut, registers, ADDRESS["clk_div"], before ^ FULL)
    await frame(dut, registers, False)
    assert effect(dut, "clk_div") == before, "a held write reached the array mid-conversion"
    assert await read(dut, ADDRESS["clk_div"]) == before ^ FULL, "a held write did not read back"

    await converting(dut, registers, False)
    assert effect(dut, "clk_div") == before ^ FULL
    agrees_on_effect(dut, registers, "after the conversion ended")


@cocotb.test()
async def a_held_write_waits_for_the_frame_to_close(dut):
    """A field wider than one register takes more than one write, so the frame
    is what makes them one change rather than several."""
    registers = await start(dut)
    assert BY_NAME["dac"].registers > 1
    before = effect(dut, "dac")

    await frame(dut, registers, True)
    await write(dut, registers, ADDRESS["dac"], WIDE & FULL)
    assert effect(dut, "dac") == before, "half a wide field reached the array"
    await write(dut, registers, ADDRESS["dac"] + 1, WIDE >> REGISTER_WIDTH)
    assert effect(dut, "dac") == before, "half a wide field reached the array"
    await frame(dut, registers, False)

    assert effect(dut, "dac") == WIDE
    agrees_on_effect(dut, registers, "after the frame closed")


@cocotb.test()
async def a_field_that_waits_for_nothing_takes_effect_at_once(dut):
    """What the dedicated outputs show is not the analog half's to be disturbed
    by, so it does not wait for a conversion."""
    registers = await start(dut)
    view = BY_NAME["view"]
    assert not view.held and view.access == RW

    await converting(dut, registers, True)
    await frame(dut, registers, True)
    for choice in VIEWS:
        await write(dut, registers, ADDRESS["view"], choice)
        assert effect(dut, "view") == choice, f"view {choice} waited"
        assert effect(dut, "view") == registers["view"]


@cocotb.test()
async def every_sequence_matches_the_model(dut):
    """Random writes, reads, frames and conversions. A held write landing on the
    wrong edge shows up as a field in effect that the model does not have."""
    registers = await start(dut)
    rng = random.Random(SOAK_SEED)
    open_frame = False
    busy = False
    for step in range(SOAK_STEPS):
        choice = rng.randrange(4)
        if choice == 0:
            open_frame = not open_frame
            await frame(dut, registers, open_frame)
        elif choice == 1:
            busy = not busy
            await converting(dut, registers, busy)
        elif choice == 2:
            await report(
                dut,
                registers,
                ready=rng.randrange(2),
                done=rng.randrange(2),
                metastable=rng.randrange(2),
                cmp_out=rng.randrange(2),
                bit_index=rng.randrange(1 << bits_for(N_BITS)),
            )
        else:
            if not open_frame:
                open_frame = True
                await frame(dut, registers, True)
            address = rng.randrange(PAST_THE_END + 2)
            await write(dut, registers, address, rng.randrange(1 << REGISTER_WIDTH))
        agrees_on_effect(dut, registers, f"step {step}")
        await agrees_on_reads(dut, registers, f"step {step}")


def test_sar_regfile():
    run(
        DUT,
        sources=rtl(DUT),
        parameters={
            "REGISTER_WIDTH": REGISTER_WIDTH,
            "N_BITS": N_BITS,
            "VIEW_WIDTH": bits_for(len(VIEWS)),
        },
        test_dir=Path(__file__).parent,
    )
