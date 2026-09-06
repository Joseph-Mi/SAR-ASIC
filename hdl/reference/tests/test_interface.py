"""The interface freeze, enforced.

A committed symbol that nothing checks drifts the first time someone adds a pin
in the editor. This asserts the symbol still declares exactly what the contract
says, so changing the boundary is a deliberate edit in two places rather than
an accident in one.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from interface import N_BITS, PORTS, declarations

REPO = pathlib.Path(__file__).resolve().parents[3]
SYMBOL = REPO / "xschem" / "sar_analog.sym"
RTL_DIR = REPO / "hdl" / "rtl"

#: A resolution default in the RTL. Synthesis reads these, not the value a
#: testbench passes in, so a stale one ships even when every test is green.
RTL_N_BITS = re.compile(r"^\s*parameter\s+integer\s+N_BITS\s*=\s*(\d+)", re.M)

#: Terminals in a symbol file, one per line: `B <n> <coords...> {name=.. dir=..}`
TERMINAL = re.compile(r"^B\s+(?:\S+\s+){5}\{name=(?P<name>\S+)\s+dir=(?P<dir>\w+)\}", re.M)


@pytest.fixture(scope="module")
def declared() -> dict[str, str]:
    if not SYMBOL.exists():
        pytest.skip(f"{SYMBOL.name} not generated yet")
    return {m["name"]: m["dir"] for m in TERMINAL.finditer(SYMBOL.read_text())}


def test_symbol_declares_exactly_the_contract(declared):
    """No terminal appears on one side and not the other."""
    assert set(declared) == set(declarations())


def test_every_direction_agrees(declared):
    """A supply drawn as an input is a short nobody notices until LVS."""
    assert declared == declarations()


def test_the_bus_is_as_wide_as_the_resolution(declared):
    """Width is derived from the resolution, never restated beside it."""
    bus = next(p for p in PORTS if p.width > 1)
    assert f"{bus.name}[{N_BITS - 1}:0]" in declared


def test_the_comparator_returns_both_outputs(declared):
    """Both latch outputs cross the boundary: the two being equal is the
    metastability flag, and it cannot be formed from one of them."""
    assert declared["cmp_out"] == "out"
    assert declared["cmp_out_n"] == "out"


def test_the_reference_is_its_own_terminal(declared):
    """The array pulls charge from the reference on every bit trial, so it does
    not share a terminal with the supply that has to recover in time."""
    assert {"vref", "vdd"} <= set(declared)


def test_the_rtl_defaults_to_the_declared_resolution():
    """A testbench overrides the parameter; synthesis does not. The default is
    what reaches silicon, so it is the one that has to agree."""
    declared = [
        (path.name, int(m.group(1)))
        for path in sorted(RTL_DIR.glob("*.v"))
        for m in RTL_N_BITS.finditer(path.read_text())
    ]
    if not declared:
        pytest.skip("no RTL declares a resolution yet")
    for name, value in declared:
        assert value == N_BITS, f"{name} defaults to {value}, contract says {N_BITS}"
