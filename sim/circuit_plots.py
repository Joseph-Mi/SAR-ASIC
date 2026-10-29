"""Draw the committed circuit measurements.

The same split the model's plots keep: this reads the artifact a run
committed rather than re-running the measurement, so a picture always shows
the numbers that are under review. Regenerating the artifact and then looking
at a picture of something else is the failure mode that buys.

It lives here rather than beside the model's plots because the artifacts it
reads are `sim`'s, and `studies` may not import `sim` -- the layers run one
way. The house style owns how any of it looks.
"""

from __future__ import annotations

import pathlib

import numpy as np

import house
from bench import Supplies
from interface import N_BITS
from offset import BASELINE, DRAWS, MILLIVOLT

OUT_DIR = pathlib.Path("build/sim")

#: Panel aspect, per panel.
PANEL = (6.2, 4.6)

#: Bins the spread is drawn with. Enough that a tail is visible at a hundred
#: draws and not so many that the shape is counting noise.
BINS = 24

#: How far past the data the panel reaches, as a fraction of its span, so the
#: sigma rules and their labels clear the frame.
HEADROOM = 0.12


def read_draws(path: pathlib.Path = DRAWS) -> dict[tuple[str, str], np.ndarray]:
    """Every draw, in millivolts, by the corner it came from.

    The file is long and thin -- one draw a line, tagged -- so this groups
    rather than reshapes, and a corner added to the study needs nothing here.
    """
    rows = [ln.split() for ln in path.read_text().splitlines() if not ln.startswith("#")]
    header, body = rows[0], rows[1:]
    at = {name: i for i, name in enumerate(header)}
    found: dict[tuple[str, str], list[float]] = {}
    for row in body:
        key = (row[at["corner"]], row[at["temp"]])
        found.setdefault(key, []).append(float(row[at["offset_mv"]]))
    return {k: np.array(v) for k, v in found.items()}


def read_summary(path: pathlib.Path = BASELINE) -> list[dict[str, str]]:
    """The committed summary table, as its own rows."""
    rows = [ln.split() for ln in path.read_text().splitlines() if not ln.startswith("#")]
    header, body = rows[0], rows[1:]
    return [dict(zip(header, row, strict=True)) for row in body]


def plot_offset(out_dir: pathlib.Path = OUT_DIR) -> pathlib.Path:
    """The comparator's offset, as the spread of parts it actually is.

    The number this figure exists to put next to the spread is one LSB. A
    StrongARM's offset is set by the mismatch of a pair that is deliberately
    small and fast, so it is tens of times the quantity the converter is
    trying to resolve -- which is not a defect to be sized away but the reason
    DFT mode 4 exists. A latch quiet enough to skip calibration would be a
    latch too slow to make a decision in the clock it is given.

    Drawn per corner because the offset moves with the corner, and that is
    what decides whether one factory trim is enough: it is not, and firmware
    measuring it in the field is.
    """
    drawn = read_draws()
    summary = {(r["corner"], r["temp"]): r for r in read_summary()}
    lsb = Supplies().vref / 2**N_BITS / MILLIVOLT

    fig, axes = house.canvas(1, len(drawn), size=PANEL)
    axes = np.atleast_1d(axes)
    for ax, ((corner, temp), values) in zip(axes.flat, sorted(drawn.items()), strict=True):
        row = summary[(corner, temp)]
        sigma, mean = values.std(ddof=1), values.mean()
        ax.hist(values, bins=BINS, color=house.SERIES[0])
        for k in (-1, 1):
            house.bound(
                ax,
                mean + k * sigma,
                f"+-sigma, {sigma:.2f} mV" if k > 0 else None,
                axis="x",
            )
        # One LSB, drawn from the mean so the comparison is a width against a
        # width rather than a position against a position.
        ax.axvspan(
            mean - lsb / 2,
            mean + lsb / 2,
            color=house.GOOD,
            alpha=house.SHADE_ALPHA,
            lw=0,
            label=f"one LSB, {lsb:.3f} mV",
        )
        ax.set_xlabel("comparator offset  [mV]")
        ax.set_ylabel(f"parts, of {values.size}")
        ax.set_title(f"{corner}, {row['supply'].rstrip('0').rstrip('.')} V, {temp} C")
        ax.legend(loc="upper right", fontsize=house.FONT_SMALL)
        house.note(
            ax,
            f"sigma {sigma / lsb:.1f} LSB\\nmean {mean / lsb:+.1f} LSB\\n"
            f"worst {float(np.abs(values).max()) / lsb:.1f} LSB",
        )
        span = values.max() - values.min()
        ax.set_xlim(values.min() - HEADROOM * span, values.max() + HEADROOM * span)

    fig.suptitle(
        f"StrongARM offset over {next(iter(drawn.values())).size} drawn parts, "
        f"per corner, at {N_BITS} bits\\n"
        "the spread is tens of LSB and it moves with the corner, so one "
        "factory trim cannot remove it --\\n"
        "which is what DFT mode 4 is for: firmware measures this in the "
        "field, on the part it is running on.",
    )
    fig.tight_layout()
    return house.save(fig, out_dir / "offset.png")


FIGURES = (plot_offset,)


def draw_all(out_dir: pathlib.Path = OUT_DIR) -> list[pathlib.Path]:
    return [figure(out_dir) for figure in FIGURES]


if __name__ == "__main__":
    for path in draw_all():
        print(path)
