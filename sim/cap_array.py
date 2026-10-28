"""The capacitor array as a schematic sheet, generated from its own netlist.

What the sheet is of: the binary-weighted array that is both the
sample-and-hold and the DAC. One element per branch and not one per unit --
the largest branch is 512 units and the array is 1024, which is not a drawing
anyone reads. A branch of 2^k units is 2^k identical capacitors in parallel,
which is what a multiplier says, and a schematic's job here is the *ratio*:
which 1024 pieces build it, and where each one sits, is the layout's business
and is scripted (M6). `analog.array_capacitors` is what the benches simulate
and what this is built from, so the two cannot come apart.

Three things about drawing the PDK's capacitor that had to be measured:

* **The PDK's own symbol cannot state the matching multiplier.** Its format
  emits `MF=`, and `MF` is not a parameter its model reads -- the model takes
  `mult`, and divides its mismatch term by `sqrt(w*l*mult)`. Measured: a
  branch of sixteen units drawn as `MF=16 m=16` reports 0.19 % spread, which
  is one unit's (0.22 %), where sixteen drawn units give 0.055 %. The
  transistor symbols next to it in the same library get this right (`mult=@mult
  m=@mult`), so it is the capacitor's symbol that is wrong and not a
  convention this has misread.
* **An instance may carry a `format` of its own, and it overrides the
  symbol's.** Measured by netlisting one of each side by side. That is how
  this sheet states `mult` while still instantiating the PDK's symbol rather
  than a copy of it kept here to rot.
* **`c0` is the upper plate.** The straight plate on the symbol, against the
  curved one every capacitor symbol draws on its other terminal, and the
  plate magic extracts first (`device csubcircuit ... *mimcap *m3`): the
  `capm` plate above the met3 one. So the array's top plate belongs on `c0`,
  which is what DD-13 asks for -- the met3 plate underneath shields the
  floating node -- and is the way round LVS will see it.
"""

from __future__ import annotations

import analog
import sky130
from sheet import (
    FORMAT,
    PLATES,
    PORT,
    REPO,
    SECTIONS,
    SHEET_DIR,
    calls,
    instance,
    regenerate,
)
from sheet import symbol as sheet_symbol

SHEET = SHEET_DIR / f"{analog.ARRAY_NAME}.sch"
SYMBOL = SHEET_DIR / f"{analog.ARRAY_NAME}.sym"

#: The editor symbol for the PDK's MiM, named from the model's own two halves
#: so that it cannot name a device the netlist does not instantiate.
LIBRARY, _, DEVICE = sky130.MIM.partition("__")
CAPACITOR = f"{LIBRARY}/{DEVICE}.sym"

#: What that symbol's template calls the geometry the netlist states in lower
#: case, and `MF` for the multiplier its own model reads as `mult`. Mapping
#: the names rather than restating the numbers: the values come from the
#: netlist every bench is measured on.
SPELLING = {"w": "W", "l": "L", "mult": "MF"}

#: The format the instance carries instead of the symbol's own, which would
#: emit `MF=` and lose the multiplier the model reads. `@MF` is still where
#: the number is kept, because that is the attribute the symbol's template
#: declares and the one the editor shows on the page.
OVERRIDE = f"@spiceprefix@name @pinlist {LIBRARY}__@model w=@W l=@L mult=@MF m=@MF"

# ---------------------------------------------------------------- the drawing
#
# A row of branches, weight ascending left to right, each one's bottom plate
# dropping to its own port and every top plate on a single trunk. That trunk
# is the floating node the whole converter balances on, so it is drawn as one
# unbroken wire rather than carried by label: a reader should be able to see
# that there is exactly one of it.

#: Centre to centre between two branches on the page, and where the row sits.
PITCH = 160
ROW_Y = 0

#: The gap before the dummy, which is not part of the weighting: it carries no
#: charge and no bit drives it. Drawn apart so that the eleven elements do not
#: read as eleven weights.
DUMMY_GAP = 120

#: The trunk every top plate reaches up to, and the depth the bottom plates
#: drop to before their ports. The symbol's own plates sit 30 either side of
#: its origin.
PLATE_REACH = 30
TRUNK_Y = ROW_Y - 140
PORT_Y = ROW_Y + 140

#: Where the top plate leaves the sheet, left of the row so that the trunk is
#: read from its port rather than ending in air.
TOP_X = -PITCH


def _columns(n_bits: int = analog.N_BITS) -> dict[str, int]:
    """Where each branch's column sits, by the tag that names it."""
    tags = analog.branch_tags(n_bits)
    places = {}
    for index, tag in enumerate(tags):
        places[tag] = index * PITCH + (DUMMY_GAP if tag == "d" else 0)
    return places


def _branches(n_bits: int = analog.N_BITS) -> dict[str, tuple[str, dict[str, str], str]]:
    """Every branch as the editor needs it: its nets, and its attributes.

    Built from the netlist rather than from the weights, so that a branch this
    sheet draws is a branch the benches have.
    """
    netlisted = "\n".join(analog.array_capacitors(n_bits, analog.Mim()))
    drawn = {}
    for name, call in calls(netlisted).items():
        if tuple(call.nets) != PLATES:
            raise ValueError(f"{name} has {len(call.nets)} plates, so it is not a capacitor")
        geometry = " ".join(
            f"{spelled}={call.parameters[key]}" for key, spelled in SPELLING.items()
        )
        attributes = f'name={name} model={DEVICE} {geometry} spiceprefix=X format="{OVERRIDE}"'
        drawn[name] = (CAPACITOR, dict(call.nets), attributes)
    return drawn


def check(n_bits: int = analog.N_BITS) -> None:
    """Refuse a drawing that is not of the array the netlist states.

    The three ways this one can be quietly wrong: a branch the netlist has and
    the row does not place, a plate wired to a net that is not one of the
    block's terminals, and a weighting that is not binary -- which is the
    whole circuit, and which no element-by-element comparison would catch if
    this generator built the netlist too. It does not: it reads it.
    """
    branches = _branches(n_bits)
    columns = _columns(n_bits)
    expected = {f"u{tag}" for tag in columns}
    if set(branches) != expected:
        raise ValueError(f"the netlist's branches are {sorted(branches)}, not {sorted(expected)}")

    terminals = set(analog.array_terminals(n_bits))
    for name, (_, nets, _) in branches.items():
        stray = sorted(set(nets.values()) - terminals)
        if stray:
            raise ValueError(f"{name} reaches {stray}, which the array does not bring out")
        if nets[PLATES[0]] != analog.array_terminals(n_bits)[0]:
            raise ValueError(f"{name}'s upper plate is on {nets[PLATES[0]]}, not the top plate")

    weights = analog.branch_multipliers(n_bits)
    if weights != [2**k for k in range(n_bits)] + [1]:
        raise ValueError(f"{weights} is not a binary weighting with one dummy")


def sheet(n_bits: int = analog.N_BITS) -> str:
    """The sheet, text."""
    check(n_bits)
    branches = _branches(n_bits)
    columns = _columns(n_bits)

    records = [FORMAT, *SECTIONS]
    records.append(
        f"T {{{analog.ARRAY_NAME} -- the binary-weighted array, "
        f"{sum(analog.branch_multipliers(n_bits))} units of "
        f"{sky130.mim_side():g} x {sky130.mim_side():g} um in "
        f"{n_bits + 1} branches.}} {TOP_X} {TRUNK_Y - 200} 0 0 0.4 0.4 {{}}"
    )
    records.append(
        f"T {{One element per branch, its multiplier the units in it. The units "
        f"themselves\nare the layout's (M6): a branch is 2^k identical "
        f"capacitors in parallel and this\nsheet carries the ratio. Each "
        f"instance states a format of its own because the\nPDK's symbol emits "
        f"MF=, which its model does not read -- see sim/cap_array.py.}} "
        f"{TOP_X} {TRUNK_Y - 160} 0 0 0.25 0.25 {{}}"
    )

    top = analog.array_terminals(n_bits)[0]
    right = max(columns.values())
    records.append(f"N {TOP_X} {TRUNK_Y} {right} {TRUNK_Y} {{}}")
    records.append(instance(PORT["inout"], TOP_X, TRUNK_Y, f"name=p{top} lab={top}"))

    for index, (tag, x) in enumerate(columns.items()):
        name = f"u{tag}"
        symbol, nets, attributes = branches[name]
        records.append(instance(symbol, x, ROW_Y, attributes))
        records.append(f"N {x} {TRUNK_Y} {x} {ROW_Y - PLATE_REACH} {{}}")
        records.append(f"N {x} {ROW_Y + PLATE_REACH} {x} {PORT_Y} {{}}")
        bottom = nets[PLATES[1]]
        records.append(instance(PORT["inout"], x, PORT_Y, f"name=p{index} lab={bottom}"))
        units = analog.branch_multipliers(n_bits)[index]
        label = "dummy" if tag == "d" else f"bit {tag}"
        records.append(
            f"T {{{label}\n{units} unit{'s' if units != 1 else ''}}} "
            f"{x + 20} {PORT_Y - 60} 0 0 0.25 0.25 {{}}"
        )

    return "\n".join(records) + "\n"


def sides(n_bits: int = analog.N_BITS) -> dict[str, str]:
    """Which edge of the symbol's box each terminal leaves by.

    The bottoms come in from the switches on the left and the top plate
    leaves to the comparator on the right, which is the order the tile's own
    sheet puts those blocks in. A drawing choice and only that: the port
    order is `analog.array_terminals` and does not follow from this.
    """
    top, *bottoms = analog.array_terminals(n_bits)
    return {top: "right", **dict.fromkeys(bottoms, "left")}


def directions(n_bits: int = analog.N_BITS) -> dict[str, str]:
    """Every terminal is a plate, and a plate is driven from either side.

    None of them is a rail, which is a separate question the symbol asks: a
    plate drawn in the supply colour reads as one.
    """
    return dict.fromkeys(analog.array_terminals(n_bits), "inout")


def symbol(n_bits: int = analog.N_BITS) -> str:
    """The array's symbol, declaring exactly the block's terminals."""
    return sheet_symbol(
        analog.ARRAY_NAME,
        analog.array_terminals(n_bits),
        directions(n_bits),
        sides(n_bits),
    )


#: Who owns the sheet's arrangement. `generated` while the row the generator
#: draws is the arrangement; `drawn` once it has been taken over in the
#: editor, after which a regeneration leaves it alone. The guarantee does not
#: change with the stage: the sheet is netlisted back and compared element by
#: element against `analog.array_capacitors`.
ARRANGEMENT = "generated"

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
        held_by="sim/tests/test_cap_array.py",
    )


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
