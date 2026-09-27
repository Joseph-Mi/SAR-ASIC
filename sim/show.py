"""Watch the converter convert: the closed loop, drawn.

Contract: `show` runs the real controller against the analog block for the
given inputs and writes two files -- a figure, and the waveforms as an ngspice
raw file for any viewer that reads one. The figure puts, on one time axis,
the top plate with the level the golden model expects at every trial, the
trial word the controller drives, and every control line. Nothing is
asserted: a disagreement is there to be seen.

matplotlib is imported inside `draw`, as in `studies/plots.py`: CI's digital
job does not install it, and a module-scope import fails test collection there
before the ngspice skip can apply.
"""

from __future__ import annotations

import argparse
import pathlib
from dataclasses import dataclass, replace

import numpy as np

import analog
import bench
import cosim
import loop
import ngspice
from bench import Block, Supplies
from interface import N_BITS
from measure import first_trial_error, law_clock
from sar import VCM_FRACTION, ideal_units, sar_convert, top_plate_voltage
from sweep import EDGE_OFFSET_LSB, lsb

REPO = next(p for p in pathlib.Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
CONTROLLER = REPO / "hdl" / "rtl" / "sar_fsm.v"
OUT_DIR = REPO / "build" / "show"

#: The inputs drawn when none are given, as fractions of the reference: one
#: below mid-scale and one near the top, so both halves of the search show.
DEFAULT_INPUTS = (0.3, 0.9)

# How the figure looks. None of it carries a result. Series colours follow the
# validated categorical order, in that order, and text stays in neutral ink.
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
INK, INK_SOFT, RULE, SURFACE = "#0b0b0b", "#52514e", "#c9c8c3", "#fcfcfb"
LINE, THIN = 1.5, 0.8
FONT_SMALL, FONT_LABEL, FONT_TITLE = 8, 9, 11
FIGSIZE = (12, 8)
HEIGHTS = (3, 2, 3)
DPI = 140
NS = 1e-9

#: A control line drawn in its lane fills this fraction of the lane's height,
#: leaving a gap between lanes.
LANE_FILL = 0.8

#: Space kept above and below the top plate's excursion, as a fraction of it,
#: so the decision labels clear the frame.
HEADROOM = 0.15

#: Where after the strobe's rising edge the latched decision is read, and
#: where before it the top plate is: as fractions of a clock, clear of both
#: edges.
DECISION_AT, TOP_BEFORE = 0.25, 0.05


@dataclass
class Trace:
    time: np.ndarray
    wave: dict[str, np.ndarray]

    def at(self, node: str, t: float) -> float:
        return float(np.interp(t, self.time, self.wave[node]))

    def rising(self, node: str, level: float) -> list[float]:
        v = self.wave[node]
        idx = np.nonzero((v[:-1] < level) & (v[1:] >= level))[0]
        return [float(np.interp(level, v[i : i + 2], self.time[i : i + 2])) for i in idx]


def lines(block: Block) -> list[str]:
    """The control lines worth drawing for this block, in the order they act."""
    scheme = block.sampling
    names = ["sample"]
    if isinstance(scheme, analog.NonOverlap):
        names += ["xdut.phi_top", "xdut.phi_bot"]
        if scheme.switches.w_unit_p:
            names.append("xdut.phi_bot_n")
        names.append("xdut.phi_conv")
    return names + ["cmp_clk", "cmp_out", "done"]


def record(
    inputs, block: Block, clock: float, library: cosim.Library, out: pathlib.Path
) -> tuple[Trace, loop.Result, loop.Loop]:
    """Run the loop once, keeping every waveform the figure needs."""
    dac = [f"dac_b_{k}" for k in range(block.n_bits)]
    nodes = ["xdut.top", "vcm", *lines(block), *dac]
    vectors = " ".join(f"v({n})" for n in nodes)
    table = out.with_suffix(".txt")
    # Bare names: ngspice runs in the output's folder, and a folder's path
    # may hold characters a deck line cannot carry.
    raw = out.with_suffix(".raw")
    run = loop.Loop(
        list(inputs),
        library,
        block,
        clock,
        extra_control=[f"wrdata {table.name} {vectors}", f"write {raw.name} {vectors}"],
    )
    found = ngspice.run(loop.deck(run), out.parent)
    half = block.supplies.vdd / 2
    result = loop.Result(
        codes=[round(c) for c in found["m_code"]],
        flags=[f > half for f in found["m_flag"]],
        lows=found["m_low"],
    )
    rows = np.loadtxt(table)
    time = rows[:, 0]
    wave = {n: rows[:, 2 * i + 1] for i, n in enumerate(nodes)}
    wave["word"] = sum((wave[d] > half) * (1 << k) for k, d in enumerate(dac))
    return Trace(time, wave), result, run


def draw(
    trace: Trace, result: loop.Result, run: loop.Loop, out: pathlib.Path, zoom=None, offset=0.0
):
    """The figure. `offset` is the block's sampling offset, in volts: when
    given, each code is also compared with the model told of it, as a
    calibrated converter would be."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    block = run.block
    vref, vdd = block.supplies.vref, block.supplies.vdd
    units = ideal_units(block.n_bits)
    vcm = VCM_FRACTION * vref
    t = trace.time / NS
    starts = [run.start_at(i) for i in range(len(run.inputs) + 1)]

    plt.rcParams.update({"font.size": FONT_LABEL, "axes.edgecolor": RULE, "text.color": INK})
    fig, (top, word, ctrl) = plt.subplots(
        3, 1, sharex=True, figsize=FIGSIZE, gridspec_kw={"height_ratios": HEIGHTS}
    )
    fig.patch.set_facecolor(SURFACE)
    for ax in (top, word, ctrl):
        ax.set_facecolor(SURFACE)
        ax.tick_params(colors=INK_SOFT, labelsize=FONT_SMALL)
        ax.grid(color=RULE, lw=THIN / 2, alpha=0.6)

    top.plot(t, trace.wave["xdut.top"], color=SERIES[0], lw=LINE, label="top plate")
    top.axhline(vcm, color=INK_SOFT, lw=THIN, ls="--", label="Vcm (decision level)")
    strobes = trace.rising("cmp_clk", vdd / 2)
    first_model = True
    for s in strobes:
        i = next(k for k in range(len(run.inputs)) if starts[k] <= s < starts[k + 1])
        vin = run.inputs[i]
        before = s - TOP_BEFORE * run.clock
        w = int(round(trace.at("word", before)))
        expected = top_plate_voltage(vin, w, units, vref)
        top.hlines(
            expected,
            (s - run.clock) / NS,
            s / NS,
            color=SERIES[1],
            lw=LINE,
            label="model, at this trial word" if first_model else None,
        )
        first_model = False
        keep = trace.at("cmp_out", s + DECISION_AT * run.clock) > vdd / 2
        top.annotate(
            "1" if keep else "0",
            (s / NS, trace.at("xdut.top", before)),
            textcoords="offset points",
            xytext=(0, 6),
            ha="center",
            fontsize=FONT_SMALL,
            color=INK_SOFT,
        )
    top.margins(y=HEADROOM)
    top.set_ylabel("volts", color=INK_SOFT)
    top.legend(fontsize=FONT_SMALL, loc="upper right", frameon=False)

    word.step(t, trace.wave["word"], where="post", color=SERIES[0], lw=LINE)
    word.set_ylabel("trial word (dac_b)", color=INK_SOFT)
    word.set_ylim(-0.5, 2**block.n_bits - 0.5)
    word.yaxis.set_major_locator(MaxNLocator(integer=True))

    names = lines(block)
    for lane, name in enumerate(reversed(names)):
        colour = SERIES[(len(names) - 1 - lane) % len(SERIES)]
        ctrl.plot(t, lane + LANE_FILL * trace.wave[name] / vdd, color=colour, lw=LINE)
    ctrl.set_yticks([lane + LANE_FILL / 2 for lane in range(len(names))])
    ctrl.set_yticklabels([n.removeprefix("xdut.") for n in reversed(names)], color=INK)
    ctrl.set_xlabel("time  [ns]", color=INK_SOFT)

    shown = range(len(run.inputs)) if zoom is None else [zoom]
    for i in shown:
        vin, got = run.inputs[i], result.codes[i]
        want = sar_convert(vin, units, vref)[0]
        header = f" vin {vin:.4f} V: code {got}, model {want}"
        if offset:
            calibrated = sar_convert(vin, units, vref, cmp_offset=-offset)[0]
            header += f", model with the block's offset {calibrated}"
            want = calibrated
        header += "" if got == want else "   <-- differs"
        for ax in (top, word, ctrl):
            ax.axvline(starts[i] / NS, color=RULE, lw=THIN)
        top.text(
            starts[i] / NS,
            1.0,
            header,
            transform=top.get_xaxis_transform(),
            va="bottom",
            fontsize=FONT_SMALL,
            color=INK,
            clip_on=False,
        )
    if zoom is not None:
        top.set_xlim(starts[zoom] / NS, starts[zoom + 1] / NS)

    kind = "designed block" if block.sampling is not None else "ideal switches"
    fig.suptitle(
        f"Closed loop, {block.n_bits} bits, {kind}, clock {run.clock / NS:.2f} ns",
        fontsize=FONT_TITLE,
        color=INK,
    )
    fig.tight_layout()
    fig.savefig(out, dpi=DPI, facecolor=SURFACE)
    plt.close(fig)


def show(inputs, n_bits: int, designed: bool, clock=None, zoom=None, out=None):
    """Run and draw; returns where the figure and the raw file went."""
    block = replace(bench.DESIGNED if designed else Block(), n_bits=n_bits, supplies=Supplies())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # The simulator runs in the output's folder, so every path it is handed
    # has to mean the same thing from there.
    out = pathlib.Path(out).resolve() if out else OUT_DIR / "loop.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    if clock is None:
        tolerance = EDGE_OFFSET_LSB * lsb(n_bits, block.supplies.vref)
        clock = law_clock(OUT_DIR, block, tolerance) if designed else bench.PHASE
    build = REPO / "build" / "sim" / "cosim" / f"sar_fsm_{n_bits}"
    library = cosim.build(CONTROLLER, build, {"N_BITS": n_bits})
    mid = VCM_FRACTION * block.supplies.vref
    offset = first_trial_error(OUT_DIR, block, mid) if designed else 0.0
    trace, result, run = record(inputs, block, clock, library, out)
    draw(trace, result, run, out, zoom, offset)
    units = ideal_units(n_bits)
    for vin, code in zip(inputs, result.codes, strict=True):
        model = sar_convert(vin, units, block.supplies.vref)[0]
        calibrated = sar_convert(vin, units, block.supplies.vref, cmp_offset=-offset)[0]
        print(f"vin {vin:.4f} V -> code {code}  (model {model}, with the offset {calibrated})")
    print(f"-> {out}\n-> {out.with_suffix('.raw')}")
    return out, out.with_suffix(".raw")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--vin", type=float, nargs="+", help="inputs, volts")
    p.add_argument("--bits", type=int, default=N_BITS)
    p.add_argument("--designed", action="store_true", help="transistor switches and the generator")
    p.add_argument(
        "--clock",
        type=float,
        help="clock period, seconds (default: ideal bench phase, or the law's clock)",
    )
    p.add_argument("--zoom", type=int, help="draw only this conversion, counted from 0")
    p.add_argument("--out", help="figure path (default build/show/loop.png)")
    a = p.parse_args()
    vref = Supplies().vref
    inputs = a.vin if a.vin else [f * vref for f in DEFAULT_INPUTS]
    show(inputs, a.bits, a.designed, a.clock, a.zoom, a.out)


if __name__ == "__main__":
    main()
