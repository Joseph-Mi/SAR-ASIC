"""The pin map, enforced.

A pin assignment nobody checks drifts: a signal lands on two pins, a result bit
goes missing, or a pin the design never drives is left enabled and fights the
board. Each of those is a silent defect at the one boundary that cannot be
changed after submission.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from interface import N_BITS
from pins import (
    DIRECTIONS,
    GROUP_WIDTH,
    GROUPS,
    IN,
    OUT,
    SPI_PINS,
    SPILLED,
    UI_IN,
    UIO,
    UO_OUT,
    assignments,
    code_bit,
    code_pins,
    uio_oe,
)

REPO = next(p for p in pathlib.Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
RTL_DIR = REPO / "hdl" / "rtl"

#: An output-enable word written out in the RTL. Deriving it in two places is
#: two values that drift; this finds the copy so the test can compare it.
RTL_UIO_OE = re.compile(r"localparam\s+(?:\[[^\]]*\]\s*)?UIO_OE\s*=\s*\d+'b([01_]+)", re.M)

#: Groups the platform fixes the direction of, and that direction.
FIXED_DIRECTION = {"ui_in": IN, "uo_out": OUT}


def test_every_signal_appears_on_exactly_one_pin():
    """A signal on two pins is driven twice; a signal on none is not wired."""
    placed = sorted(assignments().values())
    assert placed == sorted(DIRECTIONS)


def test_every_group_declares_a_pin_for_every_position():
    """A group short of a pin leaves one unaccounted for rather than spare."""
    for group, pins in GROUPS.items():
        assert len(pins) == GROUP_WIDTH, group


def test_the_result_is_carried_whole():
    """Every bit reaches a pin, or the converter's resolution is not readable."""
    assert len(code_pins()) == N_BITS
    assert len(set(code_pins())) == N_BITS


def test_the_dedicated_outputs_carry_the_most_significant_bits():
    """Those pins on their own have to read as a number over the whole input
    range. The least significant bits on their own wrap instead."""
    assert code_bit(N_BITS - 1) in UO_OUT
    if SPILLED:
        assert code_bit(0) not in UO_OUT


def test_the_dedicated_outputs_ascend_by_one():
    """Read as a word, the group is the result's top bits in order: a gap or a
    swap turns a monotonic ramp into a scramble that still looks plausible."""
    carried = [s for s in UO_OUT if s]
    indices = [int(s[s.index("[") + 1 : -1]) for s in carried]
    assert indices == list(range(indices[0], indices[0] + len(indices)))


@pytest.mark.parametrize("group", sorted(FIXED_DIRECTION))
def test_a_fixed_direction_group_carries_nothing_that_points_the_other_way(group):
    """The platform decides these two groups' direction; a signal placed
    against it cannot work and will not be reported as miswired."""
    for signal in GROUPS[group]:
        if signal:
            assert DIRECTIONS[signal] == FIXED_DIRECTION[group], signal


def test_output_enables_are_set_exactly_where_the_design_drives():
    want = sum(1 << i for i, s in enumerate(UIO) if s and DIRECTIONS[s] == OUT)
    assert uio_oe() == want


def test_a_pin_the_design_does_not_use_is_not_enabled():
    """An unused bidirectional pin left enabled drives against the board."""
    for i, signal in enumerate(UIO):
        if signal is None:
            assert not uio_oe() >> i & 1


def test_an_input_on_the_bidirectional_group_is_not_enabled():
    """Enabling a pin the chip is meant to read shorts the driver against it."""
    for i, signal in enumerate(UIO):
        if signal and DIRECTIONS[signal] == IN:
            assert not uio_oe() >> i & 1


def test_spi_sits_where_the_platform_puts_it():
    """The convention is what lets an off-the-shelf daughterboard talk to the
    chip without rewiring, so it is worth more than a tidier map."""
    assert UIO[: len(SPI_PINS)] == SPI_PINS


def test_the_hold_pin_is_an_input():
    """It is driven from outside -- a button, or the board's microcontroller."""
    assert DIRECTIONS[UI_IN[0]] == IN


def test_the_rtl_restates_no_output_enable_word():
    """The word is derived from the map. A copy in the RTL is a second value
    that is right until the map changes."""
    sources = sorted(RTL_DIR.rglob("*.v"))
    found = [
        (path.name, int(m.group(1).replace("_", ""), 2))
        for path in sources
        for m in RTL_UIO_OE.finditer(path.read_text())
    ]
    if not found:
        pytest.skip("no RTL declares an output-enable word yet")
    for name, value in found:
        assert value == uio_oe(), f"{name} enables {value:#010b}, the map says {uio_oe():#010b}"
