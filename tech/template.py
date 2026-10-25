"""What the TinyTapeout tile template declares: the die, the pins, and which
edge each one sits on.

Contract: the platform's own file is the authority, not a transcription of it.
`layout/tt_analog_2x2.def` is vendored unmodified from the shuttle's support
tools -- it is the file the pins are actually placed from -- so everything
here is read out of it rather than written down beside it. Nothing in this
module depends on anything else in the repository.

Reading it is worth more than it looks. The port list of the tile top, the
die the floorplan budget divides, the width of the analog group and the pitch
the analog pins sit on are four facts that are otherwise copied by hand into
four places, at the one boundary that cannot be corrected after submission.

What is deliberately *not* here: the power nets. The template carries `VPWR`
and `VGND` as special nets, while the shuttle's Verilog template names the
supplies `VGND` and `VDPWR`, and the two disagree. A reader that picked one
would be making a submission decision in a parser, so the supplies are left
to the tile top and the discrepancy to `docs/floorplan.md`.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass

#: The vendored template, beside this package rather than under it: it is
#: layout's copy of a layout file, and `layout/PROVENANCE` says where from.
PATH = pathlib.Path(__file__).resolve().parent.parent / "layout" / "tt_analog_2x2.def"

#: Database units per micrometre, as the file's own UNITS line gives them.
_UNITS = re.compile(r"^UNITS\s+DISTANCE\s+MICRONS\s+(\d+)\s*;", re.M)

#: The die's far corner. The near one is the origin in every template drawn so
#: far, and the reader checks that rather than assuming it.
_DIEAREA = re.compile(
    r"^DIEAREA\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*;", re.M
)

#: How many pins the section says it holds, so a truncated read is caught
#: rather than quietly returning fewer.
_COUNT = re.compile(r"^PINS\s+(\d+)\s*;", re.M)

#: One pin: its name, possibly a bus bit, its direction, and where it is
#: placed. The layer and the port box are on the lines between.
_PIN = re.compile(
    r"^\s*-\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:\[(?P<bit>\d+)\])?\s+"
    r"\+\s+NET\s+\S+\s+\+\s+DIRECTION\s+(?P<direction>[A-Z]+)\s+\+\s+USE\s+(?P<use>[A-Z]+)"
    r".*?\+\s+LAYER\s+(?P<layer>\S+)"
    r".*?\+\s+PLACED\s*\(\s*(?P<x>-?\d+)\s+(?P<y>-?\d+)\s*\)",
    re.M | re.S,
)

#: Directions as DEF spells them, mapped to the way Verilog does.
VERILOG_DIRECTION = {"INPUT": "input", "OUTPUT": "output", "INOUT": "inout"}


@dataclass(frozen=True)
class Pin:
    """One pin of the template, in micrometres.

    `bit` is None for a pin that is not part of a bus, which is how a scalar
    port and a one-bit bus stay distinguishable -- the tile top has to declare
    each the way the template does.
    """

    name: str
    bit: int | None
    direction: str
    layer: str
    x: float
    y: float

    @property
    def declaration(self) -> str:
        """The pin as a net name, bus bit included."""
        return self.name if self.bit is None else f"{self.name}[{self.bit}]"


@dataclass(frozen=True)
class Group:
    """A port of the tile top: one pin, or a bus of them."""

    name: str
    width: int
    direction: str

    @property
    def declaration(self) -> str:
        """How Verilog has to declare it, without the name."""
        kind = VERILOG_DIRECTION[self.direction]
        return kind if self.width == 1 else f"{kind} [{self.width - 1}:0]"


def _text() -> str:
    if not PATH.exists():
        raise FileNotFoundError(f"the vendored template is missing from {PATH}")
    return PATH.read_text()


def units() -> int:
    """Database units per micrometre."""
    found = _UNITS.search(_text())
    if not found:
        raise ValueError(f"{PATH.name} declares no UNITS line")
    return int(found.group(1))


def die_area() -> tuple[float, float]:
    """The tile's width and height, micrometres."""
    found = _DIEAREA.search(_text())
    if not found:
        raise ValueError(f"{PATH.name} declares no DIEAREA")
    x0, y0, x1, y1 = (int(v) for v in found.groups())
    if (x0, y0) != (0, 0):
        raise ValueError(f"{PATH.name} does not start its die at the origin: ({x0}, {y0})")
    per = units()
    return x1 / per, y1 / per


def pins() -> list[Pin]:
    """Every pin the template declares, in the order it declares them.

    The count in the section header is checked against what was read: a
    pattern that stops matching partway through a file returns a shorter list
    and no error, which is the one failure mode a reader like this has.
    """
    text = _text()
    declared = _COUNT.search(text)
    if not declared:
        raise ValueError(f"{PATH.name} declares no PINS section")
    body = text[text.index("PINS") : text.index("END PINS")]
    per = units()
    found = [
        Pin(
            name=m.group("name"),
            bit=None if m.group("bit") is None else int(m.group("bit")),
            direction=m.group("direction"),
            layer=m.group("layer"),
            x=int(m.group("x")) / per,
            y=int(m.group("y")) / per,
        )
        for m in _PIN.finditer(body)
    ]
    if len(found) != int(declared.group(1)):
        raise ValueError(
            f"{PATH.name} says it holds {declared.group(1)} pins and {len(found)} were read"
        )
    return found


def groups() -> dict[str, Group]:
    """The template's pins collected into ports, keyed by name.

    A bus is as wide as its highest bit plus one, and a gap in the middle of
    one is refused: it would read as a narrower port that happens to elaborate.
    """
    collected: dict[str, list[Pin]] = {}
    for pin in pins():
        collected.setdefault(pin.name, []).append(pin)
    built = {}
    for name, found in collected.items():
        directions = {p.direction for p in found}
        if len(directions) > 1:
            raise ValueError(f"{name} points {len(directions)} ways: {sorted(directions)}")
        bits = sorted(p.bit for p in found if p.bit is not None)
        if not bits:
            if len(found) != 1:
                raise ValueError(f"{name} appears {len(found)} times without a bus index")
            width = 1
        elif bits != list(range(len(bits))):
            raise ValueError(f"{name} is missing bus bits: {bits}")
        else:
            width = len(bits)
        built[name] = Group(name=name, width=width, direction=found[0].direction)
    return built


#: The tile size in the template's file name, which is how the platform spells
#: it in a submission too.
_TILES = re.compile(r"_(\d+x\d+)(?:_|$)")


def tiles() -> str:
    """How many tiles the template draws, as the platform writes it.

    Taken from the vendored file's name rather than from the die, because that
    string is what a submission has to repeat and the name is where it is
    already written.
    """
    found = _TILES.search(PATH.stem)
    if not found:
        raise ValueError(f"{PATH.name} does not name a tile size")
    return found.group(1)


def analog_group() -> Group:
    """The analog port, whose width is how many pins the template draws -- not
    how many the platform will connect, which is the specification's limit and
    smaller."""
    found = groups()
    analog = [g for g in found.values() if g.direction == "INOUT"]
    if len(analog) != 1:
        raise ValueError(f"{PATH.name} has {len(analog)} bidirectional ports, expected one")
    return analog[0]


def analog_pitch() -> float:
    """How far apart consecutive analog pins sit, micrometres.

    Every gap is checked rather than the first one: a template that moved one
    pin would otherwise read as evenly spaced.
    """
    name = analog_group().name
    placed = sorted((p.bit, p.x) for p in pins() if p.name == name and p.bit is not None)
    gaps = {round(abs(b - a), 6) for (_, a), (_, b) in zip(placed, placed[1:], strict=False)}
    if len(gaps) != 1:
        raise ValueError(f"the analog pins are not evenly spaced: {sorted(gaps)}")
    return gaps.pop()
