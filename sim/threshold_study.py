"""Where the designed block's code transitions actually sit, at each corner.

The corner acceptance answers "are the codes right", which is the right
question for a gate and the wrong one for a diagnosis: when a code is wrong it
cannot say by how much, and when every code is right it cannot say how nearly
they were not. This locates the transitions themselves, by bisecting the real
controller running the real block, so the error has a magnitude and a shape.

It exists because a finding was built on a proxy and the proxy was wrong.
`measure.first_trial_error` reads the top plate at the *first* trial, where
the plate's excursion scales with the input -- so its error varies strongly
across the range and looks like a gain error of about 0.7 LSB. A threshold is
decided by the *last* trials, where the plate has converged to within an LSB
of Vcm, and there the error is nearly constant: measured end to end it moves
0.094 LSB, of which 0.055 survives a one-point calibration. The proxy
measures a real quantity that is not the one deciding codes, and reading it as
though it were cost this project a wrong diagnosis and two wrong fixes.

Expensive: every bisection round is a batch of closed-loop conversions with
transistor switches and the controller compiled into the deck. It is a
committed artifact for that reason, and `make thresholds` regenerates it.
"""

from __future__ import annotations

import argparse
import math
import pathlib

import cosim
import loop
from bench import SKY130_CORNERS, Block, at_corner
from interface import N_BITS
from measure import law_clock
from sar import ideal_units, sar_convert
from sweep import EDGE_OFFSET_LSB, VREF, lsb

REPO = next(p for p in pathlib.Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
CONTROLLER = REPO / "hdl" / "rtl" / "sar_fsm.v"
BASELINE = pathlib.Path(__file__).with_name("threshold_baseline.txt")

#: How far either side of the model's threshold the search starts, in LSB.
#: Wider than the short loop's bench uses, because the offset at the slow
#: corner is about half an LSB on its own and a window that does not bracket
#: the answer reports its own edge, which reads exactly like a measurement.
WINDOW = 1.0

#: How finely it ends, in LSB. The floor under everything here: a claim finer
#: than this is reading the grid rather than the circuit.
RESOLUTION = 0.0125

#: The transitions located. Spread over the range rather than exhaustive --
#: every one of the 1023 would be a thousand conversions a round -- and
#: weighted to the ends, where a gain error would show if there were one.
CODES = (1, 64, 128, 256, 512, 768, 896, 1000, 1023)

COLUMNS = ("corner", "vdd", "temp", "caps", "code", "loop_lsb", "model_lsb", "error_lsb")


def locate(
    workdir: pathlib.Path,
    block: Block,
    library,
    clock: float,
    codes=CODES,
    n_bits: int = N_BITS,
) -> dict[int, float]:
    """Where each of `codes` transitions, in LSB, for this block.

    All of them are bisected at once, one batch of conversions per round
    rather than per threshold: what this costs is ngspice runs, and advancing
    every search together makes that the number of rounds instead of their
    product.
    """
    step = lsb(n_bits, VREF)
    low = {k: (k - WINDOW) * step for k in codes}
    high = {k: (k + WINDOW) * step for k in codes}
    for _ in range(math.ceil(math.log2(2 * WINDOW / RESOLUTION))):
        mid = {k: (low[k] + high[k]) / 2 for k in codes}
        got = loop.convert([mid[k] for k in codes], library, workdir, block, clock)
        for k, code in zip(codes, got.codes, strict=True):
            # At or above the code means the transition is at or below here.
            if code >= k:
                high[k] = mid[k]
            else:
                low[k] = mid[k]
    return {k: (low[k] + high[k]) / 2 / step for k in codes}


def model_threshold(k: int, n_bits: int = N_BITS) -> float:
    """Where the model puts the same transition, read the way the loop's is."""
    step = lsb(n_bits, VREF)
    units = ideal_units(n_bits)
    fine = RESOLUTION / 10
    points = int(2 * WINDOW / fine) + 1
    return next(
        k + (-WINDOW + i * fine)
        for i in range(points)
        if sar_convert((k + (-WINDOW + i * fine)) * step, units, VREF)[0] >= k
    )


def sweep(workdir: pathlib.Path, library, corners=SKY130_CORNERS) -> list[dict]:
    rows = []
    for corner in corners:
        block = at_corner(corner)
        clock = law_clock(workdir, block, EDGE_OFFSET_LSB * lsb(N_BITS, VREF))
        found = locate(workdir, block, library, clock)
        for k in CODES:
            rows.append(
                {
                    "corner": corner.process,
                    "vdd": corner.vdd,
                    "temp": corner.temp,
                    "caps": corner.caps,
                    "code": k,
                    "loop_lsb": found[k],
                    "model_lsb": model_threshold(k),
                    "error_lsb": found[k] - model_threshold(k),
                }
            )
        print(f"  {corner}: located {len(CODES)} thresholds at {clock * 1e9:.2f} ns", flush=True)
    return rows


def residual_after_offset(rows: list[dict], corner: str, caps: str) -> float:
    """What a one-point calibration at mid-scale leaves, in LSB.

    The quantity the acceptance's half-LSB criterion has to clear, and the
    one the record got wrong: it is the *spread* of the errors and not the
    errors themselves, because an offset common to every threshold is what
    the calibration removes.
    """
    here = [r for r in rows if r["corner"] == corner and r["caps"] == caps]
    mid = next(r["error_lsb"] for r in here if r["code"] == 2 ** (N_BITS - 1))
    return max(abs(r["error_lsb"] - mid) for r in here)


def format_table(rows: list[dict]) -> str:
    """Fixed-width and fixed-precision, because this file is diffed."""
    widths = {c: max(len(c), len("-0.000000")) for c in COLUMNS}
    out = [
        f"# bits={N_BITS} window={WINDOW} resolution={RESOLUTION} clock=law_clock per corner",
        "  ".join(c.rjust(widths[c]) for c in COLUMNS),
    ]
    for r in rows:
        cells = []
        for c in COLUMNS:
            v = r[c]
            cell = v if isinstance(v, str) else f"{v:d}" if isinstance(v, int) else f"{v:.6f}"
            cells.append(cell.rjust(widths[c]))
        out.append("  ".join(cells))
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=pathlib.Path, default=pathlib.Path("build/thresholds"))
    parser.add_argument("--out", type=pathlib.Path, default=BASELINE)
    args = parser.parse_args()

    args.work.mkdir(parents=True, exist_ok=True)
    library = cosim.build(CONTROLLER, args.work / "rtl", {"N_BITS": N_BITS})
    rows = sweep(args.work, library)
    table = format_table(rows)
    args.out.write_text(table)
    print(table, end="")
    for corner in SKY130_CORNERS:
        left = residual_after_offset(rows, corner.process, corner.caps)
        print(f"{corner.process}/{corner.caps}: {left:.4f} LSB survives a one-point calibration")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
