"""Draw the committed sweeps.

Reads the committed artifact rather than re-running the study, so a plot always
shows exactly the numbers under review. Regenerating the artifact and then
looking at a picture of something else is the failure mode this avoids.

matplotlib is imported inside the drawing function. CI installs only the pinned
Python dependencies and matplotlib is not among them, so importing it at module
scope would make this file un-importable there for no benefit.
"""

from __future__ import annotations

import pathlib

import numpy as np

import sky130
from mismatch import (
    PERCENT,
    area_for_sigma,
    sigma_from_area,
)
from noise_study import BASELINE as NOISE_BASELINE
from noise_study import GROSS_ERROR_ONSET_LSB
from yield_study import BASELINE

OUT_DIR = pathlib.Path("build/studies")

# How the figures look. None of it carries a result.
FONT_SMALL, FONT_LABEL, FONT_TITLE = 8, 9, 11
LINE_THIN, LINE_RULE = 0.6, 0.8
GRID_ALPHA, SHADE_ALPHA = 0.3, 0.12
DPI = 140
YIELD_FIGSIZE = (11, 8)
NOISE_FIGSIZE = (14, 4.4)

# The x range is widened this far around the buildable limit so the limit
# line never sits on the frame.
LIMIT_MARGIN = (0.6, 1.4)

# Where the "none seen" note sits: this far into the axes, and this far above
# the floor line it labels.
NOTE_X, NOTE_LIFT = 0.02, 1.3

# A top-axis tick is dropped when it lands closer than this fraction of the
# axis to one already kept.
TICK_GAP = 0.06

# Log transforms of the sigma/area axes are clamped here so a zero stays finite.
LOG_FLOOR = 1e-9

# Round areas that fall inside the swept sigma range, chosen for legibility
# rather than by any rule -- this axis is read to size a capacitor, not to
# interpolate.
AREA_TICKS = (0.02, 0.1, 0.5, 2, 10, 50)

# What each panel plots, and whether it needs a log axis. Yield spans decades
# and is read near zero; the rest are read across their whole range.
PANELS = (
    ("sigma_dnl_msb", "sigma(DNL) at MSB transition  [LSB]", False),
    ("p_missing", "P(missing code)", True),
    ("max_inl", "mean worst |INL|  [LSB]", False),
    ("enob", "effective bits", False),
)


def read_table(path: pathlib.Path = BASELINE) -> tuple[dict, list[dict]]:
    """Parse the artifact back into rows. The header comment carries the run."""
    lines = path.read_text().splitlines()
    header = dict(kv.split("=") for kv in lines[0].lstrip("# ").split())
    columns = lines[1].split()
    rows = []
    for line in lines[2:]:
        values = [float(v) for v in line.split()]
        row = dict(zip(columns, values, strict=True))
        row["n_bits"] = int(row["n_bits"])
        rows.append(row)
    return header, rows


def plot(path: pathlib.Path = BASELINE, out_dir: pathlib.Path = OUT_DIR):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    header, rows = read_table(path)
    trials = int(header["trials"])
    floor = 1.0 / trials
    resolutions = sorted({r["n_bits"] for r in rows})

    # The sweep runs in matching, but area is what gets drawn, and the process
    # will not draw one below a minimum. Everything to the left of this is
    # reachable; everything to the right asks for a device that cannot be made.
    min_area = min(sky130.CAP_MIN_AREA_MIM, sky130.CAP_MIN_AREA_VPP)
    buildable = sigma_from_area(min_area, sky130.CAP_A_C) * PERCENT

    fig, axes = plt.subplots(2, 2, figsize=YIELD_FIGSIZE)
    for ax, (column, label, log) in zip(axes.flat, PANELS, strict=True):
        for n_bits in resolutions:
            picked = [r for r in rows if r["n_bits"] == n_bits]
            x = np.array([r["sigma_rel"] for r in picked]) * PERCENT
            y = np.array([r[column] for r in picked])
            if log:
                # Zero observations are an upper bound, not a zero: nothing was
                # seen in `trials` draws. Drawn at the detection floor, hollow,
                # so they are not read as measurements.
                seen = y > 0
                ax.semilogy(x[seen], y[seen], "o-", label=f"{n_bits} bits")
                ax.semilogy(
                    x[~seen],
                    np.full((~seen).sum(), floor),
                    "o",
                    mfc="none",
                    color=ax.lines[-1].get_color(),
                )
            else:
                ax.plot(x, y, "o-", label=f"{n_bits} bits")

        if column == "sigma_dnl_msb":
            for n_bits in resolutions:
                picked = [r for r in rows if r["n_bits"] == n_bits]
                x = np.array([r["sigma_rel"] for r in picked]) * PERCENT
                ax.plot(
                    x,
                    [r["analytic"] for r in picked],
                    "k--",
                    lw=LINE_RULE,
                    label="sqrt(2^N-1)*sigma" if n_bits == resolutions[0] else None,
                )
        if log:
            ax.axhline(floor, color="grey", lw=LINE_THIN, ls=":")
            ax.annotate(
                f"none seen in {trials} trials",
                (NOTE_X, floor * NOTE_LIFT),
                xycoords=("axes fraction", "data"),
                fontsize=FONT_SMALL,
                color="grey",
            )

        lo0, hi0 = ax.get_xlim()
        ax.set_xlim(
            left=min(lo0, buildable * LIMIT_MARGIN[0]), right=max(hi0, buildable * LIMIT_MARGIN[1])
        )
        ax.axvspan(buildable, ax.get_xlim()[1], color="grey", alpha=SHADE_ALPHA, lw=0)
        ax.axvline(buildable, color="grey", lw=LINE_RULE, ls="--")

        # Matching is the axis the physics depends on; area is one way to buy
        # it. Shown as a second scale rather than as the variable, so a revised
        # A_C relabels this plot instead of invalidating it.
        top = ax.secondary_xaxis(
            "top",
            functions=(
                lambda pct: area_for_sigma(np.maximum(pct, LOG_FLOOR) / PERCENT, sky130.CAP_A_C),
                lambda area: sigma_from_area(np.maximum(area, LOG_FLOOR), sky130.CAP_A_C) * PERCENT,
            ),
        )
        # Ticks are placed in area, not inherited from the sigma axis: area
        # goes as 1/sigma^2, so transformed sigma ticks bunch into an
        # unreadable smear at the low-sigma end. For the same reason only the
        # ticks that stay legibly apart on this range are kept.
        lo, hi = ax.get_xlim()
        keep: list[tuple[float, float]] = []
        for a in AREA_TICKS:
            at = sigma_from_area(a, sky130.CAP_A_C) * PERCENT
            if lo <= at <= hi and all(abs(at - s) > (hi - lo) * TICK_GAP for _, s in keep):
                keep.append((a, at))
        top.set_xticks([a for a, _ in keep])
        top.set_xticklabels([f"{a:g}" for a, _ in keep], fontsize=FONT_SMALL)
        top.set_xlabel("unit capacitor area  [um^2]", fontsize=FONT_LABEL)
        ax.set_xlabel("unit capacitor matching  sigma_u/C_u  [%]")
        ax.set_ylabel(label)
        ax.grid(alpha=GRID_ALPHA)
        ax.legend(fontsize=FONT_SMALL)

    fig.suptitle(
        f"Binary-weighted SAR: mismatch vs linearity, yield and resolution "
        f"({trials} arrays per point)\n"
        f"top axis: unit area at A_C = {sky130.CAP_A_C} %*um. Matching is set by "
        f"area alone, so the flavour changes the capacitance in it, not the axis.\n"
        f"shaded: needs a unit smaller than the process will draw "
        f"({min_area} um^2), so the array is limited by geometry, not matching.",
        fontsize=FONT_TITLE,
    )
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "yield.png"
    fig.savefig(target, dpi=DPI)
    return target


def plot_noise(path: pathlib.Path = NOISE_BASELINE, out_dir: pathlib.Path = OUT_DIR):
    """What the comparator has to be, for each resolution worth considering."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    header, rows = read_table(path)
    resolutions = sorted({r["n_bits"] for r in rows})
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=NOISE_FIGSIZE)

    for n_bits in resolutions:
        picked = [r for r in rows if r["n_bits"] == n_bits]
        x = [r["noise_lsb"] for r in picked]
        ax1.plot(x, [r["n_bits"] - r["enob_rms"] for r in picked], "o-", label=f"{n_bits} bits")
        # Same convention as the mismatch figure: a point where nothing was
        # seen is an upper bound, not a zero, and is drawn hollow at the floor.
        gross = np.array([r["p_gross"] for r in picked])
        floor = 1.0 / float(header["conversions"])
        seen = gross > 0
        ax2.semilogy(np.array(x)[seen], gross[seen], "o-", label=f"{n_bits} bits")
        ax2.semilogy(
            np.array(x)[~seen],
            np.full((~seen).sum(), floor),
            "o",
            mfc="none",
            color=ax2.lines[-1].get_color(),
        )
        ax3.semilogy(x[1:], [r["noise_uv"] for r in picked[1:]], "o-", label=f"{n_bits} bits")

    # The three curves land on top of each other, which is the result: measured
    # against its own LSB, a comparator costs the same wherever it is used.
    ax1.set_xlabel("comparator noise  [LSB rms]")
    ax1.set_ylabel("bits lost")
    ax1.set_title("Cost is the same at every resolution")

    ax2.axvline(GROSS_ERROR_ONSET_LSB, color="grey", lw=LINE_RULE, ls="--")
    ax2.axhline(1.0 / float(header["conversions"]), color="grey", lw=LINE_THIN, ls=":")
    ax2.set_xlabel("comparator noise  [LSB rms]")
    ax2.set_ylabel("P(missed by more than one code)")
    ax2.set_title("Where a wrong early bit starts costing 2^k")

    # The same fraction of an LSB, priced in volts. This is the axis a
    # comparator is designed against, and the only one resolution moves.
    ax3.set_xlabel("comparator noise  [LSB rms]")
    ax3.set_ylabel("the same noise, in microvolts")
    ax3.set_title("What that costs in volts")

    for ax in (ax1, ax2, ax3):
        ax.grid(alpha=GRID_ALPHA)
        ax.legend(fontsize=FONT_SMALL)

    fig.suptitle(
        f"Comparator noise against resolution ({header['conversions']} conversions per point)\n"
        f"degradation tracks the LSB, so resolution is bought in comparator volts",
        fontsize=FONT_TITLE,
    )
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "noise.png"
    fig.savefig(target, dpi=DPI)
    return target


if __name__ == "__main__":
    print(plot())
    print(plot_noise())
