"""The register map, and when a write reaches the half that acts on it.

The map is the chip's configuration surface: a field that overlaps another, or
one that reaches the analog half part-way through a search, is wrong in a way no
simulation of the search itself would show.
"""

from __future__ import annotations

import copy

import pytest

from interface import N_BITS
from registers import (
    ADDRESS,
    COUNT,
    FIELD_ADDRESS,
    FIELDS,
    IDENTITY,
    IDENTITY_VALUE,
    LAYOUT,
    MAP_HASH,
    REGISTER_WIDTH,
    RO,
    RW,
    UNDRIVEN,
    VIEW_CODE,
    VIEW_SEARCH,
    Registers,
    bits_for,
    description,
    fields_at,
    hash_of,
    placement,
    writes_for,
)

#: A value with a bit set in every position a register has, so a write that lands
#: in the wrong place shows up wherever it lands.
FULL = (1 << REGISTER_WIDTH) - 1

#: The one writable field that does not wait for a conversion to end. It chooses
#: what the outputs show and nothing the converter does, and the design
#: deliberately exempts a deliberate look at internals from the rule that the
#: result pins hold still.
IMMEDIATE = {"view"}


def share_registers_with(field):
    """The other writable fields of every address `field` touches."""
    return [
        f
        for address in range(FIELD_ADDRESS[field.name], FIELD_ADDRESS[field.name] + field.registers)
        for f in fields_at(address)
        if f.access == RW and f.name != field.name
    ]


def test_addresses_run_from_zero_without_gaps():
    """A gap reads as a register holding nothing, which is indistinguishable from
    one holding zero. A contiguous range makes the decoder a bound check."""
    covered = {FIELD_ADDRESS[f.name] + i for f in FIELDS for i in range(f.registers)}
    assert covered == set(range(COUNT))


def test_no_two_fields_share_a_bit():
    """Two fields over one bit means writing either moves the other."""
    for address in range(COUNT):
        taken: dict[int, str] = {}
        for field in fields_at(address):
            _, width, offset = placement(field, address)
            for bit in range(offset, offset + width):
                assert bit not in taken, f"{field.name} and {taken[bit]} share bit {bit}"
                taken[bit] = field.name


def test_every_field_fits_the_registers_it_claims():
    for field in FIELDS:
        for i in range(field.registers):
            _, width, offset = placement(field, FIELD_ADDRESS[field.name] + i)
            assert offset + width <= REGISTER_WIDTH, field.name


def test_a_field_wider_than_a_register_is_alone_in_its_own():
    """Its bits are the whole of every address it covers, so anything beside it
    would have nowhere to sit."""
    for name, group in LAYOUT:
        if any(field.registers > 1 for field in group):
            assert len(group) == 1, name


def test_reset_is_ordinary_operation():
    """A part nobody has configured converts, and converts from its pin."""
    reg = Registers()
    assert reg["raw_dac"] == 0
    assert reg["force_en"] == 0
    assert reg["view"] == VIEW_CODE


def test_the_clock_resets_to_the_slowest_it_can_ask_for():
    """Too slow still converts correctly. Too fast returns codes that are wrong
    and plausible, which is the worse failure to leave in a reset value."""
    reg = Registers()
    assert reg["clk_div"] == FULL


def test_the_search_index_can_count_every_bit():
    assert next(f for f in FIELDS if f.name == "bit_index").width == bits_for(N_BITS)


def test_a_write_reads_back_before_it_takes_effect():
    """Readback is what the host asked for. What is in effect is the converter's
    business, and the two differ only while it is busy."""
    reg = Registers()
    reg.converting(True)
    reg.write(ADDRESS["clk_div"], 1)
    assert reg.written("clk_div") == 1
    assert reg["clk_div"] == FULL


def test_no_held_write_reaches_the_converter_while_it_is_busy():
    """Every field the analog half acts on, not a chosen one. Each is written to
    the opposite of what it holds, so a write that did nothing cannot pass."""
    held = [f for f in FIELDS if f.access == RW and f.held]
    assert held, "the map holds nothing back, which cannot be right"
    for field in held:
        reg = Registers()
        reg.converting(True)
        before = reg[field.name]
        target = before ^ field.mask
        others = {f.name: reg.written(f.name) for f in share_registers_with(field)}
        for address, value in writes_for(**{field.name: target}, **others):
            reg.write(address, value)
        assert reg[field.name] == before, field.name
        assert reg.written(field.name) == target, field.name


def test_a_held_write_lands_once_the_conversion_ends():
    reg = Registers()
    reg.converting(True)
    reg.write(ADDRESS["control"], 1)
    assert reg["raw_dac"] == 0
    reg.converting(False)
    assert reg["raw_dac"] == 1


def test_a_field_wider_than_the_bus_is_whole_before_it_is_used():
    """It takes more than one write, so a conversion ending between them would
    otherwise hand the analog half half of the word."""
    reg = Registers()
    word = (1 << N_BITS) - 1 - (1 << (N_BITS - 1))
    reg.selected(True)
    for address, value in writes_for(dac=word):
        reg.write(address, value)
        reg.converting(True)
        reg.converting(False)
    reg.selected(False)
    assert reg["dac"] == word


def test_nothing_in_an_open_frame_takes_effect_yet():
    reg = Registers()
    reg.write(ADDRESS["control"], 1)
    reg.selected(True)
    reg.converting(False)
    assert reg["raw_dac"] == 0
    reg.selected(False)
    assert reg["raw_dac"] == 1


def test_a_held_write_made_while_idle_does_not_wait_for_a_conversion():
    """Nothing is stranded by a part that is never asked to convert again."""
    reg = Registers()
    reg.write(ADDRESS["control"], 1)
    reg.converting(False)
    assert reg["raw_dac"] == 1


def test_only_the_view_takes_effect_at_once():
    """A writable field that is not held and does reach the converter would
    change the array's drive mid-search."""
    assert {f.name for f in FIELDS if f.access == RW and not f.held} == IMMEDIATE
    reg = Registers()
    reg.converting(True)
    reg.write(ADDRESS["view"], VIEW_SEARCH)
    assert reg["view"] == VIEW_SEARCH


def test_a_word_wider_than_the_bus_reassembles_from_its_registers():
    """Every bit but the most significant, so a word assembled in the wrong order
    or short of a register does not land on the value asked for."""
    reg = Registers()
    word = (1 << N_BITS) - 1 - (1 << (N_BITS - 1))
    for address, value in writes_for(dac=word):
        reg.write(address, value)
    reg.converting(False)
    assert reg["dac"] == word


def test_writes_for_refuses_to_clear_a_field_it_was_not_asked_about():
    """A register is written whole, so a caller naming one of its fields and not
    the others would silently zero them."""
    with pytest.raises(KeyError):
        writes_for(raw_dac=1)
    assert writes_for(raw_dac=1, force_en=0, force_hi=0) == [(ADDRESS["control"], 1)]


def test_writes_for_refuses_a_field_the_converter_owns():
    with pytest.raises(KeyError):
        writes_for(metastable=1)


def test_a_write_to_a_register_the_converter_owns_changes_nothing():
    reg = Registers()
    reg.write(ADDRESS["status"], FULL)
    reg.converting(False)
    assert all(reg[f.name] == 0 for f in fields_at(ADDRESS["status"]))


def test_the_converter_reports_into_the_fields_it_owns():
    reg = Registers()
    reg.observe(metastable=1, bit_index=N_BITS - 1)
    assert reg["metastable"] == 1
    assert reg["bit_index"] == N_BITS - 1
    assert reg.read(ADDRESS["status"]) >> 2 & 1


def test_the_converter_may_not_report_into_the_host_s_fields():
    with pytest.raises(KeyError):
        Registers().observe(raw_dac=1)


def test_a_report_too_wide_for_its_field_is_refused():
    with pytest.raises(ValueError):
        Registers().observe(bit_index=1 << bits_for(N_BITS))


def test_a_value_too_wide_for_a_register_is_refused():
    with pytest.raises(ValueError):
        Registers().write(ADDRESS["clk_div"], 1 << REGISTER_WIDTH)


@pytest.mark.parametrize("address", [-1, COUNT])
def test_an_address_the_map_does_not_have_is_refused(address):
    reg = Registers()
    with pytest.raises(KeyError):
        reg.write(address, 0)
    with pytest.raises(KeyError):
        reg.read(address)


def test_every_field_is_one_of_the_two_accesses():
    assert all(f.access in (RW, RO) for f in FIELDS)


def test_the_identity_sits_at_the_bottom_of_the_map():
    """A host that cannot find the check cannot make it, and the bottom is the
    one address a frame of all zeros reaches."""
    assert ADDRESS[IDENTITY] == 0


def test_the_identity_reads_as_the_value_derived_from_the_map():
    assert Registers().read(ADDRESS[IDENTITY]) == IDENTITY_VALUE


def test_the_identity_is_never_what_an_undriven_line_reads_as():
    """Otherwise the check passes on a bus that is answering with nothing."""
    assert IDENTITY_VALUE not in UNDRIVEN


def test_the_identity_is_not_the_hosts_to_write():
    reg = Registers()
    reg.write(ADDRESS[IDENTITY], FULL)
    assert reg.read(ADDRESS[IDENTITY]) == IDENTITY_VALUE


def test_the_identity_is_not_described_by_its_own_value():
    """What the identity is derived from cannot include the identity: a number
    covering itself has nothing to settle on. It is reported, not stored."""
    described = next(f for f in description() if f["name"] == IDENTITY)
    assert described["reset"] != IDENTITY_VALUE
    assert IDENTITY_VALUE not in [f["reset"] for f in description()]


def test_the_hash_moves_when_a_field_moves():
    """The whole point of it. A map differing in anything a host acts on has to
    hash differently, or the check passes while the two ends disagree."""
    moved = copy.deepcopy(description())
    moved[-1]["shift"] += 1
    assert hash_of(moved) != MAP_HASH


def test_the_hash_ignores_the_order_the_fields_are_described_in():
    """So reordering a declaration does not read as a map change to every host
    already in the field."""
    assert hash_of(list(reversed(description()))) == MAP_HASH
