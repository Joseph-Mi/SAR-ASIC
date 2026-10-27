"""What the sky130 process is: the device names, the sizes it draws, and the
matching it gives.

Contract: every fact about the process that more than one layer needs is
declared here, once, and nothing here depends on anything else in the
repository. The model's statistics, the simulation's netlists and the
sandbox's experiments all take their process numbers from this module.
"""

from __future__ import annotations

import math
import os
import pathlib

import numpy as np

MOSFET = r"sky130_fd_pr__[np]fet_01v8"
NFET = "sky130_fd_pr__nfet_01v8"
PFET = "sky130_fd_pr__pfet_01v8"
MIM = "sky130_fd_pr__cap_mim_m3_1"

#: Which variables say where the process is, and what to fall back on. Two of
#: them rather than one because the image sets `PDK` to a different process
#: and derives four more paths from it before anything of ours is sourced, so
#: a reader that spelled the name itself would read a different process's tree
#: and find most of what it was looking for. The fallback is a path that
#: cannot exist, so what a test guards on is the tree rather than the
#: variable: an empty variable and a machine without the process are the same
#: situation and should skip for the same reason.
PDK_ROOT, PDK_NAME = "PDK_ROOT", "PDK"
PDK_DEFAULT, PDK_NOWHERE = "sky130A", "/nonexistent"


def pdk() -> pathlib.Path:
    """The process's own tree, wherever this machine keeps it."""
    return pathlib.Path(os.environ.get(PDK_ROOT, PDK_NOWHERE)) / os.environ.get(
        PDK_NAME, PDK_DEFAULT
    )


def drc_magic() -> pathlib.Path:
    """The rule deck Magic checks a layout against."""
    return pdk() / "libs.tech/magic" / f"{pdk().name}.tech"


def drc_klayout() -> pathlib.Path:
    """The rule deck KLayout checks a layout against.

    The `_mr` one, which is what `sak-drc.sh` runs for both the front end and
    the back end. Named because the tree carries another KLayout deck beside
    it, `klayout/drc/{pdk}.lydrc`, that nothing in the flow runs -- see the
    capacitor rules below for why reading it instead is expensive.
    """
    return pdk() / "libs.tech/klayout/drc" / f"{pdk().name}_mr.drc"


#: The narrowest core device the PDK draws and has a model for, in
#: micrometres. Below it the simulator finds no model at all.
W_MIN = 0.42

#: The widest single finger to ask the models for. Their size bins cover a
#: bounded range of widths; anything wider is drawn, and modelled, as parallel
#: fingers of equal width.
W_FINGER_MAX = 5.0

#: Capacitor matching coefficient, percent-micrometres.
CAP_A_C = 0.47

#: Corners the capacitance models carry, lowest first.
CAP_CORNERS = ("low", "typical", "high")

#: What a MiM plate gives per unit of area, farads per square micrometre, and
#: how far the plate runs past the edge that was drawn, micrometres.
#:
#: The bias is positive and far from small -- more than a tenth of a
#: micrometre at every corner -- so at the smallest unit the process draws it
#: is worth a sixth of the value. A unit computed from its drawn area alone is
#: wrong by that much, and wrong by a different amount at each corner, because
#: the bias moves further between corners than the density does.
CAP_MIM_AREA = {"low": 1.78e-15, "typical": 2.00e-15, "high": 2.23e-15}
CAP_MIM_BIAS = {"low": 0.055, "typical": 0.150, "high": 0.245}

#: The unit capacitor's drawn area, square micrometres, per flavour. Matching
#: improves with area, so the smaller of these is the worst matching an array
#: is built to have.
#:
#: This is the project's floor and not the process's, which is lower: the only
#: size rule either running deck states for the MiM is a minimum width, no
#: deck states a minimum area, and the device's own model defaults to a
#: micrometre each way -- so a square a quarter of this is legal to draw and
#: matches half as well. Which is a decision waiting to be made rather than a
#: fact, and it is written here as one so that the test below holds it to the
#: rule it has to obey rather than to a rule it invented.
CAP_MIN_AREA_MIM = 4.00
CAP_MIN_AREA_VPP = 3.24

#: What the process lets a MiM plate be drawn as, micrometres. The array is
#: a thousand of these and the pitch decides whether it fits the tile, so
#: these are the numbers the floorplan rests on.
#:
#: Read from the two decks the project's own DRC script runs -- Magic's
#: `{pdk}.tech` and KLayout's `{pdk}_mr.drc` -- because a layout has to be
#: clean to both, and where they state the same constraint differently the
#: stricter one is what is declared. The tree carries a third deck,
#: `klayout/drc/{pdk}.lydrc`, that the script never runs, and reading it
#: instead is the expensive mistake here: its capacitor rules name `m2` and
#: `via2` throughout where the device's plate is on `m3` and its contact is
#: `via3`, so every one of them is checking the metal below the right one. It
#: looks like the authority -- it is the deck named after the process, and its
#: numbers are mostly the same numbers.
#:
#: `MIM_METAL_SPACING` is the one worth distrusting, because the tree states
#: it three times and three ways: 0.14 in the unused deck's code, 0.5 in that
#: deck's own message and in the running deck's `capm.11`, and 1.34 in Magic.
#: What settles it is that the running deck also states the constraint a
#: second way, as 1.2 from the bottom plate (`capm.2b_a`), and the bottom
#: plate runs 0.14 past the plate -- so two independent expressions give 1.34
#: and only one gives 0.5. The strictest is also the corroborated one.
#:
#: `MIM_SIDE_MAX` is the exception to all of that, and is declared anyway: it
#: is `capm.6`, a real rule of the process, and the only deck that codes it is
#: the one nothing runs. So a plate drawn too large passes our own DRC, which
#: is the kind of gap worth a guard in arithmetic rather than a discovery at
#: submission. The array is nowhere near it; a bias network or a decoupling
#: capacitor drawn as one shape could be.
MIM_WIDTH_MIN = 1.0
MIM_SPACING = 0.84
MIM_PLATE_ENCLOSURE = 0.14
MIM_PLATE_SPACING = 1.2
MIM_METAL_SPACING = 1.34
MIM_SIDE_MAX = 20.0

DIFF_EXT = 0.29

#: Resistance of the NMOS that holds the top plate at the common mode, ohms,
#: by corner. Measured, like the diffusion above, and for the same reason.
#:
#: It is quoted for one width and one level because both decide it: the level
#: a switch passes is the gate drive it does not get and the body effect it
#: does, so the same switch passing the supply's midpoint instead of this
#: design's common mode is several times worse. A resistance without its bias
#: beside it is not a number.
TOP_SWITCH_WIDTH = 8.0
TOP_SWITCH_PASSES = 0.5
TOP_SWITCH_OHMS = {"typical": 181.0, "worst": 344.0}

#: What a source or drain diffusion presents when its device is off, at zero
#: bias, in farads per micrometre of width and at the minimum channel length.
#: Together with the two below it is a depletion law.
#:
#: Measured, not read: the PDK's model cards state junction parameters the
#: compact model does not use directly, and a name that looks like the right
#: one carries a value that is not. What a node sees is what the simulator
#: builds, so that is what this is fitted to -- the device as the netlister
#: writes it, fingers and all, because a width written out whole is a
#: different device and answers a different question.
DIFFUSION_ZERO_BIAS = 9.1234e-16
DIFFUSION_POTENTIAL = 0.625
DIFFUSION_GRADING = 0.2906


def diffusion_capacitance(width: float, reverse_bias: float = 0.0) -> float:
    """What an off device's source or drain presents at this reverse bias.

    The quantity that matters where a diffusion sits on a node whose charge is
    the answer: it is not a fixed capacitance, and it is largest where the
    node comes closest to the body. Takes an array of biases as readily as
    one, so a curve of it and a single number come from one expression.
    """
    if width <= 0.0:
        raise ValueError(f"{width} um is not a width")
    bias = np.asarray(reverse_bias, dtype=float)
    if np.any(bias < 0.0):
        raise ValueError("a forward-biased diffusion conducts; it does not store")
    depletion = (1.0 + bias / DIFFUSION_POTENTIAL) ** -DIFFUSION_GRADING
    return DIFFUSION_ZERO_BIAS * width * depletion


def mim_capacitance(width: float, length: float, corner: str = "typical") -> float:
    """A MiM capacitor of this drawn size, in farads.

    The device's own expression, taken on the plate the process ends up with
    rather than the shape that was drawn.
    """
    if corner not in CAP_MIM_AREA:
        raise ValueError(f"{corner} is not one of {CAP_CORNERS}")
    bias = CAP_MIM_BIAS[corner]
    if width + bias <= 0.0 or length + bias <= 0.0:
        raise ValueError(f"{width} x {length} um leaves no plate once biased")
    return CAP_MIM_AREA[corner] * (width + bias) * (length + bias)


def mim_unit(corner: str = "typical") -> float:
    """The smallest unit capacitor the process will draw, in farads.

    Square, because a unit that differs from its neighbours in shape differs
    from them in value: the bias acts on both dimensions, so two shapes of
    equal drawn area do not end up with equal plates.
    """
    side = math.sqrt(CAP_MIN_AREA_MIM)
    return mim_capacitance(side, side, corner)


def mim_pitch(side: float, shared: bool = False) -> float:
    """Centre to centre between two neighbouring units, micrometres.

    `shared` says whether the two sit on one bottom plate, which is what
    decides the answer and is not a property of the capacitors at all. Two
    units of the same branch are one net underneath, so the metal under them
    is one polygon and only the plates above it have to be apart (`capm.2a`,
    0.84). Two units of different branches are two nets, so the metal under
    them is two polygons that have to be apart as metal (`capm.2b`, 1.2), and
    each runs past its own plate by the enclosure the plate needs -- 1.48
    between the plates, a step three quarters again as wide.

    So a branch boundary costs area and a step inside a branch does not, which
    makes the cost a property of the placement rather than of the array.
    Row-major placement pays it a handful of times. A common-centroid scheme
    interleaves the branches on purpose and pays it at nearly every step: the
    placement that cancels a gradient is the one that spreads the array out,
    and the two are traded against each other rather than chosen separately.
    """
    if not MIM_WIDTH_MIN <= side <= MIM_SIDE_MAX:
        raise ValueError(
            f"{side} um is not a side the process draws a MiM at "
            f"({MIM_WIDTH_MIN} to {MIM_SIDE_MAX} um)"
        )
    if shared:
        return side + MIM_SPACING
    return side + max(MIM_SPACING, 2 * MIM_PLATE_ENCLOSURE + MIM_PLATE_SPACING)


def mim_row(units: int, side: float, shared: bool = False) -> float:
    """How far a row of that many units reaches, micrometres, plate to plate."""
    if units < 1:
        raise ValueError(f"{units} is not a row of units")
    return (units - 1) * mim_pitch(side, shared) + side


def mim_array_side(unit_count: int, ring: int = 1) -> int:
    """How many units lie along one side of the square block that holds them.

    Square because the unit is: the plate bias acts on both dimensions, so
    units of equal drawn area and unequal shape are of unequal value, and an
    array whose outline is square is the one whose gradient is shortest in
    both directions. Rounded up, because a part-filled row is still a row.

    The ring is dummies. A plate at the edge of an array is etched against
    open space and a plate inside one is etched against a neighbour, so the
    units that carry charge are the interior ones and the perimeter is there
    to be the neighbour. It is counted here because it is drawn, paid for in
    area, and easy to leave out of a budget precisely because it holds no
    charge.
    """
    if unit_count < 1:
        raise ValueError(f"{unit_count} units is not an array")
    if ring < 0:
        raise ValueError(f"a ring cannot be {ring} units wide")
    # Exact: ceil(sqrt(n)) in integers, where the float route rounds a perfect
    # square the wrong way and adds a row nothing goes in.
    return math.isqrt(unit_count - 1) + 1 + 2 * ring


def mim_rows_within(height: float, side: float, shared: bool = False) -> int:
    """How many rows of units a strip of this height holds, keep-away counted.

    Which is the question the tile actually asks, and it asks it because the
    array does not have to be square. Square is what makes a gradient
    shortest in both directions at once, and it is the shape to want where
    there is room for it; the strip the analog half gets is three times as
    wide as it is tall, so there is not. What fits is decided the short way,
    and the long way then has room to spare.

    Zero is a legitimate answer and is returned rather than refused: a strip
    too shallow for one row is a floorplan to change, and a caller that got a
    row it cannot draw would find out later and further away.
    """
    # The pitch first, so that a side the process will not draw is refused
    # whatever the height is: a strip too shallow for it would otherwise
    # answer zero, which reads as a floorplan problem rather than as the
    # geometry error it is.
    pitch = mim_pitch(side, shared)
    room = height - 2 * MIM_METAL_SPACING - side
    if room < 0.0:
        return 0
    return int(room // pitch) + 1


def mim_array_extent(unit_count: int, side: float, ring: int = 1, shared: bool = False) -> float:
    """The square block of units, how far it reaches, micrometres."""
    return mim_row(mim_array_side(unit_count, ring), side, shared)


def mim_keep_out(extent: float) -> float:
    """The same block plus the room unrelated metal has to leave around it.

    What a floorplan has to find, as against what the array measures. A power
    stripe over or beside the array is unrelated metal, and the rule holds it
    off every plate -- so the array's own extent is not the number that has to
    fit, and the difference is most of three micrometres.
    """
    if extent <= 0.0:
        raise ValueError(f"{extent} um is not a block")
    return extent + 2 * MIM_METAL_SPACING


def mosfet(w: float, length: float, mult: int = 1, nf: int = 1) -> dict[str, float]:
    """Core FET parameters, with junction geometry derived from the width.

    The PDK wrapper draws its mismatch terms against the geometry it is called
    with, so width and length belong on the subcircuit call.
    """
    return {
        "L": length,
        "W": w,
        "nf": nf,
        "ad": int((nf + 1) / 2) * w / nf * DIFF_EXT,
        "as": int((nf + 2) / 2) * w / nf * DIFF_EXT,
        "pd": 2 * int((nf + 1) / 2) * (w / nf + DIFF_EXT),
        "ps": 2 * int((nf + 2) / 2) * (w / nf + DIFF_EXT),
        "nrd": DIFF_EXT / w,
        "nrs": DIFF_EXT / w,
        "sa": 0,
        "sb": 0,
        "sd": 0,
        "mult": mult,
    }
