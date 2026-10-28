"""The editor's own vocabulary: how a sheet is written, read and netlisted.

Nothing in here knows a circuit. It is what both generated sheets are built
out of -- the comparator's (`schematic.py`) and the capacitor array's
(`cap_array.py`) -- and it exists because the alternative was a second copy of
facts that were measured rather than looked up, each capable of producing a
wrong circuit that draws correctly:

* The two FET symbols are drawn opposite ways round. `pfet_01v8.sym` keeps its
  drain where `nfet_01v8.sym` keeps its source. Pin positions are therefore
  read out of each symbol rather than tabulated here.
* Mirroring moves the pins, so a mirrored device's terminals are where
  `transform` says and not where the symbol file says.
* Wires that merely cross are not connected, and a wire ending on another
  wire is. So the routing may cross freely and must never stop short.
* The editor suppresses `m=1` while emitting `m=3`, so an instance that does
  not state its multiplier netlists without one.
* An instance's name is written through verbatim, and a SPICE subcircuit call
  is spelled with a leading X -- which is why the editor's own default
  instance name is `x1`.
* A symbol's port order is the order of its pin records, and a SPICE instance
  wires by position. So `symbol` emits the records in the subcircuit's order
  and `SIDES`-style tables decide only where each pin is drawn.

What a sheet is checked against is never this module's idea of the circuit: it
is the netlist the benches simulate, and `netlist` here is the editor reading
its own drawing back.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
from dataclasses import dataclass

from devices import pdk_library

#: The repository root: the nearest folder up that holds the project's own
#: configuration, however deep this file is moved.
REPO = next(p for p in pathlib.Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
SHEET_DIR = REPO / "xschem"

#: The format line the editor writes. Carried rather than invented so a
#: generated sheet opens as the committed one does instead of being upgraded
#: on its first save.
FORMAT = "v {xschem version=3.4.8RC file_version=1.3}"

#: The empty sections every sheet carries between its format line and its
#: contents. The editor writes them whether or not they hold anything.
SECTIONS = ("G {}", "K {}", "V {}", "S {}", "F {}", "E {}")

#: One subcircuit call, which is what every PDK device netlists as: the
#: instance's name, then the fields its terminals and its model name occupy,
#: then the geometry.
#:
#: The terminals and the model are captured as one group and counted rather
#: than matched one by one, because nothing in the syntax says where the
#: terminals stop: a four-terminal transistor and a two-plate capacitor are
#: the same line with different counts. Two patterns racing each other read
#: one as the other -- a two-net pattern matches a transistor's line by taking
#: its source and bulk for the plates and its model name for a parameter, and
#: matches it in the direction that draws a plausible circuit. So the fields
#: are what cannot hold an `=`, and the parameters are what starts with one.
CALL = re.compile(
    r"^X(?P<name>\S+)\s+(?P<fields>[^\s=]+(?:\s+[^\s=]+)*)\s+(?P<params>\w+=.*)$",
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
#: this order; an ideal capacitor's two are its plates.
MOS_TERMINALS = ("D", "G", "S", "B")
CAP_TERMINALS = ("p", "m")

#: The same for a PDK capacitor, whose plates its symbol numbers rather than
#: names. `c0` is the upper plate on the symbol -- the straight one, against
#: the curved plate every capacitor symbol draws on its other terminal -- and
#: it is also the plate magic extracts first (`device csubcircuit
#: sky130_fd_pr__cap_mim_m3_1 *mimcap *m3`), which is the `capm` plate above
#: the met3 one. So an array wired with its top plate on `c0` is drawn the way
#: DD-13 asks for it and is the same way round as what LVS will extract.
PLATES = ("c0", "c1")

#: How many nets a call carries, and what they are called. A call whose count
#: is in neither is refused rather than guessed at.
NETS = {len(MOS_TERMINALS): MOS_TERMINALS, len(PLATES): PLATES}

#: The bulk terminal, which is labelled on every device rather than drawn.
BULK = "B"

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

#: A continued line in a SPICE netlist. The editor wraps at a width of its
#: own choosing, so a parse that reads lines has to undo that first.
CONTINUED = re.compile(r"\n\+\s*")

#: The editor's own symbols: a net name, and the three kinds of port.
LABEL = "lab_pin.sym"
PORT = {"in": "ipin.sym", "out": "opin.sym", "inout": "iopin.sym"}

#: An ideal capacitor, which is what the netlist says these are.
CAPACITOR = "capa.sym"


#: Where the editor writes a netlist: beside the sheet, which is what
#: `xschemrc` sets so that there is one copy of it and not two.
NETLIST_DIR = "simulation"


#: One placed symbol on a sheet, with where it sits.
PLACED = re.compile(
    r"^C \{(?P<symbol>[^}]+)\} (?P<x>\S+) (?P<y>\S+) \S+ \S+ \{(?P<attributes>[^}]*)\}", re.M
)


def stacked(drawing: str) -> dict[tuple[float, float], list[str]]:
    """Points where a sheet places more than one symbol, and what sits there.

    Two names on one point are the same net twice: harmless to the netlist,
    which is why nothing else here would notice, and not harmless to the
    editor's own check -- it is one of the things that makes `xschem -b -n -q`
    exit non-zero. That status is meant to become a gate once the block is
    whole, so noise in it is worth refusing now rather than explaining later.
    """
    at: dict[tuple[float, float], list[str]] = {}
    for found in PLACED.finditer(drawing):
        at.setdefault((float(found["x"]), float(found["y"])), []).append(found["symbol"])
    return {point: symbols for point, symbols in at.items() if len(symbols) > 1}


def instance(symbol: str, x: float, y: float, attributes: str, rot: int = 0, flip: int = 0) -> str:
    """One placed symbol, as the editor writes it."""
    return f"C {{{symbol}}} {x:g} {y:g} {rot} {flip} {{{attributes}}}"


def netlist(sheet: str, workdir: pathlib.Path) -> str:
    """One of this repository's sheets, as the editor itself netlists it.

    The way a drawing is checked: the editor is the only thing that knows what
    a sheet means -- which wires touch, which labels name a net, which way a
    mirrored symbol's pins went -- so the check reads its answer rather than
    reimplementing it.

    Netlisted from a copy in `workdir`, because the editor writes its output
    beside the sheet and a check must not rewrite what is committed nor
    collide with another run. The whole directory is copied, not just the
    sheet: a sheet descends into the sheets of the symbols it instantiates,
    and a missing one netlists as an empty subcircuit rather than an error.

    The exit status is read only for the message it carries when no file was
    written. A non-zero one does not mean the netlist is bad: the editor
    returns 10 when it found a net with nothing driving it, which is a real
    finding and one an unfinished sheet has by construction -- the array's
    bottom plates float until the switches are drawn, and the netlist beside
    it is correct and complete. Measured by giving such a net a driver, which
    takes the same sheet to zero. Whether a net floats is therefore asserted
    from the netlist, where the test can say *which* one, rather than from a
    status that says only that one does.
    """
    for source in SHEET_DIR.iterdir():
        if source.is_file():
            shutil.copy(source, workdir / source.name)
    done = subprocess.run(
        ["xschem", "-b", "-n", "-q", "--rcfile", "./xschemrc", sheet],
        cwd=workdir,
        capture_output=True,
        text=True,
    )
    produced = workdir / NETLIST_DIR / f"{pathlib.Path(sheet).stem}.spice"
    if not produced.exists():
        raise FileNotFoundError(
            f"the editor netlisted {sheet} nowhere this can find "
            f"(exit {done.returncode}): {done.stderr.strip() or done.stdout.strip()}"
        )
    return produced.read_text()


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


@dataclass(frozen=True)
class Call:
    """One PDK device as the netlist states it: its model, which net each of
    its terminals carries, and the geometry it was built with."""

    model: str
    nets: dict[str, str]
    parameters: dict[str, str]


def _parameters(text: str) -> dict[str, str]:
    """`k=v k=v` as written by the netlister."""
    return dict(pair.split("=", 1) for pair in text.split())


def calls(netlist: str) -> dict[str, Call]:
    """Every PDK device instance in a netlist, by name.

    The parse and nothing above it: how each device is then spelled as an
    instance on a sheet belongs to the sheet that draws it, because that is
    the device's symbol's business and the two PDK symbols this repository
    draws do not agree about it.
    """
    found: dict[str, Call] = {}
    for call in CALL.finditer(netlist):
        *nets, model = call["fields"].split()
        names = NETS.get(len(nets))
        if names is None:
            raise ValueError(f"{call['name']} carries {len(nets)} nets, which is not a device here")
        found[call["name"]] = Call(
            model=model,
            nets=dict(zip(names, nets, strict=True)),
            parameters=_parameters(call["params"]),
        )
    return found


#: Significant figures a netlist carries a geometry to. Numbers are compared
#: at that precision rather than exactly: `devices.Sky130` formats to six
#: figures and the editor evaluates the symbol's own expressions from the
#: width and length it was given, so the two agree on every value and need not
#: agree on how it is spelled. Finer than the netlist is written would be
#: comparing the formatting.
FIGURES = 6

#: What a device multiplier means when a netlist does not state one. The
#: editor writes a multiplier that is not one and suppresses one that is,
#: because one copy is what an instance means on its own; the netlister always
#: states it. So both sides are read against the same default, and a wide
#: device built out of several copies still has to say so on both.
COPIES, ONE = "m", "1"


def _number(text: str) -> float:
    """One value, at the precision the netlist carries it to."""
    return float(f"{float(text):.{FIGURES}g}")


def compared(netlist: str) -> dict[str, tuple]:
    """Every element of a subcircuit as values, keyed by name.

    What "the same circuit" means, in one place, because three sheets are
    held to their netlists and three definitions of sameness is how two of
    them end up checked to different standards. A device becomes its model,
    its terminals in the order they are written, and its geometry as numbers;
    an ideal capacitor its plates and its value. What is compared is then the
    circuit and not the two tools' formatting.
    """
    found: dict[str, tuple] = {}
    # The continuations first: the editor wraps a device line at a width of
    # its own, and a parse that reads lines reads a truncated geometry
    # without noticing -- which comes out as every device differing, not as
    # an error.
    netlist = CONTINUED.sub(" ", netlist)
    for name, call in calls(netlist).items():
        geometry = dict(call.parameters)
        geometry.setdefault(COPIES, ONE)
        found[name] = (
            call.model,
            tuple(call.nets.values()),
            {key: _number(value) for key, value in geometry.items()},
        )
    for line in CONTINUED.sub(" ", netlist).splitlines():
        if (cap := CAP.match(line)) is not None:
            found[f"C{cap['name']}"] = ((cap["plus"], cap["minus"]), _number(cap["value"]))
    return found


def elements(netlist: str) -> dict[str, Element]:
    """Everything in a subcircuit that has to appear on its sheet, by name.

    The transistors as the transistor symbol wants them, and the ideal
    capacitors the netlist adds as design knobs. A PDK capacitor is not here:
    the array's sheet builds its own instances from `calls`, because its
    symbol asks for its geometry in different words.
    """
    found: dict[str, Element] = {}
    for name, call in calls(netlist).items():
        if tuple(call.nets) != MOS_TERMINALS:
            raise ValueError(f"{name} is a {len(call.nets)}-terminal device, not a transistor")
        drawn = " ".join(f"{key}={call.parameters[key]}" for key in DRAWN)
        found[name] = Element(
            symbol=symbol_for(call.model),
            attributes=f"name={name} {drawn}",
            nets=dict(call.nets),
        )
    for line in netlist.splitlines():
        if (cap := CAP.match(line)) is not None:
            found[f"C{cap['name']}"] = Element(
                symbol=CAPACITOR,
                attributes=f"name=C{cap['name']} value={cap['value']}",
                nets=dict(zip(CAP_TERMINALS, (cap["plus"], cap["minus"]), strict=True)),
            )
    return found


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


def _layout(terminals, sides) -> tuple[dict[str, tuple[int, int, str]], int, int]:
    """Where every pin box sits, and the box's own top and bottom edges.

    Each edge is laid out centred on the origin independently of the others,
    so moving one terminal to another side re-centres that side rather than
    pushing the rest of the symbol off its axis.
    """
    edges = {
        edge: [t for t in terminals if sides[t] == edge]
        for edge in ("left", "right", "top", "bottom")
    }
    unknown = sorted(set(sides) - set(terminals))
    unplaced = sorted(set(terminals) - set(sides))
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


def _pin(
    name: str, direction: str, x: int, y: int, edge: str, low: int, high: int, supply: bool
) -> list[str]:
    """One terminal: its snap box, its stub back to the box, and its name."""
    colour = SUPPLY_COLOUR if supply else SIGNAL_COLOUR
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


def symbol(name: str, terminals, directions, sides, supplies=()) -> str:
    """The symbol, text, declaring exactly the subcircuit's terminals.

    Declared in the subcircuit's own order, because that order is the symbol's
    port list -- an instance of it netlists its pins in the order the records
    appear here, so a symbol ordered any other way wires a parent sheet to the
    wrong terminals of the netlist every bench here measures. Where each pin
    sits is `sides` and changes nothing about that.

    `supplies` is which terminals are drawn in the rail colour. Asked as its
    own question rather than taken from the direction, which is what it was
    first: a capacitor plate is an `inout` and is not a rail, so an array's
    symbol came out with every pin coloured as a supply.
    """
    places, low, high = _layout(terminals, sides)

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

    for terminal in terminals:
        x, y, edge = places[terminal]
        records += _pin(terminal, directions[terminal], x, y, edge, low, high, terminal in supplies)

    return "\n".join(records) + "\n"


def said(path: pathlib.Path) -> str:
    """A path as this repository spells it, or in full if it is outside."""
    return str(path.relative_to(REPO) if path.is_relative_to(REPO) else path)


def regenerate(
    argv: list[str],
    *,
    drawing: pathlib.Path,
    description: pathlib.Path,
    arrangement: str,
    draw,
    describe,
    proposed: pathlib.Path,
    held_by: str,
) -> int:
    """Write the symbol, and the sheet if this stage still owns it.

    The policy both generated sheets share, here rather than in each of them,
    because it is the one part of generating a sheet that is about the
    workflow instead of about the circuit: a sheet starts generated, is taken
    over in the editor once it is worth arranging by hand, and from then on a
    regeneration writes what it would have produced somewhere to be read
    rather than over the drawing. A missing sheet is written in either stage,
    so a fresh checkout is never short of one, and `--force` is the way to
    throw a drawing away deliberately.
    """
    forced = "--force" in argv

    description.write_text(describe())
    print(f"wrote {said(description)}")

    if arrangement == "generated" or forced or not drawing.exists():
        drawing.write_text(draw())
        print(f"wrote {said(drawing)}")
        return 0

    proposed.parent.mkdir(parents=True, exist_ok=True)
    proposed.write_text(draw())
    print(
        f"{said(drawing)} is drawn by hand and was left alone.\n"
        f"What the generator would write is {said(proposed)}.\n"
        f"The circuit on the sheet is checked by {held_by},\n"
        "which netlists it and names any device that differs -- fix those in\n"
        "the editor. To throw the drawing away and start again: make schematic"
        " FORCE=--force"
    )
    return 0
