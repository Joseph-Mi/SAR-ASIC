"""Draw the committed sweep.

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

from mismatch import (
    SKY130_CAP_A_C,
    SKY130_CAP_MIN_AREA_MIM,
    SKY130_CAP_MIN_AREA_VPP,
    area_for_sigma,
    sigma_from_area,
)
from yield_study import BASELINE

OUT_DIR = pathlib.Path("build/model")

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
    min_area = min(SKY130_CAP_MIN_AREA_MIM, SKY130_CAP_MIN_AREA_VPP)
    buildable = sigma_from_area(min_area, SKY130_CAP_A_C) * 100

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    for ax, (column, label, log) in zip(axes.flat, PANELS, strict=True):
        for n_bits in resolutions:
            picked = [r for r in rows if r["n_bits"] == n_bits]
            x = np.array([r["sigma_rel"] for r in picked]) * 100
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
                x = np.array([r["sigma_rel"] for r in picked]) * 100
                ax.plot(
                    x,
                    [r["analytic"] for r in picked],
                    "k--",
                    lw=0.8,
                    label="sqrt(2^N-1)*sigma" if n_bits == resolutions[0] else None,
                )
        if log:
            ax.axhline(floor, color="grey", lw=0.6, ls=":")
            ax.annotate(
                f"none seen in {trials} trials",
                (0.02, floor * 1.3),
                xycoords=("axes fraction", "data"),
                fontsize=8,
                color="grey",
            )

        lo0, hi0 = ax.get_xlim()
        ax.set_xlim(left=min(lo0, buildable * 0.6), right=max(hi0, buildable * 1.4))
        ax.axvspan(buildable, ax.get_xlim()[1], color="grey", alpha=0.12, lw=0)
        ax.axvline(buildable, color="grey", lw=0.8, ls="--")

        # Matching is the axis the physics depends on; area is one way to buy
        # it. Shown as a second scale rather than as the variable, so a revised
        # A_C relabels this plot instead of invalidating it.
        top = ax.secondary_xaxis(
            "top",
            functions=(
                lambda pct: area_for_sigma(np.maximum(pct, 1e-9) / 100, SKY130_CAP_A_C),
                lambda area: sigma_from_area(np.maximum(area, 1e-9), SKY130_CAP_A_C) * 100,
            ),
        )
        # Ticks are placed in area, not inherited from the sigma axis: area
        # goes as 1/sigma^2, so transformed sigma ticks bunch into an
        # unreadable smear at the low-sigma end. For the same reason only the
        # ticks that stay legibly apart on this range are kept.
        lo, hi = ax.get_xlim()
        keep: list[tuple[float, float]] = []
        for a in AREA_TICKS:
            at = sigma_from_area(a, SKY130_CAP_A_C) * 100
            if lo <= at <= hi and all(abs(at - s) > (hi - lo) * 0.06 for _, s in keep):
                keep.append((a, at))
        top.set_xticks([a for a, _ in keep])
        top.set_xticklabels([f"{a:g}" for a, _ in keep], fontsize=8)
        top.set_xlabel("unit capacitor area  [um^2]", fontsize=9)
        ax.set_xlabel("unit capacitor matching  sigma_u/C_u  [%]")
        ax.set_ylabel(label)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)

    fig.suptitle(
        f"Binary-weighted SAR: mismatch vs linearity, yield and resolution "
        f"({trials} arrays per point)\n"
        f"top axis: unit area at A_C = {SKY130_CAP_A_C} %*um. Matching is set by "
        f"area alone, so the flavour changes the capacitance in it, not the axis.\n"
        f"shaded: needs a unit smaller than the process will draw "
        f"({min_area} um^2), so the array is limited by geometry, not matching.",
        fontsize=11,
    )
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "yield.png"
    fig.savefig(target, dpi=140)
    return target


if __name__ == "__main__":
    print(plot())
