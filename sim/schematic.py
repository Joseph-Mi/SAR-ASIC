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

How a sheet is written, read and netlisted at all is `sheet.py`, including the
handful of the editor's behaviours that had to be measured rather than assumed
-- the two FET symbols being drawn opposite ways round among them, which is
why pin positions are read out of each symbol here and not tabulated.

What distribution gets instead of wires is a label, which is what a drawn
sheet does too: the supplies, every bulk tie, and the strobe on its six gates.
Drawing those would bury the circuit in wires that carry no information.
"""

from __future__ import annotations

import sys

import devices
import strongarm
from sheet import (
    BULK,
    FORMAT,
    LABEL,
    PORT,
    REPO,
    SECTIONS,
    SHEET_DIR,
    Element,
    elements,
    instance,
    placed,
    regenerate,
)
from sheet import symbol as sheet_symbol

SHEET = SHEET_DIR / f"{strongarm.NAME}.sch"
SYMBOL = SHEET_DIR / f"{strongarm.NAME}.sym"

#: Nets carried by label everywhere they appear, because each one reaches more
#: gates than a drawing can show without hiding the circuit under wires. The
#: strobe and its inverse are the latch's clock; they fan out to six gates.
LABELLED = ("clk", "clk_i")

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
        records.append(instance(PORT[direction], x, y, f"name=p{index} lab={terminal}"))

    for x1, y1, x2, y2 in WIRES:
        records.append(f"N {x1:g} {y1:g} {x2:g} {y2:g} {{}}")

    marks = 0
    for net, (x, y) in NAMED.items():
        records.append(instance(LABEL, x, y, f"name=n{net} lab={net}"))

    for name in sorted(found):
        element = found[name]
        x, y, rot, flip = PLACEMENT[name]
        records.append(instance(element.symbol, x, y, element.attributes, rot, flip))
        for terminal, (px, py) in placed(element.symbol, x, y, rot, flip).items():
            net = element.nets[terminal]
            if terminal != BULK and net not in LABELLED:
                continue
            records.append(instance(LABEL, px, py, f"name=l{marks} lab={net}"))
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
    "vref": "left",
    "clk": "left",
    "inp": "left",
    "inn": "left",
    "vdd": "right",
    "vss": "right",
    "outp": "right",
    "outn": "right",
}

#: Which of them are rails, which is what the editor draws in its own colour.
SUPPLIES = ("vdd", "vss")


def symbol() -> str:
    """The latch's symbol, declaring exactly its subcircuit's terminals."""
    return sheet_symbol(
        strongarm.NAME,
        strongarm.TERMINALS,
        strongarm.DIRECTIONS,
        SIDES,
        supplies=SUPPLIES,
    )


#: Who owns the sheet's arrangement, which is the one thing about this file
#: that changes as the comparator is drawn rather than as it is designed.
#:
#: `generated` is the bootstrap: the generator writes the sheet, and a test
#: holds the committed file byte-for-byte to its output, so the two cannot
#: come apart. `drawn` is afterwards: the arrangement has been taken over in
#: the editor, where a person can do things this generator has no vocabulary
#: for -- a label stood off its pin on a stub of its own, text turned to read
#: outward -- and regenerating would throw them away. So in `drawn` the
#: generator will not write the sheet without being told twice.
#:
#: What does not change with the stage is the guarantee. The circuit is held
#: by netlisting the sheet back and comparing it element by element against
#: `strongarm.subckt`, which is a stronger check on a hand-drawn sheet than
#: on a generated one: against a generated sheet it compares the generator
#: with itself, and against a drawn one it is the thing that catches a wire
#: dragged off a pin. The symbol stays generated in both stages, because it
#: carries the interface and no arrangement.
ARRANGEMENT = "drawn"

#: Where a regeneration puts the sheet it would have written, once the sheet
#: itself is hand-drawn: beside the build output, to be read and not kept.
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
        held_by="sim/tests/test_schematic.py",
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
