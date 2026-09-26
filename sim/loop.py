"""The analog block run by the RTL that will run it on the chip.

Nothing replays a decision here. The controller is the Verilog itself,
compiled into the simulation, choosing each trial word from what the block's
comparator just answered -- so a conversion is right only if the controller,
the boundary between the halves and the block all are.

Contract: conversions run one after another at a fixed pace. Each is started
by one pulse while the controller is idle, and the input pin moves to the
next conversion's level with that pulse -- the pin is steady for the whole of
every conversion, and whatever it changed by has to be sampled away within
the controller's sampling cycle.

Controller ports carry a direction suffix the block's terminals do not; the
same name without it is the same wire. A port whose wire is a terminal of the
block is joined to it, and the rest are the bench's.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import analog
import bench
import cosim
import ngspice
from analog import NAME, terminals
from bench import Divider, IdealVcm, PinVcm, Supplies
from interface import TO_ANALOG, TO_DIGITAL
from protocol import conversion_sequence
from sar import ideal_units
from sweep import BATCH

#: Port suffixes that say which way a controller port points, and what each
#: leaves of the wire's name.
SUFFIXES = (("_ni", "_n"), ("_i", ""), ("_o", ""))

#: Cycles the controller is held in reset before the first conversion.
RESET_CYCLES = 2

#: Cycles between one conversion finishing and the next starting: the
#: controller sees a start only while idle, and it is idle for this long.
IDLE_CYCLES = 1

#: How far into a cycle each start pulse, the pin's move and the release of
#: reset begin, as a fraction of it: clear of both clock edges. Two sources
#: with an edge at the same instant, each computing that instant its own way,
#: can put their breakpoints closer than the solver's smallest step, and it
#: stops advancing.
START_OFFSET = 0.25

#: The controller's wires that are the bench's rather than the block's.
CLOCK, RESET, START = "clk", "rst_n", "start"
DONE, CODE, FLAG = "done", "code", "metastable"


def wire(port: str) -> str:
    """The wire a controller port is on: its name without the direction."""
    for suffix, kept in SUFFIXES:
        if port.endswith(suffix):
            return port[: -len(suffix)] + kept
    return port


def pin_wire(pin: str) -> str:
    """The wire of one bit of a controller port, as a testbench node."""
    port, bracket, bit = pin.partition("[")
    return bench.node(wire(port) + bracket + bit)


@dataclass
class Loop:
    """Conversions of `inputs` by the compiled controller `library`.

    The block's settings carry `Bench`'s field names and meaning.
    """

    inputs: list[float]
    library: cosim.Library
    supplies: Supplies = field(default_factory=Supplies)
    n_bits: int = analog.N_BITS
    unit: analog.Ideal | analog.Mim = analog.DEFAULT_UNIT
    c_par: float = 0.0
    r_vin: float = 0.0
    r_vref: float = 0.0
    ron_unit: float = analog.IDEAL_RON
    ron_top: float = analog.IDEAL_RON
    sampling: analog.Gapped | analog.NonOverlap | None = None
    vcm: IdealVcm | PinVcm | Divider = field(default_factory=IdealVcm)
    #: One controller clock cycle.
    clock: float = bench.PHASE

    @property
    def period(self) -> int:
        """Cycles from one start to the next."""
        steps = conversion_sequence(0.0, ideal_units(self.n_bits), self.supplies.vref)
        return len(steps) + IDLE_CYCLES

    def start_at(self, i: int) -> float:
        """When conversion `i`'s start pulse begins. It lasts one cycle, so
        exactly one rising edge sees it."""
        return (RESET_CYCLES + IDLE_CYCLES + i * self.period + START_OFFSET) * self.clock


def _wiring(loop: Loop) -> tuple[list[str], list[str]]:
    """The controller's pins, split into those it reads and those it drives,
    as testbench nodes; and a check that it closes the loop the interface
    declares."""
    reads = [pin_wire(p) for p in loop.library.inputs]
    drives = [pin_wire(p) for p in loop.library.outputs]
    for port in TO_DIGITAL:
        if port.name not in reads:
            raise ValueError(f"the controller does not read the block's {port.name}")
    return reads, drives


def deck(loop: Loop) -> str:
    s = loop.supplies
    t = loop.clock
    half = s.vdd / 2
    reads, drives = _wiring(loop)

    lines = [f"* {NAME} closed loop", *bench.surroundings(loop)]

    vin = [(0.0, loop.inputs[0])]
    for i in range(1, len(loop.inputs)):
        edge = loop.start_at(i)
        vin += [(edge, loop.inputs[i - 1]), (edge + bench.EDGE, loop.inputs[i])]
    lines += bench.pin(
        "vin", "PWL(" + " ".join(f"{a:.12g} {v:.9g}" for a, v in vin) + ")", loop.r_vin
    )

    lines.append(
        f"V{CLOCK} {CLOCK} 0 PULSE(0 {s.vdd} {t / 2:.12g} {bench.EDGE:.12g} "
        f"{bench.EDGE:.12g} {t / 2 - bench.EDGE:.12g} {t:.12g})"
    )
    release = (RESET_CYCLES + START_OFFSET) * t
    lines.append(
        f"V{RESET} {RESET} 0 PWL(0 0 {release:.12g} 0 {release + bench.EDGE:.12g} {s.vdd})"
    )
    pulses = ["0 0"]
    for i in range(len(loop.inputs)):
        a = loop.start_at(i)
        pulses += [f"{a:.12g} 0", f"{a + bench.EDGE:.12g} {s.vdd}"]
        pulses += [f"{a + t:.12g} {s.vdd}", f"{a + t + bench.EDGE:.12g} 0"]
    lines.append(f"V{START} {START} 0 PWL({' '.join(pulses)})")

    # Block inputs the controller does not drive are held at their reset level.
    driven = set(drives)
    ports = terminals(loop.n_bits)
    boundary = {p.name for p in TO_ANALOG}
    for terminal in ports:
        if terminal.partition("[")[0] in boundary and bench.node(terminal) not in driven:
            lines.append(f"V_{bench.node(terminal)} {bench.node(terminal)} 0 0")

    nets = {p: f"d_{pin_wire(p)}" for p in loop.library.inputs + loop.library.outputs}
    lines += cosim.reads("in", reads, [f"d_{w}" for w in reads], half)
    lines += cosim.element("ctl", loop.library, nets)
    lines += cosim.drives("out", [f"d_{w}" for w in drives], drives, s.vdd, bench.EDGE)
    lines.append("Xdut " + " ".join(bench.node(p) for p in ports) + f" {NAME}")

    code = [w for w in drives if w.startswith(f"{CODE}_")]
    word = " + ".join(f"(v({w}) gt {half:.9g})*{2 ** int(w.rsplit('_', 1)[1])}" for w in code)
    stop = loop.start_at(len(loop.inputs)) + t
    step = bench.MAX_STEP * t
    lines.append(f".options reltol={bench.RELTOL}")
    lines += [
        ".control",
        f"tran {step:.12g} {stop:.12g} 0 {step:.12g}",
        f"let word = {word}",
    ]
    # Each result is read as the done flag falls: the code changes only on the
    # edge that raises it, so by then it has held for the whole done cycle.
    for k in range(1, len(loop.inputs) + 1):
        done = f"when v({DONE})={half:.9g} fall={k}"
        lines += [
            f"meas tran m_code find word {done}",
            f"meas tran m_flag find v({FLAG}) {done}",
            f"meas tran t_sampled when v(sample)={half:.9g} fall={k}",
            f"meas tran t_done {done}",
            "meas tran m_low min v(xdut.top) from=$&t_sampled to=$&t_done",
        ]
    lines += [".endc", ".end"]
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class Result:
    """Per conversion: the code, whether the flag was up, and the lowest the
    top plate went between the end of sampling and the result."""

    codes: list[int]
    flags: list[bool]
    lows: list[float]


def run(loop: Loop, workdir) -> Result:
    found = ngspice.run(deck(loop), workdir)
    n = len(loop.inputs)
    got = {k: found.get(k, []) for k in ("m_code", "m_flag", "m_low")}
    if any(len(v) != n for v in got.values()):
        raise ngspice.DeckError(
            f"{n} conversions started, results for {[len(v) for v in got.values()]}"
        )
    half = loop.supplies.vdd / 2
    return Result(
        codes=[round(c) for c in got["m_code"]],
        flags=[f > half for f in got["m_flag"]],
        lows=got["m_low"],
    )


def convert(inputs, library: cosim.Library, workdir, **loop_args) -> Result:
    """`run`, in batches of the sweep's size, each its own run from reset."""
    parts = [
        run(Loop(list(inputs[i : i + BATCH]), library, **loop_args), workdir)
        for i in range(0, len(inputs), BATCH)
    ]
    return Result(
        codes=[c for p in parts for c in p.codes],
        flags=[f for p in parts for f in p.flags],
        lows=[v for p in parts for v in p.lows],
    )
