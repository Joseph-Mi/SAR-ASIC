"""The latch as a schematic sheet, generated from the netlist it has to match.

A schematic is how an analog circuit is reviewed by a person, and this one is
also what LVS is handed once the comparator is laid out. What it is not is a
second place the sizing lives. `strongarm.subckt` already builds this circuit
for every bench in the repository, so a sheet drawn beside it by hand would be
a copy of twenty geometries that nothing compares, and the copy would be wrong
the first time one of them moved. So the sheet is generated from that netlist
and committed, the way the register map is, and a test netlists it back and
holds the two together.

What is generated is the connectivity. The *arrangement* is written down here
by hand, device by device, because a readable analog schematic is a drawing
and not an output: the two branches are mirror images about a vertical axis,
each one a stack from the supply down through the tail, the input pair, the
integration node, the regenerating pair and its load to ground, and the
cross-coupling is drawn as the two wires that cross so that the latch can be
recognised on sight. That matters beyond readability, because this drawing is
also the first draft of the layout -- a pair drawn symmetric is a pair that
gets drawn symmetric in silicon, which is what the offset spread depends on.

Three things about the editor that this had to be measured against rather than
assumed, each one capable of producing a wrong circuit that draws correctly:

* The two FET symbols are drawn opposite ways round. `pfet_01v8.sym` keeps its
  drain where `nfet_01v8.sym` keeps its source. Pin positions are therefore
  read out of each symbol rather than tabulated here.
* Mirroring moves the pins, so a mirrored device's terminals are where
  `transform` says and not where the symbol file says.
* Wires that merely cross are not connected, and a wire ending on another
  wire is. So the routing may cross freely and must never stop short.

What distribution gets instead of wires is a label, which is what a drawn
sheet does too: the supplies, every bulk tie, and the strobe on its six gates.
Drawing those would bury the circuit in wires that carry no information.
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

#: Which terminal of the netlist's device line each symbol pin carries. A
#: transistor's four are named by the symbol and the netlist states them in
#: this order; a capacitor's two are its plates.
MOS_TERMINALS = ("D", "G", "S", "B")
CAP_TERMINALS = ("p", "m")

#: The bulk terminal, which is labelled on every device rather than drawn.
BULK = "B"

#: Nets carried by label everywhere they appear, because each one reaches more
#: gates than a drawing can show without hiding the circuit under wires. The
#: strobe and its inverse are the latch's clock; they fan out to six gates.
LABELLED = ("clk", "clk_i")

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

#: The editor's own symbols: a net name, and the three kinds of port.
LABEL = "lab_pin.sym"
PORT = {"in": "ipin.sym", "out": "opin.sym", "inout": "iopin.sym"}

#: An ideal capacitor, which is what the netlist says these are.
CAPACITOR = "capa.sym"


def symbol_for(model: str) -> str:
    """The PDK's editor symbol for one of its devices.

    The library and the device are the two halves of the model's own name, so
    this is a rename rather than a second table that could name a symbol the
    netlist does not instantiate.
    """
    library, _, device = model.partition("__")
    return f"{library}/{device}.sym"


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
    """Each terminal of a symbol, and where it sits relative to the origin."""
    found = next((root / symbol for root in library_roots() if (root / symbol).exists()), None)
    if found is None:
        raise FileNotFoundError(f"{symbol} is in none of {[str(r) for r in library_roots()]}")
    centres = {}
    for pin in PIN.finditer(found.read_text()):
        x = (float(pin["x1"]) + float(pin["x2"])) / 2
        y = (float(pin["y1"]) + float(pin["y2"])) / 2
        centres[pin["name"]] = (x, y)
    return centres


def transform(x: float, y: float, rot: int, flip: int) -> tuple[float, float]:
    """Where a symbol's own coordinate lands once the instance is placed.

    The editor mirrors about the vertical axis first and then turns a quarter
    at a time. Measured against the editor over all eight orientations rather
    than taken from its documentation, because a mirrored transistor whose
    drain and source are read the wrong way round is a circuit that netlists
    wrong and draws right.
    """
    if flip:
        x = -x
    for _ in range(rot % 4):
        x, y = -y, x
    return x, y


def placed(symbol: str, x: float, y: float, rot: int, flip: int) -> dict[str, tuple[float, float]]:
    """Each terminal of one placed instance, in the sheet's own coordinates."""
    return {
        name: (x + dx, y + dy)
        for name, (px, py) in pins(symbol).items()
        for dx, dy in [transform(px, py, rot, flip)]
    }


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


def elements(netlist: str) -> dict[str, Element]:
    """Everything in a subcircuit that has to appear on its sheet, by name."""
    found: dict[str, Element] = {}
    for line in netlist.splitlines():
        if (mos := MOS.match(line)) is not None:
            geometry = _parameters(mos["params"])
            drawn = " ".join(f"{key}={geometry[key]}" for key in DRAWN)
            found[mos["name"]] = Element(
                symbol=symbol_for(mos["model"]),
                attributes=f"name={mos['name']} {drawn}",
                nets=dict(
                    zip(MOS_TERMINALS, (mos["d"], mos["g"], mos["s"], mos["b"]), strict=True)
                ),
            )
        elif (cap := CAP.match(line)) is not None:
            found[f"C{cap['name']}"] = Element(
                symbol=CAPACITOR,
                attributes=f"name=C{cap['name']} value={cap['value']}",
                nets=dict(zip(CAP_TERMINALS, (cap["plus"], cap["minus"]), strict=True)),
            )
    return found


# ---------------------------------------------------------------- the drawing
#
# One row per device: where it sits, how far it is turned, and whether it is
# mirrored. The right-hand branch is the left one mirrored, which is what puts
# both branches' gates on the outside and both channels symmetric about the
# axis. Written out rather than computed because this is a drawing.
#
# The vertical order, top to bottom, is the circuit's own: supply, tail, input
# pair, integration node, regenerating pair, load, ground.

#: The two supply rails, as horizontal trunks, and how far they run.
VDD_Y = -520
VSS_Y = 200
RAIL_LEFT = -1060
RAIL_RIGHT = 960

PLACEMENT: dict[str, tuple[int, int, int, int]] = {
    # the tail, on the axis, handing its current to both branches
    "tail": (-20, -440, 0, 0),
    # the input pair: left unmirrored, right mirrored, gates facing out
    "inp": (-200, -280, 0, 0),
    "inn": (200, -280, 0, 1),
    # the regenerating pair, sitting on the integration nodes
    "lchn": (-200, -100, 0, 0),
    "lchp": (200, -100, 0, 1),
    # its load to ground, which is the other half of the cross-coupling
    "ldn": (-200, 80, 0, 0),
    "ldp": (200, 80, 0, 1),
    # precharge, outboard of each branch: the integration nodes, then the
    # outputs, each on its own column so no riser runs through a device
    "prxn": (-400, -150, 0, 0),
    "prxp": (400, -150, 0, 1),
    "pren": (-560, 30, 0, 0),
    "prep": (560, 30, 0, 1),
    # the capacitance the noise target asks for, and the output load, furthest
    # out because nothing else has to reach past them
    "Cxn": (-680, -150, 0, 0),
    "Cxp": (680, -150, 0, 0),
    "Coutn": (-820, 30, 0, 0),
    "Coutp": (820, 30, 0, 0),
    # the one inverter, which buys the frozen strobe sense for a PMOS tail
    "invp": (-460, -440, 0, 0),
    "invn": (-460, -280, 0, 0),
    # the mirror: its reference device gated at the converter's reference, the
    # diode the tail copies, and the pair that hands the tail its gate
    "bdio": (-880, -440, 0, 0),
    "bref": (-880, -260, 0, 0),
    "bgoff": (-680, -440, 0, 0),
    "bgon": (-760, -320, 3, 0),
    "Cbias": (-1060, -350, 0, 0),
}

#: Where each terminal of the subcircuit is brought out. Attached to the
#: circuit rather than parked in a column, so the boundary is visible.
PORTS: dict[str, tuple[int, int]] = {
    "vdd": (RAIL_LEFT, VDD_Y),
    "vss": (RAIL_LEFT, VSS_Y),
    "vref": (-1000, -260),
    "clk": (-560, -360),
    "inp": (-320, -280),
    "inn": (320, -280),
    "outn": (-280, 30),
    "outp": (280, 30),
}

#: A name for each net the subcircuit keeps to itself, placed once on its own
#: wire. The editor invents a name for a net nothing labels, so without these
#: the sheet netlists the right circuit with the wrong node names -- which
#: reads as a different circuit to anything comparing the two, and reads as an
#: anonymous node to a person. Each coordinate is a point some wire ends at.
NAMED: dict[str, tuple[int, int]] = {
    "bias": (-900, -380),
    "tgate": (-660, -340),
    "tail": (0, -360),
    "xn": (-180, -180),
    "xp": (180, -180),
}

#: Every wire, as a segment. A segment either ends on a terminal or ends on
#: another segment; the editor joins both and joins neither when two merely
#: cross, so a crossing here is a crossing on paper and nothing more.
WIRES: tuple[tuple[int, int, int, int], ...] = (
    # the supplies, and everything that stands on them
    (RAIL_LEFT, VDD_Y, RAIL_RIGHT, VDD_Y),
    (RAIL_LEFT, VSS_Y, RAIL_RIGHT, VSS_Y),
    (0, -470, 0, VDD_Y),
    (-440, -470, -440, VDD_Y),
    (-860, -470, -860, VDD_Y),
    (-660, -470, -660, VDD_Y),
    (-180, 110, -180, VSS_Y),
    (180, 110, 180, VSS_Y),
    (-380, -120, -380, VSS_Y),
    (380, -120, 380, VSS_Y),
    (-540, 60, -540, VSS_Y),
    (540, 60, 540, VSS_Y),
    (-680, -120, -680, VSS_Y),
    (680, -120, 680, VSS_Y),
    (-820, 60, -820, VSS_Y),
    (820, 60, 820, VSS_Y),
    (-440, -250, -440, VSS_Y),
    (-860, -230, -860, VSS_Y),
    (RAIL_LEFT, -320, RAIL_LEFT, VSS_Y),
    # the tail node: one trunk, both input pairs standing on it
    (0, -410, 0, -360),
    (-180, -360, 180, -360),
    (-180, -310, -180, -360),
    (180, -310, 180, -360),
    # the integration nodes, each from its input device down to its latch
    # device, with the precharge and the added capacitance hung off it
    (-180, -250, -180, -130),
    (-180, -180, -380, -180),
    (-380, -180, -680, -180),
    (180, -250, 180, -130),
    (180, -180, 380, -180),
    (380, -180, 680, -180),
    # the outputs, same shape one stage down
    (-180, -70, -180, 50),
    (-180, 0, -540, 0),
    (-540, 0, -820, 0),
    (180, -70, 180, 50),
    (180, 0, 540, 0),
    (540, 0, 820, 0),
    # the cross-coupling, drawn: each output reaching the opposite side's two
    # gates, the two wires crossing once between them
    (-180, 20, -60, 20),
    (-60, 20, -60, 150),
    (-60, 150, 220, 150),
    (220, 150, 220, 80),
    (220, 80, 220, -100),
    (180, -20, 60, -20),
    (60, -20, 60, 170),
    (60, 170, -220, 170),
    (-220, 170, -220, 80),
    (-220, 80, -220, -100),
    # the inverter: its two gates tied, its output down to the precharge
    # devices' label
    (-480, -440, -480, -280),
    (-440, -410, -440, -310),
    # the mirror: the diode's own gate, the reference device under it, the
    # bias node the pass pair reaches, and the tail's gate at the end of it
    (-860, -410, -860, -290),
    (-900, -440, -900, -380),
    (-900, -380, -860, -380),
    (RAIL_LEFT, -380, -900, -380),
    (-790, -340, -860, -340),
    (-660, -410, -660, -340),
    (-730, -340, -660, -340),
    (-660, -390, -40, -390),
    (-40, -390, -40, -440),
    # the ports that are brought out on a stub
    (-900, -260, -1000, -260),
    (-480, -360, -560, -360),
    (-220, -280, -320, -280),
    (220, -280, 320, -280),
    (-180, 30, -280, 30),
    (180, 30, 280, 30),
)


def _placed(symbol: str, x: float, y: float, attributes: str, rot: int = 0, flip: int = 0) -> str:
    return f"C {{{symbol}}} {x:g} {y:g} {rot} {flip} {{{attributes}}}"


def _endpoints() -> set[tuple[float, float]]:
    """Every point a wire starts or stops at."""
    return {(x, y) for x1, y1, x2, y2 in WIRES for x, y in ((x1, y1), (x2, y2))}


def check(found: dict[str, Element]) -> None:
    """Refuse a drawing that does not cover the circuit.

    Three ways a sheet can be quietly wrong, each of which has to fail here
    rather than reach the editor: a device the circuit has and the drawing
    does not, a drawing that places something the circuit no longer has, and
    a terminal that is neither wired nor labelled -- which netlists as its own
    private net and reads, on the page, as a device that is simply not
    connected to anything.
    """
    missing = sorted(set(found) - set(PLACEMENT))
    if missing:
        raise ValueError(f"the circuit has devices this drawing does not place: {missing}")
    stale = sorted(set(PLACEMENT) - set(found))
    if stale:
        raise ValueError(f"this drawing places devices the circuit does not have: {stale}")

    carried = set(strongarm.TERMINALS) | set(LABELLED) | set(NAMED)
    anonymous = sorted(
        {net for element in found.values() for net in element.nets.values()} - carried
    )
    if anonymous:
        raise ValueError(f"nets nothing on the sheet names, so the editor will: {anonymous}")

    reachable = _endpoints()
    placements = sorted(set(NAMED.values()) - reachable)
    if placements:
        raise ValueError(f"net names placed where no wire ends: {placements}")

    loose = []
    for name in sorted(found):
        element = found[name]
        x, y, rot, flip = PLACEMENT[name]
        for terminal, net in placed(element.symbol, x, y, rot, flip).items():
            if terminal == BULK or element.nets[terminal] in LABELLED:
                continue
            if net not in reachable:
                loose.append(f"{name}.{terminal} ({element.nets[terminal]}) at {net}")
    if loose:
        raise ValueError("terminals that no wire reaches:\n  " + "\n  ".join(loose))


def sheet(sizes: strongarm.Sizes | None = None, netlister=None) -> str:
    """The sheet, text, for one sizing built by one netlister."""
    sizes = strongarm.DESIGNED if sizes is None else sizes
    netlister = devices.Sky130() if netlister is None else netlister

    found = elements(strongarm.subckt(sizes, netlister))
    check(found)

    records = [FORMAT, *SECTIONS]

    for index, terminal in enumerate(strongarm.TERMINALS):
        x, y = PORTS[terminal]
        direction = strongarm.DIRECTIONS[terminal]
        records.append(_placed(PORT[direction], x, y, f"name=p{index} lab={terminal}"))

    for x1, y1, x2, y2 in WIRES:
        records.append(f"N {x1:g} {y1:g} {x2:g} {y2:g} {{}}")

    marks = 0
    for net, (x, y) in NAMED.items():
        records.append(_placed(LABEL, x, y, f"name=n{net} lab={net}"))

    for name in sorted(found):
        element = found[name]
        x, y, rot, flip = PLACEMENT[name]
        records.append(_placed(element.symbol, x, y, element.attributes, rot, flip))
        for terminal, (px, py) in placed(element.symbol, x, y, rot, flip).items():
            net = element.nets[terminal]
            if terminal != BULK and net not in LABELLED:
                continue
            records.append(_placed(LABEL, px, py, f"name=l{marks} lab={net}"))
            marks += 1

    return "\n".join(records) + "\n"


#: Which edge of the box each terminal leaves by. A drawing choice and only
#: that: the editor takes a symbol's port order from the order of its pin
#: records, so declaring them in the subcircuit's order (which `symbol` does)
#: leaves every side free to move without rewiring anything that instantiates
#: it. That independence is the point of the table. Writing the sides as a
#: side-effect of direction, which this did first, published a port order of
#: inputs-then-the-rest that no netlist here declares.
SIDES = {
    "vref": "left", "clk": "left", "inp": "left", "inn": "left",
    "vdd": "right", "vss": "right", "outp": "right", "outn": "right",
}

#: The symbol's box, and where its pins sit around it. The pin itself is a
#: small box the editor snaps a wire to; the line is the stub drawn out to it
#: and the text is what a reader sees. The sides take a wider pitch than the
#: ends because a name set beside a vertical stub needs the room sideways.
BOX_X = 130
PIN_X = 150
PIN_PITCH = 20
END_PITCH = 60
PIN_BOX = 2.5
BOX_MARGIN = 20
STUB = PIN_X - BOX_X

#: Wire colours the editor draws with: a supply is a different colour from a
#: signal, which is the one thing about a symbol that stops a supply being
#: read as just another pin.
SIGNAL_COLOUR = 4
SUPPLY_COLOUR = 7

#: Text sizes, as the committed block symbol uses them.
NAME_SIZE = 0.3
PIN_SIZE = 0.2


def _spread(count: int, pitch: int) -> list[int]:
    """`count` evenly pitched coordinates, centred on the origin."""
    return [-(count - 1) * pitch // 2 + index * pitch for index in range(count)]


def _layout() -> tuple[dict[str, tuple[int, int, str]], int, int]:
    """Where every pin box sits, and the box's own top and bottom edges.

    Each edge is laid out centred on the origin independently of the others,
    so moving one terminal to another side re-centres that side rather than
    pushing the rest of the symbol off its axis.
    """
    edges = {
        edge: [t for t in strongarm.TERMINALS if SIDES[t] == edge]
        for edge in ("left", "right", "top", "bottom")
    }
    unknown = sorted(set(SIDES) - set(strongarm.TERMINALS))
    unplaced = sorted(set(strongarm.TERMINALS) - set(SIDES))
    if unknown or unplaced:
        raise ValueError(f"sides name {unknown} and leave {unplaced} off the symbol")

    rows = max(len(edges["left"]), len(edges["right"]), 1)
    extent = _spread(rows, PIN_PITCH)
    low, high = extent[0] - BOX_MARGIN, extent[-1] + BOX_MARGIN

    places: dict[str, tuple[int, int, str]] = {}
    for edge, sign in (("left", -1), ("right", 1)):
        for terminal, y in zip(edges[edge], _spread(len(edges[edge]), PIN_PITCH), strict=True):
            places[terminal] = (sign * PIN_X, y, edge)
    for edge, y in (("top", low - STUB), ("bottom", high + STUB)):
        for terminal, x in zip(edges[edge], _spread(len(edges[edge]), END_PITCH), strict=True):
            places[terminal] = (x, y, edge)
    return places, low, high


def _pin(name: str, direction: str, x: int, y: int, edge: str, low: int, high: int) -> list[str]:
    """One terminal: its snap box, its stub back to the box, and its name."""
    colour = SUPPLY_COLOUR if direction == "inout" else SIGNAL_COLOUR
    tip, text, justify = {
        "left": ((-BOX_X, y), (-(BOX_X - 5), y - 4), 0),
        "right": ((BOX_X, y), (BOX_X - 5, y - 4), 1),
        "top": ((x, low), (x + 4, low + 2), 0),
        "bottom": ((x, high), (x + 4, high - 14), 0),
    }[edge]
    return [
        f"B 5 {x - PIN_BOX} {y - PIN_BOX} {x + PIN_BOX} {y + PIN_BOX} "
        f"{{name={name} dir={direction}}}",
        f"L {colour} {x} {y} {tip[0]} {tip[1]} {{}}",
        f"T {{{name}}} {text[0]} {text[1]} 0 {justify} {PIN_SIZE} {PIN_SIZE} {{}}",
    ]


def symbol(name: str = strongarm.NAME) -> str:
    """The symbol, text, declaring exactly the subcircuit's terminals.

    Declared in the subcircuit's own order, because that order is the symbol's
    port list -- an instance of it netlists its pins in the order the records
    appear here, so a symbol ordered any other way wires a parent sheet to the
    wrong terminals of the netlist every bench here measures. Where each pin
    sits is `SIDES` and changes nothing about that.
    """
    places, low, high = _layout()

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
        f"T {{@name}} {BOX_X + 5} {low - 12} 0 0 {PIN_SIZE} {PIN_SIZE} {{}}",
        f"P 4 5 {BOX_X} {low} {-BOX_X} {low} {-BOX_X} {high} {BOX_X} {high} {BOX_X} {low} {{}}",
    ]

    for terminal in strongarm.TERMINALS:
        x, y, edge = places[terminal]
        records += _pin(terminal, strongarm.DIRECTIONS[terminal], x, y, edge, low, high)

    return "\n".join(records) + "\n"


def main() -> None:
    """Write both files. The sheet is committed, so the diff is the review."""
    SHEET.write_text(sheet())
    SYMBOL.write_text(symbol())
    print(f"wrote {SHEET.relative_to(REPO)} and {SYMBOL.relative_to(REPO)}")


if __name__ == "__main__":
    main()
