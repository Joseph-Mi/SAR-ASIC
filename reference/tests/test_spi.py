"""The frame, and what a host can and cannot do to the registers with one.

The frame is the only way configuration reaches the chip, so its failures are
the ones nobody can work around afterwards: a direction bit the wrong way round
turns an idle line into a write, and an address that wraps lands a stray write
on a register that exists.
"""

from __future__ import annotations

import pytest

from registers import ADDRESS, COUNT, REGISTER_WIDTH, VIEW_SEARCH
from spi import ADDRESS_MASK, DIRECTION, IDLE_BYTE, WRITE, Slave, command

FULL = (1 << REGISTER_WIDTH) - 1

#: A word with bits in both of the registers its field spans, so a frame that
#: carries only one of them cannot pass.
WIDE = 0b11_0000_0001

#: Bytes of a frame that nobody is driving.
QUIET_FRAME = (0, 0, 0)


def test_a_command_says_where_and_which_way():
    assert command(ADDRESS["dac"], write=True) == WRITE | ADDRESS["dac"]
    assert command(ADDRESS["dac"], write=False) == ADDRESS["dac"]


def test_an_address_too_wide_for_a_command_is_refused():
    with pytest.raises(ValueError):
        command(ADDRESS_MASK + 1, write=True)


def test_the_map_fits_a_command_byte():
    """An address the frame cannot express is a register nothing can reach."""
    assert COUNT <= ADDRESS_MASK + 1


def test_a_quiet_line_changes_nothing():
    """A line nobody drives, or one stuck low, is a read of the first register.
    This is the whole reason the direction bit means write when it is set."""
    slave = Slave()
    slave.configure(raw_dac=1, force_en=1, force_hi=1)
    before = [slave.registers.read(a) for a in range(COUNT)]

    slave.select()
    for byte in QUIET_FRAME:
        slave.transfer(byte)
    slave.deselect()

    assert [slave.registers.read(a) for a in range(COUNT)] == before


def test_a_write_frame_sets_the_register():
    slave = Slave()
    slave.write(ADDRESS["clk_div"], 1)
    assert slave.registers["clk_div"] == 1


def test_the_address_steps_on_for_every_byte():
    """One frame reaches consecutive registers, which is what lets a field wider
    than the bus be set by one frame."""
    slave = Slave()
    slave.write(ADDRESS["dac"], WIDE & FULL, WIDE >> REGISTER_WIDTH)
    assert slave.registers["dac"] == WIDE


def test_a_read_frame_returns_consecutive_registers():
    slave = Slave()
    slave.configure(dac=WIDE)
    assert slave.read(ADDRESS["dac"], 2) == [WIDE & FULL, WIDE >> REGISTER_WIDTH]


def test_the_slave_says_nothing_while_the_command_is_still_arriving():
    """It cannot know what was asked for until that byte is whole."""
    slave = Slave()
    slave.select()
    assert slave.transfer(command(ADDRESS["clk_div"], write=False)) == IDLE_BYTE
    slave.deselect()


def test_a_read_reports_what_the_converter_put_there():
    slave = Slave()
    slave.registers.observe(metastable=1)
    assert slave.read(ADDRESS["status"]) == [1 << 2]


def test_an_address_past_the_end_takes_no_write():
    """And the frame survives it: hardware has no way to refuse, and a decoder
    that wrapped would land the write on a register that exists."""
    slave = Slave()
    before = [slave.registers.read(a) for a in range(COUNT)]
    slave.write(COUNT, FULL, FULL)
    assert [slave.registers.read(a) for a in range(COUNT)] == before


def test_an_address_past_the_end_reads_as_nothing():
    assert Slave().read(COUNT, 2) == [IDLE_BYTE, IDLE_BYTE]


def test_a_frame_that_runs_off_the_end_keeps_what_it_reached():
    """It walks over the registers the converter owns and then past the map
    itself. The byte that landed stays; the rest reach nothing."""
    slave = Slave()
    before = [slave.registers.read(a) for a in range(COUNT)]
    slave.write(ADDRESS["view"], VIEW_SEARCH, FULL, FULL, FULL)
    after = [slave.registers.read(a) for a in range(COUNT)]
    assert slave.registers["view"] == VIEW_SEARCH
    assert after[ADDRESS["view"] + 1 :] == before[ADDRESS["view"] + 1 :]


def test_something_that_is_not_a_byte_is_refused():
    slave = Slave()
    slave.select()
    with pytest.raises(ValueError):
        slave.transfer(1 << REGISTER_WIDTH)


def test_nothing_takes_effect_until_the_frame_closes():
    slave = Slave()
    slave.select()
    slave.transfer(command(ADDRESS["control"], write=True))
    slave.transfer(1)
    assert slave.registers["raw_dac"] == 0
    slave.deselect()
    assert slave.registers["raw_dac"] == 1


def test_a_field_wider_than_the_bus_survives_a_conversion_inside_the_frame():
    """The case the frame exists for. A conversion ending between the two writes
    would otherwise commit half of the word, which is a code nobody asked for."""
    slave = Slave()
    slave.select()
    slave.transfer(command(ADDRESS["dac"], write=True))
    slave.transfer(WIDE & FULL)
    slave.registers.converting(True)
    slave.registers.converting(False)
    slave.transfer(WIDE >> REGISTER_WIDTH)
    slave.deselect()
    assert slave.registers["dac"] == WIDE


def test_configure_leaves_alone_what_it_was_not_asked_about():
    """The frame covers every register between the lowest and highest asked for,
    so one it was not asked about has to be written back as it stands."""
    slave = Slave()
    slave.configure(dac=WIDE)
    slave.configure(view=VIEW_SEARCH)
    assert slave.registers["dac"] == WIDE
    assert slave.registers["view"] == VIEW_SEARCH
    assert slave.registers["clk_div"] == FULL


def test_configure_spans_a_register_it_was_not_asked_about():
    """Asking for fields either side of another register still reaches both, and
    the one in between keeps what it held."""
    slave = Slave()
    slave.configure(clk_div=1)
    slave.configure(raw_dac=1, force_en=0, force_hi=0, dac=WIDE)
    assert slave.registers["raw_dac"] == 1
    assert slave.registers["dac"] == WIDE
    assert slave.registers["clk_div"] == 1


def test_the_direction_bit_is_the_top_one():
    """Where it sits decides how much address a command can carry."""
    assert WRITE == 1 << DIRECTION
    assert ADDRESS_MASK == (1 << DIRECTION) - 1
