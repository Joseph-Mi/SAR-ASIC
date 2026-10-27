"""The latch as a schematic sheet, generated from the netlist it has to match.

A schematic is how an analog circuit is reviewed by a person, and this one is
also what LVS is handed once the comparator is laid out. What it is not is a
second place the sizing lives. `strongarm.subckt` already builds this circuit
for every bench in the repository, so a sheet drawn beside it by hand would be
a copy of twenty geometries that nothing compares, and the copy would be wrong
the first time one of them moved. So the sheet is generated from that netlist
and committed, the way the register map is, and a test netlists it back and
holds the two together.

What generating it cannot do is arrange it. Devices land on a grid, each one's
gate pulled left, drain up, source down and bulk right, and nets are joined by
name rather than by a drawn wire. That reads, and it is not the drawing a
person would make. Rearranging it in the editor is free: the test compares
what the sheet netlists and never where anything sits.

The transistors carry width, length and finger count only, and let the PDK
symbol's own expressions derive the junction geometry from them -- which is
what makes editing a width in the editor correct rather than half-correct.
That those expressions agree with `tech/sky130.py`'s is not assumed here: the
test compares every parameter the two emit.
"""

from __future__ import annotations

import pathlib
import re
import shutil
from dataclasses import dataclass

import devices
import strongarm
from devices import pdk_library

#: The repository root: the nearest folder up that holds the project's own
#: configuration, however deep this file is moved.
REPO = next(p for p in pathlib.Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
SHEET_DIR = REPO / "xschem"
SHEET = SHEET_DIR / f"{strongarm.NAME}.sch"
SYMBOL = SHEET_DIR / f"{strongarm.NAME}.sym"

#: The format line the editor writes. Carried rather than invented so a
#: generated sheet opens as the committed one does instead of being upgraded
#: on its first save.
FORMAT = "v {xschem version=3.4.8RC file_version=1.3}"

#: The empty sections every sheet carries between its format line and its
#: contents. The editor writes them whether or not they hold anything.
SECTIONS = ("G {}", "K {}", "V {}", "S {}", "F {}", "E {}")

#: One transistor as the PDK's wrapper, which is what `devices.Sky130` emits:
#: an X instance of a named model, its four terminals, then the geometry.
MOS = re.compile(
    r"^X(?P<name>\S+)\s+(?P<d>\S+)\s+(?P<g>\S+)\s+(?P<s>\S+)\s+(?P<b>\S+)\s+"
    r"(?P<model>\S+)\s+(?P<params>.+)$",
    re.M,
)

#: One capacitance added to a node. Not a device the PDK draws but a design
#: knob the netlist states as an ideal element, so the sheet states it the
#: same way and layout decides later what builds it.
CAP = re.compile(r"^C(?P<name>\S+)\s+(?P<plus>\S+)\s+(?P<minus>\S+)\s+(?P<value>\S+)$", re.M)

#: The geometry an instance carries, out of everything the netlister computes.
#: The rest the symbol derives from these, which is the point of leaving it to
#: the symbol.
#:
#: `m` is here although the symbol's own format string already asks for it:
#: the editor leaves that out unless the instance states it, and `m` is what
#: a device too wide for the models is built out of -- equal fingers in
#: parallel. A sheet without it is one device where the bench has several,
#: which is the defect that once read as a reference switch five hundred
#: times too small. `mult` rides along because the wrapper scales its
#: mismatch term by it and the two have to stay equal.
DRAWN = ("W", "L", "nf", "mult", "m")

#: The editor's own symbols: a net name, and the three kinds of port.
LABEL = "lab_pin.sym"
PORT = {"in": "ipin.sym", "out": "opin.sym", "inout": "iopin.sym"}

#: An ideal capacitor, which is what the netlist says these are.
CAPACITOR = "capa.sym"

#: Which terminal of the netlist's device line each symbol pin carries. A
#: transistor's four are named by the symbol and the netlist states them in
#: this order; a capacitor's two are its plates.
MOS_TERMINALS = ("D", "G", "S", "B")
CAP_TERMINALS = ("p", "m")

#: A terminal in a symbol file: a small box the editor snaps a wire to.
#: Read rather than tabulated, because the two flavours do not agree -- a
#: PMOS is drawn source upwards, so its drain sits where an NMOS keeps its
#: source. A table of offsets written from one of them silently swaps the
#: other's two, which netlists as a circuit that is wrong and looks right.
PIN = re.compile(
    r"^B\s+\S+\s+(?P<x1>\S+)\s+(?P<y1>\S+)\s+(?P<x2>\S+)\s+(?P<y2>\S+)\s+"
    r"\{name=(?P<name>\S+)\s+dir=(?P<dir>\w+)",
    re.M,
)

#: How far a net's label sits off the pin it names, along and across.
STUB = 30
REACH = 60

#: The grid. Wide enough that a label and the next device's label do not
#: collide at the longest net name this circuit has.
COLUMNS = 5
PITCH_X = 240
PITCH_Y = 200

#: The ports, in a column clear of the leftmost gate label.
PORT_X = -320
PORT_PITCH = 40


def symbol_for(model: str) -> str:
    """The PDK's editor symbol for one of its devices.

    The library and the device are the two halves of the model's own name, so
    this is a rename rather than a second table that could name a symbol the
    netlist does not instantiate.
    """
    library, _, device = model.partition("__")
    return f"{library}/{device}.sym"


#: Where the editor keeps the symbols that are not the PDK's: its own device
#: library, beside the binary that reads it.
def library_roots() -> list[pathlib.Path]:
    """Every directory a symbol may be named relative to, in search order.

    Derived from the tools rather than written down: the editor's share
    directory sits beside its binary, and the PDK's symbols sit where its own
    configuration puts them. A path spelled out here would be a third copy of
    where the image keeps things, and would be wrong on the next image.
    """
    binary = shutil.which("xschem")
    roots = []
    if binary is not None:
        share = pathlib.Path(binary).resolve().parent.parent / "share" / "xschem"
        roots += [share / "xschem_library" / "devices", share / "xschem_library"]
    roots.append(pdk_library().parent.parent / "xschem")
    return roots


def pins(symbol: str) -> dict[str, tuple[float, float]]:
    """Each terminal of a symbol, and where it sits relative to the origin.

    A net is connected to a terminal by carrying a label at the terminal's own
    coordinate, so these are the connectivity and not the drawing.
    """
    found = next((root / symbol for root in library_roots() if (root / symbol).exists()), None)
    if found is None:
        raise FileNotFoundError(f"{symbol} is in none of {[str(r) for r in library_roots()]}")
    centres = {}
    for pin in PIN.finditer(found.read_text()):
        x = (float(pin["x1"]) + float(pin["x2"])) / 2
        y = (float(pin["y1"]) + float(pin["y2"])) / 2
        centres[pin["name"]] = (x, y)
    return centres


def label_at(x: float, y: float) -> tuple[float, float]:
    """Where to put the label for a terminal sitting at (x, y).

    The terminal's own position says which way it faces: one above or below
    the body is labelled further that way, and one out to a side is labelled
    further out. That is one rule for every symbol, and it keeps the four
    terminals of a transistor from landing on each other whichever flavour
    the symbol is drawn as.
    """
    if abs(y) > abs(x):
        return (x, y + STUB * (1 if y > 0 else -1))
    return (x + REACH * (1 if x > 0 else -1), y)


@dataclass(frozen=True)
class Element:
    """One thing on the sheet: its symbol, its attributes, and which net each
    of its terminals carries."""

    symbol: str
    attributes: str
    nets: dict[str, str]


def _parameters(text: str) -> dict[str, str]:
    """`k=v k=v` as written by the netlister."""
    return dict(pair.split("=", 1) for pair in text.split())


def elements(netlist: str) -> list[Element]:
    """Everything in a subcircuit that has to appear on its sheet.

    Lines that are neither a device nor a capacitance -- the subcircuit's own
    declaration and its end -- are the sheet's ports instead, and are drawn
    from the interface rather than parsed back out of the netlist.
    """
    found: list[Element] = []
    for line in netlist.splitlines():
        if (mos := MOS.match(line)) is not None:
            geometry = _parameters(mos["params"])
            drawn = " ".join(f"{key}={geometry[key]}" for key in DRAWN)
            found.append(
                Element(
                    symbol=symbol_for(mos["model"]),
                    attributes=f"name={mos['name']} {drawn}",
                    nets=dict(
                        zip(
                            MOS_TERMINALS,
                            (mos["d"], mos["g"], mos["s"], mos["b"]),
                            strict=True,
                        )
                    ),
                )
            )
        elif (cap := CAP.match(line)) is not None:
            found.append(
                Element(
                    symbol=CAPACITOR,
                    attributes=f"name=C{cap['name']} value={cap['value']}",
                    nets=dict(zip(CAP_TERMINALS, (cap["plus"], cap["minus"]), strict=True)),
                )
            )
    return found


def _placed(symbol: str, x: float, y: float, attributes: str) -> str:
    return f"C {{{symbol}}} {x:g} {y:g} 0 0 {{{attributes}}}"


def sheet(sizes: strongarm.Sizes | None = None, netlister=None) -> str:
    """The sheet, text, for one sizing built by one netlister.

    The netlister is the same object the benches hand `subckt`, so the sheet
    carries the PDK's devices because the benches do, and a sheet of generic
    models could be asked for by passing the other one.
    """
    sizes = strongarm.DESIGNED if sizes is None else sizes
    netlister = devices.Sky130() if netlister is None else netlister

    records = [FORMAT, *SECTIONS]

    for index, terminal in enumerate(strongarm.TERMINALS):
        direction = strongarm.DIRECTIONS[terminal]
        y = index * PORT_PITCH
        records.append(_placed(PORT[direction], PORT_X, y, f"name=p{index} lab={terminal}"))

    marks = 0
    for slot, element in enumerate(elements(strongarm.subckt(sizes, netlister))):
        x = (slot % COLUMNS) * PITCH_X
        y = (slot // COLUMNS) * PITCH_Y
        records.append(_placed(element.symbol, x, y, element.attributes))
        placed = pins(element.symbol)
        for terminal, net in element.nets.items():
            px, py = placed[terminal]
            lx, ly = label_at(px, py)
            records.append(f"N {x + px:g} {y + py:g} {x + lx:g} {y + ly:g} {{lab={net}}}")
            records.append(_placed(LABEL, x + lx, y + ly, f"name=l{marks} lab={net}"))
            marks += 1

    return "\n".join(records) + "\n"


#: The symbol's box, and where its pins sit on the two sides of it. The pin
#: itself is a small box the editor snaps a wire to; the line is the stub
#: drawn out to it and the text is what a reader sees.
BOX_X = 130
PIN_X = 150
PIN_PITCH = 20
PIN_BOX = 2.5
BOX_MARGIN = 20

#: Wire colours the editor draws with: a supply is a different colour from a
#: signal, which is the one thing about a symbol that stops a supply being
#: read as just another pin.
SIGNAL_COLOUR = 4
SUPPLY_COLOUR = 7

#: Text sizes, as the committed symbol uses them.
NAME_SIZE = 0.3
PIN_SIZE = 0.2


def _pin(name: str, direction: str, side: int, y: int) -> list[str]:
    """One terminal: its snap box, its stub, and its label."""
    colour = SUPPLY_COLOUR if direction == "inout" else SIGNAL_COLOUR
    x = side * PIN_X
    justify = 0 if side < 0 else 1
    return [
        f"B 5 {x - PIN_BOX} {y - PIN_BOX} {x + PIN_BOX} {y + PIN_BOX} "
        f"{{name={name} dir={direction}}}",
        f"L {colour} {x} {y} {side * BOX_X} {y} {{}}",
        f"T {{{name}}} {side * (BOX_X - 5)} {y - 4} 0 {justify} {PIN_SIZE} {PIN_SIZE} {{}}",
    ]


def symbol(name: str = strongarm.NAME) -> str:
    """The symbol, text, declaring exactly the subcircuit's terminals.

    Inputs on the left and everything the circuit drives or shares on the
    right, which is the convention the committed block symbol follows. The
    terminals and their directions come from the subcircuit, so the symbol
    cannot declare a pin the netlist does not have.
    """
    left = [t for t in strongarm.TERMINALS if strongarm.DIRECTIONS[t] == "in"]
    right = [t for t in strongarm.TERMINALS if strongarm.DIRECTIONS[t] != "in"]
    rows = max(len(left), len(right))
    top = -(rows - 1) * PIN_PITCH // 2

    records = [
        FORMAT,
        "K {type=subcircuit",
        'format="@name @pinlist @symname"',
        'spectre_format="@name ( @pinlist ) @symname"',
        'template="name=x1"',
        "}",
        "V {}",
        "S {}",
        "E {}",
        f"T {{@symname}} -63 -6 0 0 {NAME_SIZE} {NAME_SIZE} {{}}",
        f"T {{@name}} {BOX_X + 5} {top - 12} 0 0 {PIN_SIZE} {PIN_SIZE} {{}}",
    ]

    low = top - BOX_MARGIN
    high = top + (rows - 1) * PIN_PITCH + BOX_MARGIN
    records.append(
        f"P 4 5 {BOX_X} {low} {-BOX_X} {low} {-BOX_X} {high} {BOX_X} {high} {BOX_X} {low} {{}}"
    )

    for side, terminals in ((-1, left), (1, right)):
        for index, terminal in enumerate(terminals):
            records += _pin(terminal, strongarm.DIRECTIONS[terminal], side, top + index * PIN_PITCH)

    return "\n".join(records) + "\n"


def main() -> None:
    """Write both files. The sheet is committed, so the diff is the review."""
    SHEET.write_text(sheet())
    SYMBOL.write_text(symbol())
    print(f"wrote {SHEET.relative_to(REPO)} and {SYMBOL.relative_to(REPO)}")


if __name__ == "__main__":
    main()
