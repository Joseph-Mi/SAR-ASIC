"""The spread of the designed latch's offset across parts.

One part's offset is measured by `strongarm.offset`; this draws a population of
them and reports what the spread is. A constant offset moves no code relative
to its neighbour, so what this answers is not whether the latch fits a budget
but how much calibration has to be able to remove, and how far the parts at the
edge of a wafer sit from the ones in the middle.

Contract: a draw's seed depends on the study's seed, the corner and the draw's
own number -- never on its position in a list -- so adding draws or reordering
corners leaves every other draw's part exactly as it was, and the table written
twice is byte-identical. Each draw is one simulated part, because the simulator
re-seeds on every redraw: a seeded run of many draws would be one part measured
many times, reporting a spread of zero.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import pathlib
import zlib
from dataclasses import dataclass, field

import numpy as np

import strongarm
from bench import NOMINAL_TEMP, SKY130_CORNERS, Supplies
from devices import Sky130
from interface import N_BITS
from sar import VCM_FRACTION

BASELINE = pathlib.Path(__file__).with_name("offset_baseline.txt")

#: Every draw, beside the table that summarises them. The table is what the
#: regression compares and is the smaller diff, so it stays; this is what a
#: histogram needs, and a spread has a shape that three numbers cannot carry
#: -- whether it is Gaussian, whether it is centred, whether the worst part
#: is a tail or an outlier. Written by the same run as the table, so the two
#: cannot describe different populations, and held to each other by a test.
DRAWS = pathlib.Path(__file__).with_name("offset_draws.txt")

#: Volts per millivolt, for the columns an offset is readable in.
MILLIVOLT = 1e-3

#: The largest seed the simulator is given. Its own range is wider; this keeps
#: every derived seed inside a signed 32-bit integer whatever derives it.
SEED_LIMIT = 2**31 - 2

#: The corners the spread is measured at: nominal, and the hottest fast one --
#: where the noise budget already leaves the least room, so it is where a
#: static error has the least left to spend.
CORNERS = (
    next(c for c in SKY130_CORNERS if c[0] == "tt" and c[2] == NOMINAL_TEMP),
    max((c for c in SKY130_CORNERS if c[0] == "ff"), key=lambda corner: corner[2]),
)

#: The strobe every pass is taken with. It is part of the answer and not a
#: setting: a strobe too short to finish regenerating moves the crossing by
#: tens of millivolts, because what displaces it is then which output got
#: ahead rather than where the circuit ties. Held at the order the
#: conversion's own evaluate phase allows.
STROBE = 200e-9


def seed_for(seed: int, corner, draw: int) -> int:
    """The part a draw simulates, from what the draw *is* and not where it sits."""
    key = f"{seed}:{corner[0]}:{corner[1]:.6g}:{corner[2]:.6g}:{draw}".encode()
    return zlib.crc32(key) % SEED_LIMIT + 1


@dataclass(frozen=True)
class OffsetStudy:
    draws: int = 100
    seed: int = 20261026
    corners: tuple = CORNERS
    columns: tuple[str, ...] = field(
        default_factory=lambda: (
            "corner",
            "supply",
            "temp",
            "draws",
            "mean_mv",
            "sigma_mv",
            "worst_mv",
            "sigma_lsb",
        )
    )


def one_draw(base: pathlib.Path, corner, seed: int) -> float:
    """One part's offset, in its own directory so draws may run at once."""
    # Three of the corner's four axes: the latch is a comparator across a pair
    # of nodes and does not touch the array, so its capacitance corner is not
    # one of its own.
    process, supply, temp = corner.process, corner.vdd, corner.temp
    workdir = base / f"{process}_{temp:g}_{seed}"
    workdir.mkdir(parents=True, exist_ok=True)
    return strongarm.offset(
        workdir,
        strongarm.DESIGNED,
        Sky130(process),
        strongarm.Drive(supply, STROBE, temp, Supplies().vref),
        VCM_FRACTION * Supplies().vref,
        seed,
    )


def population(study: OffsetStudy, base: pathlib.Path, corner, workers: int) -> np.ndarray:
    """Every draw's offset at one corner, volts.

    The draws are independent parts and each simulation is its own process, so
    they are run together; the scratch deck each one writes is named for the
    process holding it, which is what makes that safe.
    """
    seeds = [seed_for(study.seed, corner, draw) for draw in range(study.draws)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        return np.array(list(pool.map(lambda seed: one_draw(base, corner, seed), seeds)))


def run_point(study: OffsetStudy, base: pathlib.Path, corner, workers: int) -> tuple:
    """The summary row for one corner, and the draws it was taken over."""
    drawn = population(study, base, corner, workers)
    lsb = Supplies().vref / 2**N_BITS
    return {
        "corner": corner[0],
        "supply": corner[1],
        "temp": corner[2],
        "draws": int(drawn.size),
        "mean_mv": float(drawn.mean()) / MILLIVOLT,
        "sigma_mv": float(drawn.std(ddof=1)) / MILLIVOLT,
        "worst_mv": float(np.abs(drawn).max()) / MILLIVOLT,
        "sigma_lsb": float(drawn.std(ddof=1)) / lsb,
    }, drawn


def format_table(study: OffsetStudy, rows: list[dict]) -> str:
    """Fixed-width and fixed-precision, because this file is diffed.

    The widths come from the columns themselves rather than from a shared
    figure: this table's numbers are its own, and a width chosen for another
    table's would be a value restated in two places.
    """
    widths = {c: max(len(c), len("-0.000000")) for c in study.columns}
    out = [
        f"# draws={study.draws} seed={study.seed} strobe={STROBE:g} sizing=DESIGNED",
        "  ".join(c.rjust(widths[c]) for c in study.columns),
    ]
    for row in rows:
        cells = []
        for c in study.columns:
            value = row[c]
            if isinstance(value, str):
                cell = value
            elif isinstance(value, int):
                cell = f"{value:d}"
            else:
                cell = f"{value:.6f}"
            cells.append(cell.rjust(widths[c]))
        out.append("  ".join(cells))
    return "\n".join(out) + "\n"


def format_draws(study: OffsetStudy, rows: list[dict], drawn: list) -> str:
    """Every draw, one per line, tagged by the corner it came from.

    Long and thin rather than a column per corner, so a corner added or
    dropped is a block of lines rather than a reshaped file, and so a reader
    does not have to count columns to know which corner a number is.
    """
    out = [
        f"# draws={study.draws} seed={study.seed} strobe={STROBE:g} sizing=DESIGNED",
        f"# every draw in millivolts; the summary of these is {BASELINE.name}",
        "  ".join(c.rjust(len("-0.000000")) for c in ("corner", "temp", "draw", "offset_mv")),
    ]
    for row, values in zip(rows, drawn, strict=True):
        for i, volts in enumerate(values):
            cells = (row["corner"], f"{row['temp']:g}", f"{i:d}", f"{volts / MILLIVOLT:.6f}")
            out.append("  ".join(c.rjust(len("-0.000000")) for c in cells))
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--draws", type=int, default=OffsetStudy.draws)
    parser.add_argument("--seed", type=int, default=OffsetStudy.seed)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--work", type=pathlib.Path, default=pathlib.Path("build/offset"))
    parser.add_argument("--out", type=pathlib.Path, default=BASELINE)
    args = parser.parse_args()

    study = OffsetStudy(draws=args.draws, seed=args.seed)
    if (study.draws, study.seed) != (OffsetStudy.draws, OffsetStudy.seed) and args.out == BASELINE:
        parser.error(
            f"refusing to write {BASELINE.name} from a non-default study -- the "
            "committed baseline is what the regression test compares against. "
            "Pass --out to write an exploratory run somewhere else."
        )

    args.work.mkdir(parents=True, exist_ok=True)
    measured = [run_point(study, args.work, corner, args.workers) for corner in study.corners]
    rows = [row for row, _ in measured]
    drawn = [values for _, values in measured]
    table = format_table(study, rows)
    args.out.write_text(table)
    # The draws go beside whatever the table went beside, so an exploratory
    # run cannot leave its draws next to the committed summary.
    draws_out = args.out.with_name(args.out.stem.replace("baseline", "draws") + args.out.suffix)
    if draws_out == args.out:
        draws_out = args.out.with_name(args.out.stem + "_draws" + args.out.suffix)
    draws_out.write_text(format_draws(study, rows, drawn))
    print(table, end="")
    print(f"-> {args.out}")
    print(f"-> {draws_out}")


if __name__ == "__main__":
    main()
