"""The SPI slave, against the frame model that defines what a frame means.

The bench is the master. It drives the select line, the clock and the data as
plain signals -- the slave samples them with the system clock, so there is only
one clock here and the wire's rate is a number of cycles per phase.

Python stands in for the register file: it answers reads, takes the writes the
slave announces, and tells the registers when a frame is open. Every frame is
run against `reference/spi` as well, and both the bytes returned and the state
left behind have to agree.
"""

import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

from registers import (
    ADDRESS,
    COUNT,
    FIELDS,
    IDENTITY,
    IDENTITY_VALUE,
    REGISTER_WIDTH,
    RW,
    Registers,
)
from spi import Slave, command
from tb_common import rtl, run

DUT = "sar_spi"

CLK_PERIOD_NS = 10
RESET_CYCLES = 2

#: System clocks per phase of the wire's clock. The slave samples the wire, so a
#: phase has to last long enough to be seen; this is comfortably over that.
SCK_PHASE_CYCLES = 4

FULL = (1 << REGISTER_WIDTH) - 1

#: A word with bits in both registers its field spans.
WIDE = 0b11_0000_0001

#: Bytes of a frame nobody is driving.
QUIET_FRAME = (0, 0, 0)

#: Frames per soak, and the longest one. Enough to reach every byte position and
#: to run a frame off the end of the map.
SOAK_FRAMES = 60
SOAK_BYTES = 5
SOAK_SEED = 11

SETTLED = {f.name for f in FIELDS if f.access == RW}


async def serve_registers(dut, registers: Registers) -> None:
    """The register file, in Python. Reads are answered for whatever address the
    slave is presenting; writes are taken on the cycle it announces one."""
    while True:
        await FallingEdge(dut.clk_i)
        if dut.write_o.value == 1:
            address = int(dut.address_o.value)
            if address < COUNT:
                registers.write(address, int(dut.wdata_o.value))
        registers.selected(bool(dut.selected_o.value))
        address = int(dut.address_o.value)
        dut.rdata_i.value = registers.read(address) if address < COUNT else 0


async def start(dut) -> Registers:
    cocotb.start_soon(Clock(dut.clk_i, CLK_PERIOD_NS, unit="ns").start())
    dut.sck_i.value = 0
    dut.cs_ni.value = 1
    dut.mosi_i.value = 0
    dut.rdata_i.value = 0
    dut.rst_ni.value = 0
    await ClockCycles(dut.clk_i, RESET_CYCLES)
    await RisingEdge(dut.clk_i)
    dut.rst_ni.value = 1
    registers = Registers()
    cocotb.start_soon(serve_registers(dut, registers))
    await ClockCycles(dut.clk_i, RESET_CYCLES)
    return registers


async def phase(dut, level: int) -> None:
    dut.sck_i.value = level
    await ClockCycles(dut.clk_i, SCK_PHASE_CYCLES)


async def transfer(dut, byte: int) -> int:
    """One byte out, one byte in. The slave moves its line on the falling edge,
    so the master reads it at the end of the low phase."""
    got = 0
    for i in range(REGISTER_WIDTH - 1, -1, -1):
        dut.mosi_i.value = (byte >> i) & 1
        await phase(dut, 0)
        got = (got << 1) | int(dut.miso_o.value)
        await phase(dut, 1)
    dut.sck_i.value = 0
    return got


async def frame(dut, data) -> list[int]:
    dut.cs_ni.value = 0
    await ClockCycles(dut.clk_i, SCK_PHASE_CYCLES)
    out = []
    for byte in data:
        out.append(await transfer(dut, byte))
    await ClockCycles(dut.clk_i, SCK_PHASE_CYCLES)
    dut.cs_ni.value = 1
    await ClockCycles(dut.clk_i, SCK_PHASE_CYCLES)
    return out


def state(registers: Registers) -> dict[str, int]:
    return {name: registers[name] for name in sorted(SETTLED)}


async def agrees(dut, registers, slave, data, what) -> list[int]:
    """Run one frame against the RTL and the model, and compare both what came
    back and what was left behind."""
    got = await frame(dut, data)
    slave.select()
    want = [slave.transfer(byte) for byte in data]
    slave.deselect()
    assert got == want, f"{what}: returned {got}, model says {want}"
    assert state(registers) == state(slave.registers), f"{what}: registers diverged"
    return got


@cocotb.test()
async def a_write_frame_reaches_the_register(dut):
    registers = await start(dut)
    slave = Slave()
    data = [command(ADDRESS["clk_div"], write=True), 0x5A]
    await agrees(dut, registers, slave, data, "write")
    assert registers["clk_div"] == 0x5A


@cocotb.test()
async def one_frame_sets_a_field_wider_than_the_bus(dut):
    """The address steps on per byte, which is what makes the two writes one
    change rather than two."""
    registers = await start(dut)
    slave = Slave()
    data = [command(ADDRESS["dac"], write=True), WIDE & FULL, WIDE >> REGISTER_WIDTH]
    await agrees(dut, registers, slave, data, "wide write")
    assert registers["dac"] == WIDE


@cocotb.test()
async def a_read_frame_returns_consecutive_registers(dut):
    registers = await start(dut)
    await frame(dut, [command(ADDRESS["dac"], write=True), WIDE & FULL, WIDE >> REGISTER_WIDTH])
    got = await frame(dut, [command(ADDRESS["dac"], write=False), 0, 0])
    assert got == [0, WIDE & FULL, WIDE >> REGISTER_WIDTH]
    assert registers["dac"] == WIDE


@cocotb.test()
async def a_quiet_line_returns_the_identity_and_changes_nothing(dut):
    """A line nobody drives reads the bottom of the map, which is the register
    that says which map this is -- so the harmless case is also the one that
    proves the part is answering.

    The registers the frame reaches are given a bit first, and through the model
    as well so the two agree on what a read returns: a register holding its reset
    value of zero reads the same whether or not the frame wrote it.
    """
    registers = await start(dut)
    slave = Slave()
    setup = [command(ADDRESS["control"], write=True), 1, 1]
    await agrees(dut, registers, slave, setup, "setup")
    before = state(registers)
    got = await agrees(dut, registers, slave, list(QUIET_FRAME), "quiet frame")
    assert got[1] == IDENTITY_VALUE, f"quiet frame read {got[1]:#04x} at {IDENTITY}"
    assert state(registers) == before


@cocotb.test()
async def the_slave_says_nothing_through_a_write(dut):
    registers = await start(dut)
    await frame(dut, [command(ADDRESS["clk_div"], write=True), FULL])
    assert registers["clk_div"] == FULL
    got = await frame(dut, [command(ADDRESS["clk_div"], write=True), 0x3C])
    assert got == [0, 0]


@cocotb.test()
async def a_frame_cut_short_leaves_nothing_behind(dut):
    """Bits left in the shifter from an abandoned frame would turn two partial
    frames into one write nobody asked for."""
    registers = await start(dut)
    dut.cs_ni.value = 0
    await ClockCycles(dut.clk_i, SCK_PHASE_CYCLES)
    dut.mosi_i.value = 1
    for _ in range(REGISTER_WIDTH // 2):
        await phase(dut, 0)
        await phase(dut, 1)
    dut.sck_i.value = 0
    dut.cs_ni.value = 1
    await ClockCycles(dut.clk_i, SCK_PHASE_CYCLES)

    slave = Slave()
    data = [command(ADDRESS["clk_div"], write=True), 0x42]
    await agrees(dut, registers, slave, data, "after an abandoned frame")
    assert registers["clk_div"] == 0x42


@cocotb.test()
async def every_frame_matches_the_model(dut):
    """Random frames, including ones that run off the end of the map and ones
    that are nothing but a command byte."""
    registers = await start(dut)
    slave = Slave()
    rng = random.Random(SOAK_SEED)
    for i in range(SOAK_FRAMES):
        data = [rng.randrange(1 << REGISTER_WIDTH) for _ in range(rng.randint(1, SOAK_BYTES))]
        await agrees(dut, registers, slave, data, f"frame {i}")


def test_sar_spi():
    run(
        DUT,
        sources=rtl(DUT, "sync2"),
        parameters={"REGISTER_WIDTH": REGISTER_WIDTH},
        test_dir=Path(__file__).parent,
    )
