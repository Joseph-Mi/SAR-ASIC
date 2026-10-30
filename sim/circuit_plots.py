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
from corner_study import BASELINE as CORNERS
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

#: The reference's series resistance when the board decouples it at the pin.
#: The row carrying it is the control, not a corner.
DECOUPLED = 0.0


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
            f"sigma {sigma / lsb:.1f} LSB\nmean {mean / lsb:+.1f} LSB\n"
            f"worst {float(np.abs(values).max()) / lsb:.1f} LSB",
        )
        span = values.max() - values.min()
        ax.set_xlim(values.min() - HEADROOM * span, values.max() + HEADROOM * span)

    fig.suptitle(
        f"StrongARM offset over {next(iter(drawn.values())).size} drawn parts, "
        f"per corner, at {N_BITS} bits\n"
        "the spread is tens of LSB and it moves with the corner, so one "
        "factory trim cannot remove it --\n"
        "which is what DFT mode 4 is for: firmware measures this in the "
        "field, on the part it is running on.",
    )
    fig.tight_layout()
    return house.save(fig, out_dir / "offset.png")


def read_corners(path: pathlib.Path = CORNERS) -> list[dict]:
    """The committed corner table, each cell already a number where it is one."""
    rows = [ln.split() for ln in path.read_text().splitlines() if not ln.startswith("#")]
    header, body = rows[0], rows[1:]
    out = []
    for row in body:
        r = dict(zip(header, row, strict=True))
        out.append({k: v if k in ("corner", "caps") else float(v) for k, v in r.items()})
    return out


def plot_corners(out_dir: pathlib.Path = OUT_DIR) -> pathlib.Path:
    """What the corner acceptance measures, and what the one failure is.

    The acceptance is a gate, so it answers yes or no. These are the numbers
    behind the answer: how much array each corner builds, how slow that makes
    the sampling loop, and how many codes come out wrong at the one clock
    every corner shares -- the clock the slowest corner's *sampling* loop
    asks for.

    The right panel is the part a gate cannot say. The corner that fails
    comes right by lengthening the clock, which would read as ordinary
    settling margin, except that it also comes right at the original clock
    with the reference's pin taken out and nothing else changed. A margin
    does not care which resistor you remove. That is what makes this the
    reference pin rather than the sampling loop, and `law_clock` only knows
    about the second one.
    """
    rows = read_corners()
    corners = [r for r in rows if r["mult"] == 1.0 and r["r_vref"] != DECOUPLED]
    swept = sorted(
        [r for r in rows if r["r_vref"] != DECOUPLED and (r["mult"] > 1.0 or r in corners[:0])]
        + [r for r in corners if r["caps"] == "high"],
        key=lambda r: r["mult"],
    )
    decoupled = next(r for r in rows if r["r_vref"] == DECOUPLED)

    fig, (sizes, sweep) = house.canvas(1, 2, size=PANEL)

    labels = [f"{r['corner']}\n{r['vdd']:g} V {r['temp']:g} C\n{r['caps']} C" for r in corners]
    x = np.arange(len(corners))
    bars = sizes.bar(x, [r["tau_ns"] for r in corners], color=house.SERIES[0])
    for bar, r in zip(bars, corners, strict=True):
        if r["wrong"]:
            bar.set_color(house.BAD)
        sizes.annotate(
            f"{r['ctot_pf']:.2f} pF\n{int(r['wrong'])}/{int(r['of'])} wrong",
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            textcoords="offset points",
            xytext=(0, 4),
            ha="center",
            fontsize=house.FONT_SMALL,
            color=house.BAD if r["wrong"] else house.INK_SOFT,
        )
    sizes.set_xticks(x)
    sizes.set_xticklabels(labels, fontsize=house.FONT_SMALL)
    sizes.set_ylabel("sampling loop tau  [ns]")
    sizes.margins(y=0.25)
    sizes.set_title("Each corner builds a different array, so each samples at its own speed")
    house.note(
        sizes,
        f"one clock for all five, {corners[0]['own_clock_ns']:.0f} ns, from the "
        f"slowest\nthe array spans {min(r['ctot_pf'] for r in corners):.2f} to "
        f"{max(r['ctot_pf'] for r in corners):.2f} pF across the capacitance corners",
    )

    sweep.step(
        [r["mult"] for r in swept],
        [r["wrong"] for r in swept],
        where="post",
        color=house.SERIES[0],
        lw=house.LINE,
        label="the failing corner, clock lengthened",
    )
    sweep.plot(
        [r["mult"] for r in swept],
        [r["wrong"] for r in swept],
        "o",
        color=house.SERIES[0],
    )
    sweep.plot(
        [decoupled["mult"]],
        [decoupled["wrong"]],
        "*",
        markersize=16,
        color=house.GOOD,
        label="same clock, reference at the array (r_vref = 0)",
    )
    sweep.set_xlabel("clock, as a multiple of the one sampling asks for")
    sweep.set_ylabel(f"codes wrong, of {int(swept[0]['of'])}")
    sweep.set_ylim(-0.3, max(r["wrong"] for r in swept) + 0.7)
    sweep.legend(loc="upper right", fontsize=house.FONT_SMALL)
    sweep.set_title("The one failure, and the two things that remove it")
    house.note(
        sweep,
        "lengthening the clock fixes it -- which looks like settling margin.\n"
        "removing the reference's pin fixes it at the original clock, which\n"
        "margin cannot do. the binding path is the reference, not sampling.",
        (0.02, 0.60),
    )

    fig.suptitle(
        "The corner acceptance, measured rather than asserted: sky130 "
        "devices and array, the real controller,\n"
        "behind the platform's 500 ohm pins -- "
        f"{int(swept[0]['of'])} mid-code inputs either side of every carry.",
    )
    fig.tight_layout()
    return house.save(fig, out_dir / "corners.png")


FIGURES = (plot_offset, plot_corners)


def draw_all(out_dir: pathlib.Path = OUT_DIR) -> list[pathlib.Path]:
    return [figure(out_dir) for figure in FIGURES]


if __name__ == "__main__":
    for path in draw_all():
        print(path)
