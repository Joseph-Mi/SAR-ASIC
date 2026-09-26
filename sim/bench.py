"""A transient testbench around the analog block, driven phase by phase.

Contract: a bench is a list of phases, each holding every digital input at a
level for one phase length. The first phase must be sampling -- at time zero
the top plate is joined to Vcm, so the operating point exists; a bench that
starts with the top plate floating asks the simulator for the voltage of a
node with no DC path, and gets whatever its solver makes up.

Results come back per phase, read just before the phase ends, when whatever
that phase set moving has had the whole phase to settle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import analog
from analog import NAME, terminals
from sar import VCM_FRACTION

#: One protocol phase. Ideal switches settle in picoseconds; this only has to be
#: long enough that the edges are a small part of it.
PHASE = 10e-9

#: Rise and fall of every digital edge.
EDGE = 0.1e-9

#: How long before a phase ends its results are read, as a fraction of the
#: phase: late enough to see everything the phase settled, early enough that
#: the next phase's edges have not begun.
READ_BEFORE_END = 0.02

#: Largest internal timestep, as a fraction of a phase, so no phase is stepped
#: over.
MAX_STEP = 0.01

#: Solver relative tolerance. The default, a part in a thousand, lets the
#: floating top plate drift by a visible fraction of an LSB at the target
#: resolution; a floating node's charge has to be conserved far more tightly
#: than the answer it is compared against. A decade tighter brings it well under
#: that at no cost in run time. Tighter again stalls the solver on the ideal
#: switches' hard edges without buying anything a test can see.
RELTOL = 1e-4

#: Times are written with this many significant digits. A long sweep runs to
#: tens of microseconds while its edges and read points are a fraction of a
#: nanosecond apart, so fewer digits round a read into the wrong phase, or past
#: the end of the run.
TIME_DIGITS = 12

#: What is read at the end of every phase, and where. The top plate is inside
#: the block; the comparator outputs are its terminals, named by their nets.
#: Result names differ from every net name: a measurement named after a vector
#: that already exists is refused.
PROBES = {"m_top": "v(xdut.top)", "m_cmp": "v(cmp_out)", "m_cmp_n": "v(cmp_out_n)"}


@dataclass(frozen=True)
class Phase:
    """Every digital input's level for one phase. `dac_b` is a word."""

    sample: int = 0
    dac_b: int = 0
    cmp_clk: int = 0
    force_en: int = 0
    force_hi: int = 0
    #: The pin's level during this phase; None leaves it at the supplies' vin.
    #: Only a sampling phase can show it to the array -- the point of letting it
    #: move elsewhere is to prove that.
    vin: float | None = None


@dataclass(frozen=True)
class IdealVcm:
    """The common-mode pin held by an ideal source at `fraction` of the
    reference: nothing sampling does can move it."""

    fraction: float = VCM_FRACTION


@dataclass(frozen=True)
class PinVcm:
    """The common-mode pin as the design has it: a source off-chip, decoupled
    there so heavily that it does not move, reaching the pin through
    `r_pin`. What sampling kicks settles through that resistance."""

    r_pin: float
    fraction: float = VCM_FRACTION


@dataclass(frozen=True)
class Divider:
    """The alternative the pin replaced, kept to measure it against: a resistor
    string across the reference inside the chip, tapped onto the common mode,
    optionally decoupled. Its current is drawn through the reference pin."""

    r_total: float
    fraction: float = VCM_FRACTION
    c_dec: float = 0.0


@dataclass(frozen=True)
class Supplies:
    vdd: float = 1.8
    vref: float = 1.0
    vin: float = 0.0


@dataclass
class Bench:
    phases: list[Phase]
    supplies: Supplies = field(default_factory=Supplies)
    n_bits: int = analog.N_BITS
    unit: analog.Ideal | analog.Mim = analog.DEFAULT_UNIT
    c_par: float = 0.0
    #: Length of every phase. Settling is measured by shortening it.
    phase: float = PHASE
    #: Series resistance between each source and its pin -- the package, bond
    #: wire and pad the signal crosses before it reaches the block.
    r_vin: float = 0.0
    r_vref: float = 0.0
    #: Switch on-resistances, passed to the block.
    ron_unit: float = analog.IDEAL_RON
    ron_top: float = analog.IDEAL_RON
    #: How the block samples: ideal switches, or transistors and how their
    #: phases are made. Passed to the block.
    sampling: analog.Gapped | analog.NonOverlap | None = None
    #: Lines added to the control block after the reads, for measurements a
    #: phase-end read cannot make -- when an edge crosses a level, say.
    extra_control: list[str] = field(default_factory=list)
    #: What drives the common-mode pin.
    vcm: IdealVcm | PinVcm | Divider = field(default_factory=IdealVcm)
    #: Phases whose results are read; None reads every one. A sweep of many
    #: conversions in one run reads only the phases it checks, because every
    #: read is a measurement the simulator has to evaluate.
    read: list[int] | None = None
    #: What is read; defaults to every probe.
    probes: dict[str, str] | None = None


def _pwl(values: list[float], phase: float) -> str:
    """A PWL source holding each value for one phase, switching at the edges.

    A value repeated across phases adds no points, so a long run of constant
    phases costs the simulator nothing.
    """
    points = [(0.0, values[0])]
    for i in range(1, len(values)):
        if values[i] == values[i - 1]:
            continue
        edge = i * phase
        points.append((edge, values[i - 1]))
        points.append((edge + EDGE, values[i]))
    points.append((len(values) * phase, values[-1]))
    return "PWL(" + " ".join(f"{t:.{TIME_DIGITS}g} {v:.9g}" for t, v in points) + ")"


def _pin(name: str, source: str, resistance: float) -> list[str]:
    """A source reaching its pin through `resistance`, or directly at zero --
    so a test that means no pin gets none, not a small one."""
    if not resistance:
        return [f"V{name} {name} 0 {source}"]
    return [f"V{name} {name}_src 0 {source}", f"R{name} {name}_src {name} {resistance:.9g}"]


def _common_mode(vcm: IdealVcm | PinVcm | Divider, vref: float) -> list[str]:
    """What drives the common-mode pin. A divider hangs on the reference's
    chip side, so its current crosses whatever the reference pin is."""
    if isinstance(vcm, IdealVcm):
        return [f"Bvcm vcm 0 V = {vcm.fraction}*v(vref)"]
    if isinstance(vcm, PinVcm):
        return _pin("vcm", f"{vcm.fraction * vref:.9g}", vcm.r_pin)
    lines = [
        f"Rvcm_hi vref vcm {vcm.r_total * (1 - vcm.fraction):.9g}",
        f"Rvcm_lo vcm 0 {vcm.r_total * vcm.fraction:.9g}",
    ]
    if vcm.c_dec:
        lines.append(f"Cvcm vcm 0 {vcm.c_dec:.6e}")
    return lines


def _node(terminal: str) -> str:
    """Testbench net for a terminal: brackets are not portable in node names."""
    return terminal.replace("[", "_").replace("]", "")


def deck(bench: Bench) -> str:
    if not bench.phases or not bench.phases[0].sample:
        raise ValueError("a bench starts by sampling, or the top plate has no DC path")

    s = bench.supplies
    header = [] if bench.sampling is None else bench.sampling.devices.header()
    lines = [
        f"* {NAME} bench",
        *header,
        analog.subckt(
            bench.n_bits, bench.unit, bench.c_par, bench.ron_unit, bench.ron_top, bench.sampling
        ),
        "Vvss vss 0 0",
        f"Vvdd vdd 0 {s.vdd}",
        *_pin("vref", str(s.vref), bench.r_vref),
    ]
    lines += _common_mode(bench.vcm, s.vref)
    pin = [s.vin if p.vin is None else p.vin for p in bench.phases]
    lines += _pin("vin", _pwl(pin, bench.phase), bench.r_vin)

    drives = {
        "sample": [p.sample for p in bench.phases],
        "cmp_clk": [p.cmp_clk for p in bench.phases],
        "force_en": [p.force_en for p in bench.phases],
        "force_hi": [p.force_hi for p in bench.phases],
    }
    for k in range(bench.n_bits):
        drives[f"dac_b[{k}]"] = [(p.dac_b >> k) & 1 for p in bench.phases]
    for terminal, levels in drives.items():
        volts = [level * s.vdd for level in levels]
        lines.append(f"V_{_node(terminal)} {_node(terminal)} 0 {_pwl(volts, bench.phase)}")

    lines.append("Xdut " + " ".join(_node(t) for t in terminals(bench.n_bits)) + f" {NAME}")

    stop = len(bench.phases) * bench.phase
    step = MAX_STEP * bench.phase
    lines.append(f".options reltol={RELTOL}")
    lines += [
        ".control",
        f"tran {step:.{TIME_DIGITS}g} {stop:.{TIME_DIGITS}g} 0 {step:.{TIME_DIGITS}g}",
    ]
    read = range(len(bench.phases)) if bench.read is None else bench.read
    probes = PROBES if bench.probes is None else bench.probes
    for i in read:
        at = (i + 1 - READ_BEFORE_END) * bench.phase
        for name, expression in probes.items():
            lines.append(f"meas tran {name} find {expression} at={at:.{TIME_DIGITS}g}")
    lines += bench.extra_control
    lines += [".endc", ".end"]
    return "\n".join(lines) + "\n"
