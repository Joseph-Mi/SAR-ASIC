"""The tile top, enforced against the two things it is not free to choose.

Its port list is the platform's, and the platform ships the authority for it:
the DEF the shuttle places the pins from, vendored in `layout/`. Its other
face is the frozen boundary in `interface.py`, which the analog half's Verilog
declaration has to match the same way the Xschem symbol does.

Both are copies, and a copy nobody compares is the defect this file exists to
catch. A port named wrongly here is a pin that is not connected, found after
submission or not at all.
"""

from __future__ import annotations

import pathlib
import re

import pytest

import submission
import template
from interface import N_BITS, PORTS
from pins import ANALOG_WIDTH, analog_pins
from tinytapeout import GROUND, SUPPLY

REPO = next(p for p in pathlib.Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
RTL_DIR = REPO / "hdl" / "rtl"

#: The platform's name for a tile top. The shuttle requires the prefix, the
#: module name and the GDS and LEF file names beside it all agree, and that it
#: be unique on the shuttle -- which is what the rest of the name is for.
TT_PREFIX = "tt_um_"

#: One port of a Verilog module: a direction, an optional range, a name. The
#: range is kept as written rather than evaluated, because a width given as a
#: parameter expression is the thing worth checking, not a number.
PORT = re.compile(
    r"^\s*(?P<direction>input|output|inout)\s+wire\s*"
    r"(?:\[\s*(?P<range>[^\]]+?)\s*\])?\s*"
    # A trailing comment may sit between the last port's name and the closing
    # parenthesis, which is how the platform's own template writes it.
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?:[ \t]*//[^\n]*)?\s*[,)]",
    re.M,
)

#: How the contract's directions are spelled in Verilog.
VERILOG = {"in": "input", "out": "output", "inout": "inout"}


def _port_list(path: pathlib.Path) -> str:
    """Just the module's port list, so a parameter default or a body cannot be
    read as a port."""
    text = path.read_text()
    opened = text.index("(", text.index("module "))
    if text[:opened].rstrip().endswith("#"):
        opened = text.index("(", text.index(")", opened) + 1)
    return text[opened : text.index(");", opened) + 2]


def _ports(path: pathlib.Path) -> dict[str, tuple[str, int]]:
    """Each port of a module, as a direction and a width.

    A range written against the resolution resolves to it: the RTL may not
    restate the width, and `test_interface` already holds the parameter's
    default against the contract, so `N_BITS-1:0` is that many bits.
    """
    found = {}
    for m in PORT.finditer(_port_list(path)):
        written = m.group("range")
        if written is None:
            width = 1
        elif written == "N_BITS-1:0":
            width = N_BITS
        else:
            high, low = (int(v) for v in written.split(":"))
            assert low == 0, f"{m.group('name')} is declared [{written}], not down to zero"
            width = high + 1
        found[m.group("name")] = (m.group("direction"), width)
    return found


def tile_top() -> pathlib.Path:
    """The one tile top in the tree.

    One, because the shuttle takes one: a second would elaborate, lint and
    pass every test here while being the file that is not submitted.
    """
    found = sorted(RTL_DIR.glob(f"{TT_PREFIX}*.v"))
    if not found:
        pytest.skip("no tile top yet")
    assert len(found) == 1, f"{len(found)} tile tops: {[p.name for p in found]}"
    return found[0]


def analog_face() -> pathlib.Path:
    path = RTL_DIR / "sar_analog.v"
    if not path.exists():
        pytest.skip("the analog half has no Verilog declaration yet")
    return path


def test_the_tile_top_is_named_the_way_the_shuttle_requires():
    """The module name, the file name and the GDS and LEF handed in beside them
    all have to be the same string."""
    path = tile_top()
    declared = re.search(r"^module\s+([A-Za-z_][A-Za-z0-9_]*)", path.read_text(), re.M)
    assert declared, "the tile top declares no module"
    assert declared.group(1) == path.stem, f"{path.name} declares {declared.group(1)}"
    assert declared.group(1).startswith(TT_PREFIX)
    assert declared.group(1) == submission.TOP_MODULE, (
        "the RTL and the file the shuttle reads name different modules"
    )


def test_the_tile_top_declares_every_pin_the_template_places():
    """The template is the file the shuttle places the pins from. A port it
    declares and this module does not is a pin left unconnected."""
    declared = _ports(tile_top())
    for name, group in sorted(template.groups().items()):
        want = (template.VERILOG_DIRECTION[group.direction], group.width)
        assert declared.get(name) == want, (
            f"{name}: the tile top says {declared.get(name)}, the template says {want}"
        )


def test_the_tile_top_declares_nothing_the_template_does_not_place():
    """Beyond the supplies, which the template carries as special nets rather
    than as pins and which the platform's Verilog declares as ports."""
    extra = set(_ports(tile_top())) - set(template.groups())
    assert extra == {GROUND, SUPPLY}, f"ports the template does not place: {sorted(extra)}"


def test_the_supplies_arrive_as_inputs():
    """Which is how the platform's template declares them, and the reason the
    tile top carries them across to the analog half by name rather than
    straight through its port map."""
    declared = _ports(tile_top())
    for name in (GROUND, SUPPLY):
        assert declared[name] == ("input", 1), f"{name} is {declared[name]}"


def test_the_design_claims_no_more_analog_pins_than_the_platform_connects():
    """The template draws more analog pins than the specification allows, so
    the port's width is not the limit -- a signal on a pin past the limit looks
    routed and is not bonded."""
    assert ANALOG_WIDTH <= template.analog_group().width
    assert len(analog_pins()) <= ANALOG_WIDTH


def test_the_analog_pins_are_claimed_from_the_first_one_upward():
    """The platform connects them in order as the submission declares them, so
    a gap is a pin paid for and left unbonded."""
    from pins import UA

    claimed = [index for index, signal in enumerate(UA) if signal]
    assert claimed == list(range(len(claimed))), f"the analog pins are claimed at {claimed}"


def test_the_analog_half_declares_the_frozen_boundary():
    """Its Verilog face is the contract, the same way the symbol is: every
    name, direction and width, and nothing else."""
    declared = _ports(analog_face())
    want = {p.name: (VERILOG[p.direction], p.width) for p in PORTS}
    assert declared == want, f"declared {declared}, the contract says {want}"


def test_the_analog_half_is_a_blackbox():
    """It has no body and cannot have one -- it is hand-drawn layout -- and
    saying so is what stops the structural check looking for logic that was
    never written, and makes its outputs count as driven."""
    assert "(* blackbox *)" in analog_face().read_text()
