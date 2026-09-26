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

#: One protocol phase. Ideal switches settle in picoseconds; this only has to be
#: long enough that the edges are a small part of it.
PHASE = 10e-9

#: Rise and fall of every digital edge.
EDGE = 0.1e-9

#: How long before a phase ends its results are read.
READ_BEFORE_END = 0.5e-9

#: Largest internal timestep, as a fraction of a phase, so no phase is stepped
#: over.
MAX_STEP = PHASE / 100

#: Solver relative tolerance. The default, a part in a thousand, lets the
#: floating top plate drift by a visible fraction of an LSB at the target
#: resolution; a floating node's charge has to be conserved far more tightly
#: than the answer it is compared against. A decade tighter brings it well under
#: that at no cost in run time. Tighter again stalls the solver on the ideal
#: switches' hard edges without buying anything a test can see.
RELTOL = 1e-4

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


def _pwl(levels: list[int], high: float) -> str:
    """A PWL source holding each level for one phase, switching at the edges."""
    points = [(0.0, levels[0] * high)]
    for i in range(1, len(levels)):
        edge = i * PHASE
        points.append((edge, levels[i - 1] * high))
        points.append((edge + EDGE, levels[i] * high))
    points.append((len(levels) * PHASE, levels[-1] * high))
    return "PWL(" + " ".join(f"{t:.4e} {v:.6g}" for t, v in points) + ")"


def _node(terminal: str) -> str:
    """Testbench net for a terminal: brackets are not portable in node names."""
    return terminal.replace("[", "_").replace("]", "")


def deck(bench: Bench) -> str:
    if not bench.phases or not bench.phases[0].sample:
        raise ValueError("a bench starts by sampling, or the top plate has no DC path")

    s = bench.supplies
    lines = [
        f"* {NAME} bench",
        analog.subckt(bench.n_bits, bench.unit, bench.c_par),
        "Vvss vss 0 0",
        f"Vvdd vdd 0 {s.vdd}",
        f"Vvref vref 0 {s.vref}",
        f"Vvin vin 0 {s.vin}",
    ]

    drives = {
        "sample": [p.sample for p in bench.phases],
        "cmp_clk": [p.cmp_clk for p in bench.phases],
        "force_en": [p.force_en for p in bench.phases],
        "force_hi": [p.force_hi for p in bench.phases],
    }
    for k in range(bench.n_bits):
        drives[f"dac_b[{k}]"] = [(p.dac_b >> k) & 1 for p in bench.phases]
    for terminal, levels in drives.items():
        lines.append(f"V_{_node(terminal)} {_node(terminal)} 0 {_pwl(levels, s.vdd)}")

    lines.append("Xdut " + " ".join(_node(t) for t in terminals(bench.n_bits)) + f" {NAME}")

    stop = len(bench.phases) * PHASE
    lines.append(f".options reltol={RELTOL}")
    lines += [".control", f"tran {MAX_STEP:.4e} {stop:.4e} 0 {MAX_STEP:.4e}"]
    for i in range(len(bench.phases)):
        at = (i + 1) * PHASE - READ_BEFORE_END
        for name, expression in PROBES.items():
            lines.append(f"meas tran {name} find {expression} at={at:.4e}")
    lines += [".endc", ".end"]
    return "\n".join(lines) + "\n"
