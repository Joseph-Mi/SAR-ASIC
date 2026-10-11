"""The pin timing contract, and the one place it is allowed to come from.

A bound that is right because someone wrote the right number down is a bound
that stops being right silently. These check it is derived, that the
derivation is the conservative one, and that the RTL has not grown a second
copy of the synchroniser depth it rests on.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from registers import REGISTER_WIDTH
from timing import (
    EDGES_PER_LEVEL,
    MIN_LEVEL_CYCLES,
    SYNCHRONISER_STAGES,
    edges_guaranteed,
    frame_cycles,
    latency_cycles,
    max_wire_fraction,
    min_wire_period_cycles,
)

REPO = next(p for p in pathlib.Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
RTL_DIR = REPO / "hdl" / "rtl"

#: The synchroniser's declared depth in the RTL. The design cannot read this
#: module, so the depth is a copy, and a copy nobody compares is what lets the
#: bound and the hardware drift apart.
RTL_STAGES = re.compile(r"localparam\s+integer\s+STAGES\s*=\s*(\d+)\s*;", re.M)

#: Longest frame to check the cycle count against.
FRAME_BYTES = 4


def test_the_minimum_level_is_derived_and_not_declared():
    """One cycle is what a careless bound would say, and it is wrong: a level
    exactly a cycle long can fall between two sampling instants."""
    assert edges_guaranteed(1) < EDGES_PER_LEVEL
    assert edges_guaranteed(MIN_LEVEL_CYCLES) >= EDGES_PER_LEVEL
    assert MIN_LEVEL_CYCLES > 1


def test_the_guarantee_is_the_pessimistic_count():
    """A lucky alignment sees one edge per cycle. The bound has to assume the
    unlucky one, which sees one fewer."""
    for cycles in range(0, 8):
        assert edges_guaranteed(cycles) == max(0, cycles - 1)


def test_a_negative_duration_is_refused():
    with pytest.raises(ValueError):
        edges_guaranteed(-1)


def test_a_wire_period_is_two_levels_because_an_edge_needs_both():
    """An edge detector compares a level against the one before it, so a
    period that registers only one of its phases registers no edges."""
    assert min_wire_period_cycles() == 2 * MIN_LEVEL_CYCLES
    assert max_wire_fraction() == 1.0 / min_wire_period_cycles()
    assert 0.0 < max_wire_fraction() < 1.0


def test_the_latency_counts_the_stages_and_the_cycle_that_uses_them():
    """A bench that waits only for the synchroniser reads the pin's effect one
    cycle before it exists."""
    assert latency_cycles() == SYNCHRONISER_STAGES + 1


def test_a_frame_is_as_long_as_its_bits_at_the_fastest_legal_rate():
    """So a bench can wait for a frame rather than guess at it, and so a rate
    can be quoted for the configuration interface."""
    for data_bytes in range(FRAME_BYTES + 1):
        bits = (1 + data_bytes) * REGISTER_WIDTH
        expected = bits * min_wire_period_cycles() + 2 * MIN_LEVEL_CYCLES
        assert frame_cycles(data_bytes, REGISTER_WIDTH) == expected
    assert frame_cycles(1, REGISTER_WIDTH) > frame_cycles(0, REGISTER_WIDTH)


def test_a_frame_of_negative_bytes_is_refused():
    with pytest.raises(ValueError):
        frame_cycles(-1, REGISTER_WIDTH)


def test_the_rtl_synchroniser_is_as_deep_as_the_bound_assumes():
    """The bound rests on the pin being resolved before it is read. A shallower
    synchroniser in the RTL would make every figure here optimistic."""
    found = [
        (path.name, int(m.group(1)))
        for path in sorted(RTL_DIR.rglob("*.v"))
        for m in RTL_STAGES.finditer(path.read_text())
    ]
    if not found:
        pytest.skip("no RTL declares a synchroniser depth yet")
    for name, stages in found:
        assert stages == SYNCHRONISER_STAGES, (
            f"{name} synchronises through {stages} stages, the contract assumes "
            f"{SYNCHRONISER_STAGES}"
        )
