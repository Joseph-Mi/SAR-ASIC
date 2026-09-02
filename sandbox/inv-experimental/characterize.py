"""Trip point, small-signal gain and mismatch of the experimental inverter.

Contract: the testbench must have been netlisted, and that netlist must still
define the cell as an instantiable subcircuit.

The netlist is read as a parts bin rather than run as a deck: the model library
and the cell come out of it, and the deck is built around them here. The
schematic is never rewritten, so a run that dies partway leaves no half-edited
cell behind, and the schematic stays the only thing that says what the circuit
is.

Every geometry under study is instantiated as its own subcircuit, sharing one
input source and read out on its own node, so a sweep of any size costs one
model library load.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tools import netlist, ngspice, sky130  # noqa: E402

HERE = pathlib.Path(__file__).parent
WORKDIR = HERE / "simulation"
NETLIST = WORKDIR / "tb_inv.spice"
CELL = "inv"

VDD = 1.8
CLOAD = "10f"
VIN_STEP = 0.005
NOMINAL_TEMP = 27


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
        return sky130.mosfet(
            self.wn if pull_down else self.wp, self.length, self.mult
        )


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


def cmd_sweep(args: argparse.Namespace) -> None:
    points = [
        Point(i, args.wn, args.wn * ratio, length)
        for i, (length, ratio) in enumerate(itertools.product(args.lengths, args.ratios))
    ]
    got = ngspice.run(
        deck(points, args.corner, False, vtc_control(points, args.temp)), WORKDIR
    )

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
            f"L={p.length:<5g} Wp/Wn={p.wp / p.wn:<5g} "
            f"vm={rows[-1]['vm']:.4f}  gain={rows[-1]['gain_at_vm']:.2f}"
        )

    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} points -> {args.out}")


def cmd_mc(args: argparse.Namespace) -> None:
    # The second leg scales multiplicity, not width or length. All three raise
    # area by the same factor, but width and length also move the trip point,
    # and a spread measured at a different trip point is a different
    # measurement. Replicating the device leaves current density and every bias
    # untouched, which is what isolates area from everything else.
    points = [Point(0, args.wn, args.wn * args.ratio, args.l)]
    if args.pelgrom > 1:
        points.append(Point(1, args.wn, args.wn * args.ratio, args.l, int(args.pelgrom)))

    got = ngspice.run(
        deck(points, args.corner, True, mc_control(points, args.runs)), WORKDIR
    )

    sigmas = []
    with open(args.out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["wn", "wp", "l", "mult", "corner", "vm"])
        for p in points:
            draws = got[f"vm{p.index}"]
            if len(draws) != args.runs:
                raise ngspice.DeckError(
                    f"asked for {args.runs} draws, deck returned {len(draws)}"
                )
            sigmas.append(statistics.pstdev(draws))
            print(
                f"Wn={p.wn:g} Wp={p.wp:g} L={p.length:g} mult={p.mult}  n={len(draws)}  "
                f"mean={statistics.fmean(draws) * 1e3:.2f} mV  "
                f"sigma={sigmas[-1] * 1e3:.3f} mV"
            )
            for v in draws:
                writer.writerow([p.wn, p.wp, p.length, p.mult, args.corner, v])

    if len(sigmas) == 2:
        print(
            f"\nsigma ratio {sigmas[0] / sigmas[1]:.3f}  "
            f"(Pelgrom predicts {args.pelgrom ** 0.5:.3f})"
        )
    print(f"draws -> {args.out}")


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
    s.add_argument("--wn", type=float, default=1.0, help="NMOS width, um")
    s.add_argument(
        "--ratios", type=float, nargs="+", default=[1, 1.5, 2, 3, 4],
        help="PMOS widths to try, as multiples of --wn",
    )
    s.add_argument(
        "--lengths", type=float, nargs="+", default=[0.15, 0.3, 0.5, 1.0],
        help="channel lengths to try, um, both devices",
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
    m.add_argument("--ratio", type=float, default=4.0, help="PMOS width / NMOS width")
    m.add_argument("--l", type=float, default=0.15, help="channel length, um")
    m.add_argument("--runs", type=int, default=200, help="draws per geometry")
    m.add_argument("--corner", default="tt", help="model library section")
    m.add_argument(
        "--pelgrom",
        type=float,
        default=1.0,
        help="also run with multiplicity scaled by this, to check sigma falls by its root",
    )
    m.add_argument("--out", default=WORKDIR / "mc_vm.csv", help="one row per draw")
    m.set_defaults(func=cmd_mc)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
