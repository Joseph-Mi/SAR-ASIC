"""Trip point, small-signal gain and mismatch of the experimental inverter.

Contract: the testbench must have been netlisted, and that netlist must still
define the cell as an instantiable subcircuit.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import pathlib
import re
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from tools import netlist, ngspice, sky130  # noqa: E402

HERE = pathlib.Path(__file__).parent
WORKDIR = HERE / "simulation"
NETLIST = WORKDIR / "tb_inv.spice"
PEXLIST = HERE / "inv.pex.spice"
WAVES = WORKDIR / "pex_waves.csv"
PLOT = WORKDIR / "pex_compare.png"
MC_PLOT = WORKDIR / "mc_spread.png"
CELL = "inv"

VDD = 1.8
CLOAD = "10f"
VIN_STEP = 0.005
NOMINAL_TEMP = 27
EDGE = "100p"
PULSE = f"pulse 0 {VDD} 1n {EDGE} {EDGE} 5n 10n"
TRAN = "1p 12n"
WINDOW = 300e-12


class Point:
    """One geometry under study, and the node it is measured on."""

    def __init__(self, index: int, wn: float, wp: float, length: float, mult: int = 1):
        self.index = index
        self.wn = wn
        self.wp = wp
        self.length = length
        self.mult = mult
        self.cell = f"cell{index}"
        self.node = f"out{index}"

    def params(self, match) -> dict[str, float]:
        pull_down = "__nfet" in match.group("model")
        return sky130.mosfet(self.wn if pull_down else self.wp, self.length, self.mult)


def deck(points: list[Point], corner: str, mismatch: bool, control: str) -> str:
    source = NETLIST.read_text()
    cell = ngspice.subckt(source, CELL)
    lines = [
        f".lib {ngspice.library(source)} {corner}",
        f".param mc_mm_switch={int(mismatch)}",
        ".param mc_pr_switch=0",
        "",
    ]
    for point in points:
        sized = netlist.restamp(cell, sky130.MOSFET, point.params)
        lines.append(sized.replace(f".subckt {CELL} ", f".subckt {point.cell} ", 1))
    lines += ["", f"VDD vdd 0 {VDD}", "VIN in 0 dc 0"]
    for point in points:
        lines.append(f"X{point.index} vdd {point.node} in 0 {point.cell}")
        lines.append(f"C{point.index} {point.node} 0 {CLOAD}")
    return "\n".join([*lines, "", control, ".end", ""])


def vtc_control(points: list[Point], temp: float) -> str:
    lines = [".control", "set nomodcheck"]
    if temp != NOMINAL_TEMP:
        lines.append(f"option temp = {temp:g}")
    lines.append(f"dc VIN 0 {VDD} {VIN_STEP}")
    for p in points:
        lines += [
            f"let diff{p.index} = v({p.node}) - v(in)",
            f"meas dc vm{p.index} when diff{p.index}=0",
            f"let slope{p.index} = deriv(v({p.node}))",
            f"meas dc gain{p.index} find slope{p.index} when diff{p.index}=0",
            f"meas dc peak{p.index} min slope{p.index}",
        ]
    return "\n".join([*lines, ".endc"])


def mc_control(points: list[Point], runs: int) -> str:
    """A draw per pass. `reset` is what re-evaluates the PDK's mismatch terms."""
    lines = [
        ".control",
        "set nomodcheck",
        "let k = 0",
        f"dowhile k < {runs}",
        "  reset",
        f"  dc VIN 0 {VDD} {VIN_STEP}",
    ]
    for p in points:
        lines += [
            f"  let diff{p.index} = v({p.node}) - v(in)",
            f"  meas dc vm{p.index} when diff{p.index}=0",
        ]
    return "\n".join([*lines, "  let k = k + 1", "end", ".endc"])


def rename(subckt: str, new: str) -> str:
    return re.sub(rf"(?m)^(\.subckt\s+){re.escape(CELL)}\b", rf"\g<1>{new}", subckt)


def instance(ref: str, subckt: str, cell: str, nets: dict[str, str]) -> str:
    return f"{ref} " + " ".join(nets[p] for p in ngspice.ports(subckt)) + f" {cell}"


def cmd_pex(args: argparse.Namespace) -> None:
    """Delay of the drawn cell against the designed one, across load."""
    if not PEXLIST.exists():
        raise ngspice.DeckError(f"{PEXLIST.name} not found -- run `make pex` first")
    source = NETLIST.read_text()
    # Extraction does not write the source and drain sheet-resistance terms
    # that the schematic instance carries. Left in, they slow one side only and
    # the difference stops being the parasitics.
    sch = re.sub(r"\s+nr[ds]=\S+", "", ngspice.subckt(source, CELL))
    pex = ngspice.subckt(PEXLIST.read_text(), CELL)

    lines = [
        f".lib {ngspice.library(source)} {args.corner}",
        ".param mc_mm_switch=0",
        ".param mc_pr_switch=0",
        "",
        rename(sch, "inv_sch"),
        rename(pex, "inv_pex"),
        "",
        f"VDD vdd 0 {VDD}",
        f"VIN in 0 {PULSE}",
    ]
    control = [".control", "set nomodcheck", f"tran {TRAN}"]
    for i, load in enumerate(args.loads):
        for tag, sub, cell in (("sch", sch, "inv_sch"), ("pex", pex, "inv_pex")):
            node = f"out_{tag}{i}"
            # By name: an extracted subcircuit declares its terminals in a
            # different order, and wiring by position miswires it silently.
            lines.append(
                instance(
                    f"X{tag}{i}",
                    sub,
                    cell,
                    {"Vdd": "vdd", "out": node, "in": "in", "Vss": "0"},
                )
            )
            lines.append(f"C{tag}{i} {node} 0 {load}f")
            control += [
                f"meas tran fall_{tag}{i} trig v(in) val={VDD / 2} rise=1 "
                f"targ v({node}) val={VDD / 2} fall=1",
                f"meas tran rise_{tag}{i} trig v(in) val={VDD / 2} fall=1 "
                f"targ v({node}) val={VDD / 2} rise=1",
            ]
    control.append(f"wrdata {WAVES.name} v(in) v(out_sch0) v(out_pex0)")
    control.append(".endc")
    lines += ["", "\n".join(control), ".end", ""]

    got = ngspice.run("\n".join(lines), WORKDIR)

    rows = []
    for i, load in enumerate(args.loads):
        row = {"load_ff": load}
        for edge in ("fall", "rise"):
            row[f"{edge}_sch_ps"] = got[f"{edge}_sch{i}"][0] * 1e12
            row[f"{edge}_pex_ps"] = got[f"{edge}_pex{i}"][0] * 1e12
            row[f"{edge}_penalty_pct"] = (
                100 * (row[f"{edge}_pex_ps"] - row[f"{edge}_sch_ps"]) / row[f"{edge}_sch_ps"]
            )
        rows.append(row)
        print(
            f"CL={load:>5g} fF   fall {row['fall_sch_ps']:6.1f} -> "
            f"{row['fall_pex_ps']:6.1f} ps ({row['fall_penalty_pct']:+5.1f}%)   "
            f"rise {row['rise_sch_ps']:6.1f} -> {row['rise_pex_ps']:6.1f} ps "
            f"({row['rise_penalty_pct']:+5.1f}%)"
        )

    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{args.out}\n{WAVES}")
    if args.plot:
        draw(rows, args.loads[0])


def draw_mc(spread: list[tuple[str, list[float]]]) -> None:
    """The distribution, and how well a run of this length pins its own width.

    matplotlib is imported here rather than at module scope so this file stays
    importable where it is not installed.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))

    for i, (label, draws) in enumerate(spread):
        mv = np.array(draws) * 1e3
        sigma = mv.std()
        ax1.hist(mv, bins=25, alpha=0.55, color=f"C{i}", label=f"{label}  sigma={sigma:.2f} mV")
        ax1.axvline(mv.mean(), color=f"C{i}", lw=1.2, ls="--")
        run = np.array([mv[: n + 1].std() for n in range(len(mv))])
        n = np.arange(1, len(mv) + 1)
        ax2.plot(n, run, color=f"C{i}", label=label)
        ax2.fill_between(
            n,
            sigma * (1 - 1 / np.sqrt(2 * n)),
            sigma * (1 + 1 / np.sqrt(2 * n)),
            color=f"C{i}",
            alpha=0.15,
        )

    ax1.set_xlabel("trip point (mV)")
    ax1.set_ylabel("draws")
    ax1.set_title("Distribution of Vm under device mismatch")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.3)

    ax2.set_xlabel("draws")
    ax2.set_ylabel("running sigma (mV)")
    ax2.set_title("How well a run of this length pins its own spread")
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(MC_PLOT, dpi=130)
    print(MC_PLOT)


def draw(rows: list[dict], smallest: float) -> None:
    """Delay against load, and the waveform pair at the lightest load.

    matplotlib is imported here rather than at module scope so this file stays
    importable where it is not installed.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))

    load = [r["load_ff"] for r in rows]
    for edge, style in (("fall", "-"), ("rise", "--")):
        ax1.plot(
            load, [r[f"{edge}_sch_ps"] for r in rows], style, color="C0", label=f"{edge} schematic"
        )
        ax1.plot(
            load, [r[f"{edge}_pex_ps"] for r in rows], style, color="C3", label=f"{edge} extracted"
        )
    ax1.set_xscale("log")
    ax1.set_xlabel("load capacitance (fF)")
    ax1.set_ylabel("propagation delay (ps)")
    ax1.set_title("Delay vs load")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.3)

    cols = np.loadtxt(WAVES)
    time, vin, vsch, vpex = cols[:, 0], cols[:, 1], cols[:, 3], cols[:, 5]

    # One edge, not the whole run: the shift under study is a few picoseconds
    # in a run of nanoseconds and is not visible at full scale.
    edge = int(np.argmax(vin > VDD / 2))
    lo, hi = time[edge] - WINDOW, time[edge] + WINDOW
    keep = (time >= lo) & (time <= hi)

    ax2.plot(time[keep] * 1e12, vin[keep], color="0.5", label="in")
    ax2.plot(time[keep] * 1e12, vsch[keep], color="C0", label="out schematic")
    ax2.plot(time[keep] * 1e12, vpex[keep], color="C3", label="out extracted")
    ax2.axhline(VDD / 2, color="0.7", lw=0.8, ls=":")
    ax2.set_xlabel("time (ps)")
    ax2.set_ylabel("volts")
    ax2.set_title(f"One falling edge at {smallest:g} fF")
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(PLOT, dpi=130)
    print(PLOT)


def cmd_sweep(args: argparse.Namespace) -> None:
    points = [
        Point(i, wn, wp, length)
        for i, (length, wn, wp) in enumerate(itertools.product(args.lengths, args.wn, args.wp))
    ]
    got = ngspice.run(deck(points, args.corner, False, vtc_control(points, args.temp)), WORKDIR)

    rows = []
    for p in points:
        rows.append(
            {
                "wn": p.wn,
                "wp": p.wp,
                "l": p.length,
                "ratio": p.wp / p.wn,
                "corner": args.corner,
                "temp": args.temp,
                "vm": got[f"vm{p.index}"][0],
                "gain_at_vm": got[f"gain{p.index}"][0],
                "peak_gain": got[f"peak{p.index}"][0],
            }
        )
        print(
            f"L={p.length:<5g} Wn={p.wn:<5g} Wp={p.wp:<5g} ratio={p.wp / p.wn:<5g} "
            f"vm={rows[-1]['vm']:.4f}  gain={rows[-1]['gain_at_vm']:.2f}"
        )

    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} points -> {args.out}")


def cmd_mc(args: argparse.Namespace) -> None:
    points = [Point(0, args.wn, args.wp, args.l)]
    if args.pelgrom > 1:
        points.append(Point(1, args.wn, args.wp, args.l, args.pelgrom))

    got = ngspice.run(deck(points, args.corner, True, mc_control(points, args.runs)), WORKDIR)

    sigmas = []
    spread = []
    with open(args.out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["wn", "wp", "l", "mult", "corner", "vm"])
        for p in points:
            draws = got[f"vm{p.index}"]
            if len(draws) != args.runs:
                raise ngspice.DeckError(f"asked for {args.runs} draws, deck returned {len(draws)}")
            sigmas.append(statistics.pstdev(draws))
            spread.append((f"Wn={p.wn:g} Wp={p.wp:g} mult={p.mult}", draws))
            print(
                f"Wn={p.wn:g} Wp={p.wp:g} ratio={p.wp / p.wn:g} L={p.length:g} "
                f"mult={p.mult}  n={len(draws)}  "
                f"mean={statistics.fmean(draws) * 1e3:.2f} mV  "
                f"sigma={sigmas[-1] * 1e3:.3f} mV"
            )
            for v in draws:
                writer.writerow([p.wn, p.wp, p.length, p.mult, args.corner, v])

    if len(sigmas) == 2:
        area = points[1].mult / points[0].mult
        print(f"\nsigma ratio {sigmas[0] / sigmas[1]:.3f}  (Pelgrom predicts {area**0.5:.3f})")
    print(f"draws -> {args.out}")
    if args.plot:
        draw_mc(spread)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser(
        "sweep",
        help="trip point and gain over Wp/Wn and L",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    s.add_argument("--wn", type=float, nargs="+", default=[1.0], help="NMOS widths to try, um")
    s.add_argument(
        "--wp",
        type=float,
        nargs="+",
        default=[1, 1.5, 2, 3, 4],
        help="PMOS widths to try, um",
    )
    s.add_argument(
        "--lengths",
        type=float,
        nargs="+",
        default=[0.15, 0.3, 0.5, 1.0],
        help="channel lengths to try, um, applied to both devices",
    )
    s.add_argument("--corner", default="tt", help="model library section")
    s.add_argument("--temp", type=float, default=NOMINAL_TEMP, help="degrees C")
    s.add_argument("--out", default=WORKDIR / "sweep.csv", help="one row per geometry")
    s.set_defaults(func=cmd_sweep)

    m = sub.add_parser(
        "mc",
        help="spread of the trip point under device mismatch",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    m.add_argument("--wn", type=float, default=1.0, help="NMOS width, um")
    m.add_argument("--wp", type=float, default=4.0, help="PMOS width, um")
    m.add_argument("--l", type=float, default=0.15, help="channel length, um")
    m.add_argument("--runs", type=int, default=200, help="draws per geometry")
    m.add_argument("--corner", default="tt", help="model library section")
    m.add_argument(
        "--pelgrom",
        type=int,
        default=1,
        help="also run with multiplicity scaled by this, to check sigma falls by its root",
    )
    m.add_argument("--plot", action="store_true", help="also draw a figure")
    m.add_argument("--out", default=WORKDIR / "mc_vm.csv", help="one row per draw")
    m.set_defaults(func=cmd_mc)

    x = sub.add_parser(
        "pex",
        help="delay of the drawn cell against the designed one",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    x.add_argument("--corner", default="tt", help="model library section")
    x.add_argument(
        "--loads",
        type=float,
        nargs="+",
        default=[1, 2, 5, 10, 20, 50],
        help="load capacitances to try, fF",
    )
    x.add_argument("--plot", action="store_true", help="also draw a figure")
    x.add_argument("--out", default=WORKDIR / "pex_delay.csv", help="one row per load")
    x.set_defaults(func=cmd_pex)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
