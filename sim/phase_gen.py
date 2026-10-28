"""The phase generator as a schematic sheet, generated from its own netlist.

What the sheet is of: the three switch phases, made from the one `sample`
wire, each able to change only once the phase it must follow has finished
changing (DD-11). The ordering is the circuit's whole purpose, and it holds by
construction rather than by timing: every "has fallen" is read by an
off-detector on the line the switches' gates actually hang on, so a phase
waits for that wire, its load and its corner to reach the level where its
switch is really off.

It is drawn as a logic sheet: every gate is a stack, PMOS above and NMOS
below, and the lines between gates are carried by name rather than by wire.
That is a choice about what a reader needs to see here. The structure that
matters is *which line each gate watches* -- the cross-coupling between the
input phase and the conversion phase, and each detector reading the phase
before it -- and labelled gates say that on sight, where fifty-four devices
wired across four rows would bury it. Within a gate the wires are real,
because a stack is a picture of a gate and a netlist is not.

The cells are not listed here. They are read out of the netlist by name --
`sim/analog.py` builds every gate through `_inverter`, `_nor`, `_buffer` and
the two off-detectors, and each names its devices after itself -- so this
module says where each cell goes and never what is in one. A gate that gains
a transistor appears on the sheet; a cell this file places and the netlist
does not build is refused.
"""

from __future__ import annotations

import itertools
import re

import analog
import devices
from sheet import (
    BULK,
    FORMAT,
    LABEL,
    PORT,
    REPO,
    SECTIONS,
    SHEET_DIR,
    elements,
    instance,
    placed,
    regenerate,
)
from sheet import symbol as sheet_symbol

SHEET = SHEET_DIR / f"{analog.GENERATOR_NAME}.sch"
SYMBOL = SHEET_DIR / f"{analog.GENERATOR_NAME}.sym"

#: A device's name split into the cell it belongs to and its place in it.
#: `nor_cnvp2` is the third PMOS of `nor_cnv`; `stopsp` is the skewed PMOS of
#: `stop`; `btop0n` is the NMOS of `btop0`. Read rather than tabulated: the
#: netlist builds these names, so a gate that gains a device gains it here.
CELL = re.compile(r"^(?P<cell>.+?)(?P<flavour>s?[pn])(?P<index>\d*)$")

#: The supplies, which every cell reaches and none of them draws.
RAILS = ("vdd", "vss")

# ---------------------------------------------------------------- the drawing
#
# Four rows, one per line the generator makes, each read left to right in the
# order the signal travels: the gates that make the phase, then the detector
# that watches it. The rows are in the order the phases happen, which is also
# the order each waits on the last.

ROWS = (
    ("the top switch's line: it follows sample", ("btop0", "btop1", "stop", "stopr")),
    (
        "the input switches' NMOS line: it cannot fall until the top line is"
        " off, nor rise until the conversion line is",
        ("nor_held", "nor_bot", "bbot0", "bbot1", "bbot2", "bbot3", "sbot", "sbotr"),
    ),
    (
        "their PMOS line: the same edge, complemented, with a detector of its own",
        ("bbotn0", "bbotn1", "bbotn2", "sbotn", "sbotnr0", "sbotnr1"),
    ),
    (
        "the conversion switches' line: it cannot rise until both input lines are off",
        ("nor_cnv", "bcnv0", "bcnv1", "scnv", "scnvr"),
    ),
)

#: How far apart the rows sit, and where the first one's output node is.
ROW_PITCH = 560
ROW_Y = 0

#: Within a cell: the output node's height is the row's, the NMOS sit one step
#: below it and each PMOS one step above the next, so a stack hangs from the
#: output upward and a taller gate reaches further toward its supply instead
#: of pushing the row apart.
STEP = 100

#: Side to side: between the parallel NMOS of one gate, and between gates.
LEG_PITCH = 100
CELL_GAP = 100


def cells(scheme: analog.NonOverlap) -> dict[str, dict[tuple[str, int], str]]:
    """Every gate the netlist builds, and which device plays each part in it.

    Keyed by cell, then by flavour and position: `("p", 1)` is the second
    PMOS of a series stack, `("n", 0)` the first NMOS. The skewed devices of
    an off-detector are `("sp", 0)` and `("sn", 0)` -- a different part,
    because they are a different size and are what reads the line.
    """
    found: dict[str, dict[tuple[str, int], str]] = {}
    for name in elements("\n".join(analog.generator_devices(scheme))):
        split = CELL.match(name)
        if split is None:
            raise ValueError(f"{name} is not a device of any gate this can draw")
        part = (split["flavour"], int(split["index"] or 0))
        place = found.setdefault(split["cell"], {})
        if part in place:
            raise ValueError(f"{split['cell']} has two devices at {part}")
        place[part] = name
    return found


def _stack(place: dict[tuple[str, int], str], flavour: str) -> list[str]:
    """One gate's devices of one flavour, in the order the netlist stacks
    them: the first is the one nearest the supply."""
    wanted = [(f, k) for f, k in place if f.endswith(flavour)]
    return [place[part] for part in sorted(wanted, key=lambda part: part[1])]


def _width(place: dict[tuple[str, int], str]) -> int:
    """How wide a cell is on the page: its parallel legs, plus a gap."""
    return LEG_PITCH * (len(_stack(place, "n")) - 1) + CELL_GAP


def _columns(scheme: analog.NonOverlap) -> dict[str, tuple[int, int]]:
    """Where each cell's output node sits, by cell."""
    built = cells(scheme)
    drawn = [name for _, row in ROWS for name in row]
    missing = sorted(set(built) - set(drawn))
    stale = sorted(set(drawn) - set(built))
    if missing:
        raise ValueError(f"the generator has gates this drawing does not place: {missing}")
    if stale:
        raise ValueError(f"this drawing places gates the generator does not have: {stale}")

    places = {}
    for index, (_, row) in enumerate(ROWS):
        x = 0
        for name in row:
            places[name] = (x, ROW_Y + index * ROW_PITCH)
            x += _width(built[name])
    return places


def _signal(element) -> set[str]:
    """What a device carries on the two terminals that are not its gate or its
    bulk, leaving out the rails: for any gate here that is its output alone,
    and for a device inside a series stack it is the stack's node as well."""
    return {
        net
        for terminal, net in element.nets.items()
        if terminal not in (BULK, "G") and net not in RAILS
    }


def _cell(name: str, place: dict[tuple[str, int], str], x: int, y: int, found, tag) -> list[str]:
    """One gate: its devices, the wires inside it, and the names on its lines.

    Every terminal is dealt with by the net it carries rather than by which of
    drain and source it is, because the two FET symbols disagree about that --
    a PMOS keeps its drain where an NMOS keeps its source, so a table of
    offsets written from one flavour swaps the other's two and draws a circuit
    that is wrong. A rail is a label, the output node is a wire to the gate's
    own output line, and a node inside a series stack is named where it sits,
    since a net nothing names is a net the editor names itself.
    """
    pmos, nmos = _stack(place, "p"), _stack(place, "n")
    shared = set.intersection(*(_signal(found[leg]) for leg in nmos))
    outputs = sorted(shared)
    if len(outputs) != 1:
        raise ValueError(f"{name}'s legs share {outputs}, so its output is not one net")
    output = outputs[0]

    legs = [x + LEG_PITCH * k for k in range(len(nmos))]
    spine = x + SPINE
    records = [instance(LABEL, spine, y, f"name=l{next(tag)} lab={output}")]
    # The line along the output node, where there is more than one leg to
    # join. A gate with one leg would otherwise get a wire from a point to
    # itself, which the editor drops on the next save -- so the sheet it
    # writes back differs from the one this wrote, for no reason anyone
    # reading the diff could see.
    if len(legs) > 1:
        records.insert(0, f"N {spine} {y} {legs[-1] + SPINE} {y} {{}}")
    for depth, device in enumerate(pmos):
        at = (x, y - STEP * (len(pmos) - depth))
        records.append(instance(found[device].symbol, *at, found[device].attributes))
        records += _terminals(found[device], at, output, spine, y, tag)
    for leg, device in zip(legs, nmos, strict=True):
        at = (leg, y + STEP)
        records.append(instance(found[device].symbol, *at, found[device].attributes))
        records += _terminals(found[device], at, output, leg + SPINE, y, tag)
    return records


def _terminals(element, at, output: str, spine: int, row: int, tag) -> list[str]:
    """Each of one device's four terminals, wired or named."""
    drawn = []
    for terminal, (px, py) in placed(element.symbol, *at, 0, 0).items():
        net = element.nets[terminal]
        px, py = round(px), round(py)
        if terminal == "G":
            # The name on the pin itself and not on a stub reaching out to
            # it. A stub is what a person draws, and it is what this drew
            # first: between parallel legs a stub one pitch long put the
            # label of one gate on top of its neighbour's body tie, and the
            # two nets merged. The sheet drew correctly and netlisted a NOR
            # whose second input was the ground rail -- a gate that can never
            # go high, so the phase it guards would have been free to move
            # whatever the line it was supposed to wait for was doing. Caught
            # by netlisting it back, which is the whole reason that check
            # exists and the reason it is not a formality here.
            drawn.append(instance(LABEL, px, py, f"name=l{next(tag)} lab={net}"))
        elif net == output and terminal != BULK:
            drawn.append(f"N {px} {py} {spine} {row} {{}}")
        else:
            drawn.append(instance(LABEL, px, py, f"name=l{next(tag)} lab={net}"))
    return drawn


def sheet(scheme: analog.NonOverlap | None = None) -> str:
    """The sheet, text."""
    scheme = DRAWN_WITH if scheme is None else scheme
    built = cells(scheme)
    places = _columns(scheme)
    found = elements("\n".join(analog.generator_devices(scheme)))
    tag = itertools.count()

    records = [FORMAT, *SECTIONS]
    records.append(
        f"T {{{analog.GENERATOR_NAME} -- three switch phases from one wire, each able "
        f"to change\nonly once the phase it must follow has finished changing (DD-11).}} "
        f"{TITLE_X} {ROW_Y - TITLE_UP} 0 0 0.4 0.4 {{}}"
    )
    records.append(
        f"T {{A logic sheet: every gate is a stack, and the lines between gates are "
        f"carried by\nname. What matters here is which line each gate watches, which "
        f"the names say.\nThe arrangement is sim/phase_gen.py; the circuit is "
        f"sim/analog.py, netlisted back\nand compared element by element by "
        f"sim/tests/test_phase_gen.py.}} "
        f"{TITLE_X} {ROW_Y - TITLE_UP + 60} 0 0 0.25 0.25 {{}}"
    )

    for index, (caption, row) in enumerate(ROWS):
        y = ROW_Y + index * ROW_PITCH
        records.append(f"T {{{caption}}} {TITLE_X} {y - STEP * 3} 0 0 0.25 0.25 {{}}")
        for name in row:
            x, _ = places[name]
            records += _cell(name, built[name], x, y, found, tag)

    for index, port in enumerate(analog.generator_terminals()):
        x, y = PORTS[port]
        direction = DIRECTIONS[port]
        records.append(instance(PORT[direction], x, y, f"name=p{index} lab={port}"))
    return "\n".join(records) + "\n"


#: Which devices the sheet is drawn with. The process's, not the generic
#: models the benches default to: a sheet is a drawing of what gets laid out.
DRAWN_WITH = analog.NonOverlap(devices=devices.Sky130())

#: The output node's wire runs from the drain pin's own x, which the symbol
#: puts a little to the right of the instance's origin.
SPINE = 20

#: Where the page's title sits, and the row captions.
TITLE_X = -260
TITLE_UP = 240

#: Where each terminal of the block is brought out. The supplies and the one
#: input on the left, the four phases down the right-hand side in the order
#: they happen, each beside the row that makes it.
PORTS = {
    "vdd": (TITLE_X, ROW_Y - STEP * 2),
    "vss": (TITLE_X, ROW_Y - STEP),
    "sample": (TITLE_X, ROW_Y),
    "phi_top": (TITLE_X, ROW_Y + STEP),
    "phi_bot": (TITLE_X, ROW_Y + ROW_PITCH + STEP * 2),
    "phi_bot_n": (TITLE_X, ROW_Y + ROW_PITCH * 2 + STEP * 2),
    "phi_conv": (TITLE_X, ROW_Y + ROW_PITCH * 3 + STEP * 2),
}

#: Which way each terminal faces. The phases leave, `sample` arrives, and the
#: supplies do neither.
DIRECTIONS = {
    "vdd": "inout",
    "vss": "inout",
    "sample": "in",
    "phi_top": "out",
    "phi_bot": "out",
    "phi_bot_n": "out",
    "phi_conv": "out",
}

#: Which edge of the symbol's box each terminal leaves by, and which are
#: rails. A drawing choice and only that -- the port order is
#: `analog.generator_terminals()` and does not follow from this.
SIDES = {
    "vdd": "left",
    "vss": "left",
    "sample": "left",
    "phi_top": "right",
    "phi_bot": "right",
    "phi_bot_n": "right",
    "phi_conv": "right",
}
SUPPLIES = ("vdd", "vss")


def symbol() -> str:
    """The generator's symbol, declaring exactly the block's terminals."""
    return sheet_symbol(
        analog.GENERATOR_NAME,
        analog.generator_terminals(),
        DIRECTIONS,
        SIDES,
        supplies=SUPPLIES,
    )


#: Who owns the sheet's arrangement; see `cap_array.ARRANGEMENT`. Taken over
#: in the editor once the gates were spread out to be read, so a regeneration
#: leaves it alone and the netlist comparison is what holds it.
ARRANGEMENT = "drawn"

#: Where a regeneration puts the sheet it would have written, once the sheet
#: itself is hand-drawn.
PROPOSED = REPO / "build" / "schematic" / SHEET.name


def main(argv: list[str] | None = None) -> int:
    """Write the symbol, and the sheet if this stage still owns it."""
    return regenerate(
        list(argv if argv is not None else []),
        drawing=SHEET,
        description=SYMBOL,
        arrangement=ARRANGEMENT,
        draw=sheet,
        describe=symbol,
        proposed=PROPOSED,
        held_by="sim/tests/test_phase_gen.py",
    )


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
