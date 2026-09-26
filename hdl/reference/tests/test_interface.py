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
RTL_N_BITS = re.compile(r"^\s*parameter\s+(?:integer\s+)?N_BITS\s*=\s*(\d+)", re.M)

#: Terminals in a symbol file, one per line: `B <n> <coords...> {name=.. dir=..}`
TERMINAL = re.compile(r"^B\s+(?:\S+\s+){5}\{name=(?P<name>\S+)\s+dir=(?P<dir>\w+)\}", re.M)

#: A resolution, or an array size derived from one, spelled out as a number.
#: Prose that states one is a second copy of the constant that no test reads.
PROSE_RESOLUTION = re.compile(r"\b\d+(?:-|\s+)bits?\b|\b\d+-(?:cell|unit)\b", re.I)

#: Prose is every Markdown file and every extensionless README, wherever it
#: sits. Generated trees are not ours to word, and working notes are not
#: documentation.
PROSE_EXCLUDED = {".git", ".claude", "build", "runs"}


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
    sources = sorted(RTL_DIR.rglob("*.v"))
    if not sources:
        pytest.skip("no RTL yet")
    declared = [
        (path.name, int(m.group(1)))
        for path in sources
        for m in RTL_N_BITS.finditer(path.read_text())
    ]
    assert declared, "RTL exists but declares no resolution to check"
    for name, value in declared:
        assert value == N_BITS, f"{name} defaults to {value}, contract says {N_BITS}"


def test_no_document_restates_the_resolution():
    """Code is checked against the contract; prose is checked by nobody. A
    document that names a resolution by number is right until the day it is
    changed, and then it is trusted. Name `N_BITS` instead."""
    prose = [
        path
        for path in REPO.rglob("*")
        if path.is_file()
        and (path.suffix == ".md" or path.name == "README")
        and not PROSE_EXCLUDED & set(path.relative_to(REPO).parts)
    ]
    # Whole files, not lines: prose wraps, and a number left at the end of one
    # line is still a number.
    stated = [
        f"{path.relative_to(REPO)}:{text.count(chr(10), 0, m.start()) + 1}: {m.group(0)!r}"
        for path in prose
        for text in [path.read_text()]
        for m in PROSE_RESOLUTION.finditer(text)
    ]
    assert not stated, "resolution stated in prose:\n" + "\n".join(stated)
