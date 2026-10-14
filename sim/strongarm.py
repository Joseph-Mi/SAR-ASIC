"""The comparator as transistors: a StrongARM latch, sized and measured.

Contract: the subcircuit's terminals are the supplies, the strobe, the two
inputs and the two outputs, in that order. Evaluate is the strobe high and
precharge is the strobe low, whichever input flavour is built -- a
pair-polarity that wants the opposite sense inverts it inside, so the digital
half's interface does not change with an analog decision.

`outp` goes high when `inp` is the greater input. That costs a crossing in
here, because the input device that conducts harder discharges the node on
*its* side, and the output above a discharged node is the one that falls. The
crossing is in one place rather than in every reading of the result.

The integration nodes are precharged alongside the outputs. Left floating
they keep charge from the previous decision, and a latch with memory between
trials is hysteresis inside a binary search, where it walks the code rather
than adding noise to it.

Sizing is a `Sizes`, and nothing here carries a default geometry that a
measurement could silently inherit: every width and length is named by the
caller, so a figure and a test cannot disagree about what was simulated.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import ngspice

NAME = "strongarm"

#: Terminals, in the order the subcircuit declares them.
TERMINALS = ("vdd", "vss", "clk", "inp", "inn", "outp", "outn")

#: The integration nodes and the tail, named here because the measurements
#: probe them: they are where the noise and offset of this circuit are made,
#: and a bench that could not see them could not say which stage was at fault.
INTEGRATION = ("xp", "xn")
TAIL = "tail"

#: Input pair flavours. An NMOS pair needs its inputs well above ground and a
#: PMOS pair needs them well below the supply, which is the whole of the
#: question this design has about its own common mode.
FLAVOURS = ("n", "p")

#: The flavour this design builds, and the reason it is not a free choice.
#: The array holds its top plate at half the reference, which is under an
#: NMOS threshold once the tail's own headroom is taken off it: such a pair
#: integrates the right way but never regenerates to a logic level, leaving
#: every decision in the state the interface carries two wires to detect.
#: Widening it does not help, because what is missing is gate drive the
#: common mode never supplies. A PMOS pair has the whole excursion in its
#: range instead, at the cost of transconductance per micrometre, which is
#: paid back in the integration node the noise target asks for.
DESIGNED_FLAVOUR = "p"


@dataclass(frozen=True)
class Sizes:
    """One sizing of the latch. Micrometres, farads.

    `c_node` is capacitance added deliberately to the integration nodes. It is
    a design knob and not a parasitic: input-referred noise falls as the root
    of the charge swung on those nodes, so this is the cheapest way to buy
    quiet once the input pair is as efficient as it is going to get. It is paid
    for in energy per decision and in integration time.
    """

    w_in: float
    l_in: float
    w_tail: float
    l_tail: float
    w_latch_n: float
    w_latch_p: float
    l_latch: float
    w_pre: float
    l_pre: float
    c_node: float = 0.0
    c_load: float = 0.0
    flavour: str = "n"

    def __post_init__(self) -> None:
        if self.flavour not in FLAVOURS:
            raise ValueError(f"{self.flavour!r} is not an input pair flavour")
        widths = (self.w_in, self.w_tail, self.w_latch_n, self.w_latch_p, self.w_pre)
        lengths = (self.l_in, self.l_tail, self.l_latch, self.l_pre)
        if min(widths) <= 0.0:
            raise ValueError(f"{min(widths)} um is not a width")
        if min(lengths) <= 0.0:
            raise ValueError(f"{min(lengths)} um is not a length")
        if self.c_node < 0.0 or self.c_load < 0.0:
            raise ValueError("a capacitance added to a node is not negative")


def _rails(flavour: str) -> tuple[str, str]:
    """Which rail the tail sits on, and which the loads hang from."""
    return ("vss", "vdd") if flavour == "n" else ("vdd", "vss")


def subckt(sizes: Sizes, devices, name: str = NAME) -> str:
    """The latch as a subcircuit, text.

    `devices` is the netlister, so the same sizing can be built from the
    PDK's devices or from generic models and the difference is the only thing
    that changes between the two runs.
    """
    tail_rail, load_rail = _rails(sizes.flavour)
    sunk = devices.nmos if sizes.flavour == "n" else devices.pmos
    sourced = devices.pmos if sizes.flavour == "n" else devices.nmos
    xp, xn = INTEGRATION

    lines = [f".subckt {name} {' '.join(TERMINALS)}"]

    # The tail conducts while the strobe asks for a decision. An NMOS tail
    # does that on a high gate and a PMOS tail on a low one, so the second
    # flavour buys the frozen strobe sense with one inverter.
    strobe = "clk"
    if sizes.flavour == "p":
        strobe = "clk_i"
        lines += [
            devices.pmos("invp", strobe, "clk", "vdd", "vdd", sizes.w_pre, sizes.l_pre),
            devices.nmos("invn", strobe, "clk", "vss", "vss", sizes.w_pre, sizes.l_pre),
        ]

    lines += [
        sunk("tail", TAIL, strobe, tail_rail, tail_rail, sizes.w_tail, sizes.l_tail),
        sunk("inp", xn, "inp", TAIL, tail_rail, sizes.w_in, sizes.l_in),
        sunk("inn", xp, "inn", TAIL, tail_rail, sizes.w_in, sizes.l_in),
        sunk("lchp", "outp", "outn", xp, tail_rail, sizes.w_latch_n, sizes.l_latch),
        sunk("lchn", "outn", "outp", xn, tail_rail, sizes.w_latch_n, sizes.l_latch),
        sourced("ldp", "outp", "outn", load_rail, load_rail, sizes.w_latch_p, sizes.l_latch),
        sourced("ldn", "outn", "outp", load_rail, load_rail, sizes.w_latch_p, sizes.l_latch),
        sourced("prep", "outp", strobe, load_rail, load_rail, sizes.w_pre, sizes.l_pre),
        sourced("pren", "outn", strobe, load_rail, load_rail, sizes.w_pre, sizes.l_pre),
        sourced("prxp", xp, strobe, load_rail, load_rail, sizes.w_pre, sizes.l_pre),
        sourced("prxn", xn, strobe, load_rail, load_rail, sizes.w_pre, sizes.l_pre),
    ]

    if sizes.c_node > 0.0:
        lines += [
            f"Cxp {xp} vss {sizes.c_node:.6g}",
            f"Cxn {xn} vss {sizes.c_node:.6g}",
        ]
    if sizes.c_load > 0.0:
        lines += [
            f"Coutp outp vss {sizes.c_load:.6g}",
            f"Coutn outn vss {sizes.c_load:.6g}",
        ]

    return "\n".join([*lines, ".ends"])


#: Strobe edge, seconds. Short against the period and long enough that the
#: solver does not have to resolve a step.
EDGE = 50e-12

#: Where in a strobe's period the inputs are allowed to move, and where the
#: outputs are read, as fractions of it. The inputs move early, while the
#: latch is precharging, because a latch whose input moves during evaluation
#: decides on a blend of two questions. The read sits just inside the end of
#: the evaluate phase, where the separation is largest and still held.
MOVE_AT = 0.05
READ_AT = 0.95

#: The largest step the solver may take, seconds. Set by regeneration and not
#: by the strobe: the separation grows by `e` every time constant, and the
#: constant is tens of picoseconds however long the strobe is held. A step
#: scaled to the period instead steps straight over the window where the
#: decision is actually made, and the answer that comes back is the solver's
#: rather than the circuit's -- including, at a long strobe, the wrong sign.
STEP = EDGE

#: When the first strobe rises, and how long it stays up, in periods. One
#: period passes before it does: the sources start at their first level and
#: the latch precharges, so the first decision is asked of a circuit at rest
#: rather than of one still settling from time zero.
FIRST_STROBE = 1.5
EVALUATE = 0.5


@dataclass(frozen=True)
class Drive:
    """How the latch is strobed while it is measured. Volts, seconds, celsius."""

    supply: float
    period: float
    temp: float = 27.0

    def __post_init__(self) -> None:
        if self.supply <= 0.0:
            raise ValueError(f"{self.supply} V is not a supply")
        if self.period <= 0.0:
            raise ValueError(f"{self.period} s is not a strobe period")


def around(common: float, differences) -> list[tuple[float, float]]:
    """Input levels for each difference, centred on one common mode.

    The common mode is a question and not a setting. An input pair's
    transconductance, and whether it conducts at all, follow from the level
    its gates sit at, which for this converter is the common mode the array
    holds its top plate to -- not the supply's midpoint. So a run is free to
    move it between strobes, and `levels` below takes the pairs rather than a
    centre, which is what lets one simulation sweep bias and difference at
    once instead of one simulation per bias.
    """
    return [(common + d / 2, common - d / 2) for d in differences]


def _staircase(name: str, node: str, levels, drive: Drive) -> str:
    """A source that steps to each level once per strobe period.

    The steps are offset from the strobe's own edges: two breakpoints a
    fraction of a picosecond apart, computed by different routes, stall the
    solver rather than resolving.
    """
    points = [(0.0, levels[0])]
    for index, level in enumerate(levels):
        moment = (index + 1 + MOVE_AT) * drive.period
        points += [(moment, points[-1][1]), (moment + EDGE, level)]
    body = " ".join(f"{t:.12g} {v:.9g}" for t, v in points)
    return f"V{name} {node} 0 pwl({body})"


def read_moments(count: int, drive: Drive) -> list[float]:
    """When each strobe's decision is read, seconds."""
    return [(index + 1 + READ_AT) * drive.period for index in range(count)]


def deck(
    sizes: Sizes,
    devices,
    levels,
    drive: Drive,
    draws: int = 1,
    mismatch: bool = False,
) -> str:
    """One run that asks the latch every question in `levels`.

    `levels` is a pair of input voltages per strobe. Each pair gets its own
    strobe and the outputs are read inside each evaluate phase, so a whole
    transfer curve -- or a whole bias study -- costs one simulation instead of
    one per point. With `mismatch`, `draws` passes each redraw the process'
    own matching terms, which is what makes the spread of the result a yield
    statement rather than a single part's.
    """
    if draws < 1:
        raise ValueError(f"{draws} is not a number of draws")
    asked = [(float(high), float(low)) for high, low in levels]
    if not asked:
        raise ValueError("a run with no levels asks nothing")
    flat = [level for pair in asked for level in pair]
    if min(flat) < 0.0 or max(flat) > drive.supply:
        raise ValueError(
            f"inputs span {min(flat):g} V to {max(flat):g} V, outside a {drive.supply:g} V supply"
        )

    highs = [high for high, _ in asked]
    lows = [low for _, low in asked]
    span = (len(asked) + FIRST_STROBE + EVALUATE) * drive.period
    pulse = (
        f"pulse(0 {drive.supply:g} {FIRST_STROBE * drive.period:.12g} "
        f"{EDGE:.12g} {EDGE:.12g} {EVALUATE * drive.period:.12g} {drive.period:.12g})"
    )

    lines = [
        f"* {NAME}: one strobe per question",
        *devices.header(),
        *devices.models(),
        f".param mc_mm_switch={int(mismatch)}",
        ".param mc_pr_switch=0",
        subckt(sizes, devices),
        f".options reltol={ngspice.RELTOL}",
        f"Vdd vdd 0 {drive.supply:g}",
        f"Vclk clk 0 {pulse}",
        _staircase("inp", "inp", highs, drive),
        _staircase("inn", "inn", lows, drive),
        f"X{NAME} vdd 0 clk inp inn outp outn {NAME}",
        f".temp {drive.temp:g}",
        ".control",
        "set nomodcheck",
        "let draw = 0",
        f"dowhile draw < {draws}",
        "  reset",
        f"  tran {STEP / 5:.12g} {span:.12g} 0 {STEP:.12g}",
    ]
    for index, moment in enumerate(read_moments(len(asked), drive)):
        lines += [
            f"  meas tran p{index} find v(outp) at={moment:.12g}",
            f"  meas tran n{index} find v(outn) at={moment:.12g}",
        ]
    lines += ["  let draw = draw + 1", "end", ".endc", ".end"]
    return "\n".join(lines) + "\n"


def separations(workdir, sizes: Sizes, devices, levels, drive: Drive, **kwargs):
    """Signed output separation for every question asked, volts.

    Rows are draws and columns are the levels in the order they were asked.
    Positive means the latch said `inp` was the greater, so where a row of a
    difference sweep changes sign is where that part's own decision boundary
    lies.
    """
    levels = list(levels)
    found = ngspice.run(deck(sizes, devices, levels, drive, **kwargs), workdir)
    width = len(levels)
    high = np.array([found[f"p{index}"] for index in range(width)]).T
    low = np.array([found[f"n{index}"] for index in range(width)]).T
    return high - low


def boundary(differences, separation) -> float:
    """Where one part's decision boundary sits, volts of input difference.

    The input-referred offset: the difference the latch calls a tie. Found by
    interpolating the separation through zero rather than by bisection, so one
    run answers it.

    It refuses a staircase that does not bracket the crossing instead of
    returning its nearest end, because an offset reported as the edge of the
    range it was looked for in is indistinguishable from a real answer and
    reads as a suspiciously round number.
    """
    order = np.argsort(differences)
    swept, signs = np.asarray(differences)[order], np.asarray(separation)[order]
    crossings = np.nonzero(np.diff(np.sign(signs)))[0]
    if not crossings.size:
        raise ValueError(
            f"no decision boundary between {swept[0]:g} V and {swept[-1]:g} V: "
            f"the latch answered {'high' if signs[0] > 0 else 'low'} throughout"
        )
    k = crossings[0]
    gap = signs[k + 1] - signs[k]
    return float(swept[k] - signs[k] * (swept[k + 1] - swept[k]) / gap)
