"""Draw the committed sweeps.

Reads the committed artifact rather than re-running the study, so a plot always
shows exactly the numbers under review. Regenerating the artifact and then
looking at a picture of something else is the failure mode this avoids.

Nothing here chooses how a figure looks, and nothing here imports matplotlib:
the house style owns both, so these figures match every other one in the
repository, a restyle is one edit somewhere else, and this file stays
importable where the drawing library is not installed.
"""

from __future__ import annotations

import pathlib

import numpy as np

import house
import sky130
from mismatch import (
    PERCENT,
    area_for_sigma,
    sigma_from_area,
)
from noise_study import BASELINE as NOISE_BASELINE
from noise_study import GROSS_ERROR_ONSET_LSB
from unit_study import BASELINE as UNIT_BASELINE
from yield_study import BASELINE

OUT_DIR = pathlib.Path("build/studies")

#: Panel aspect, per panel. The yield figure is a square grid; the noise
#: figure is a row, so its panels are narrower to keep the canvas readable.
YIELD_PANEL = (5.6, 4.2)
NOISE_PANEL = (4.7, 4.2)

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


def read_table(
    path: pathlib.Path = BASELINE, counts: tuple[str, ...] = ("n_bits",)
) -> tuple[dict, list[dict]]:
    """Parse an artifact back into rows. The header comment carries the run.

    `counts` names the columns that are whole numbers rather than
    measurements, because one printed as a float labels a series "10.0 bits".
    A study whose columns are all measurements passes none.
    """
    lines = path.read_text().splitlines()
    header = dict(kv.split("=") for kv in lines[0].lstrip("# ").split())
    columns = lines[1].split()
    rows = []
    for line in lines[2:]:
        values = [float(v) for v in line.split()]
        row = dict(zip(columns, values, strict=True))
        for name in counts:
            row[name] = int(row[name])
        rows.append(row)
    return header, rows


def plot(path: pathlib.Path = BASELINE, out_dir: pathlib.Path = OUT_DIR):
    header, rows = read_table(path)
    trials = int(header["trials"])
    floor = 1.0 / trials
    resolutions = sorted({r["n_bits"] for r in rows})

    # The sweep runs in matching, but area is what gets drawn, and the process
    # will not draw one below a minimum. Everything to the left of this is
    # reachable; everything to the right asks for a device that cannot be made.
    min_area = min(sky130.CAP_MIN_AREA_MIM, sky130.CAP_MIN_AREA_VPP)
    buildable = sigma_from_area(min_area, sky130.CAP_A_C) * PERCENT

    fig, axes = house.canvas(2, 2, size=YIELD_PANEL)
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
                    "--",
                    color=house.MODEL,
                    lw=house.BOUND_WIDTH,
                    label="sqrt(2^N-1)*sigma" if n_bits == resolutions[0] else None,
                )
        if log:
            ax.axhline(floor, color=house.INK_SOFT, lw=house.THIN, ls=":")
            ax.annotate(
                f"none seen in {trials} trials",
                (NOTE_X, floor * NOTE_LIFT),
                xycoords=("axes fraction", "data"),
                fontsize=house.FONT_SMALL,
                color=house.INK_SOFT,
            )

        lo0, hi0 = ax.get_xlim()
        ax.set_xlim(
            left=min(lo0, buildable * LIMIT_MARGIN[0]), right=max(hi0, buildable * LIMIT_MARGIN[1])
        )
        ax.axvspan(buildable, ax.get_xlim()[1], color=house.BAD, alpha=house.SHADE_ALPHA, lw=0)
        house.bound(ax, buildable, "process floor", axis="x", color=house.BAD)

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
        top.set_xticklabels([f"{a:g}" for a, _ in keep], fontsize=house.FONT_SMALL)
        top.set_xlabel("unit capacitor area  [um^2]")
        ax.set_xlabel("unit capacitor matching  sigma_u/C_u  [%]")
        ax.set_ylabel(label)
        ax.legend()

    fig.suptitle(
        f"Binary-weighted SAR: mismatch vs linearity, yield and resolution "
        f"({trials} arrays per point)\n"
        f"top axis: unit area at A_C = {sky130.CAP_A_C} %*um. Matching is set by "
        f"area alone, so the flavour changes the capacitance in it, not the axis.\n"
        f"shaded: needs a unit smaller than the process will draw "
        f"({min_area} um^2), so the array is limited by geometry, not matching.",
    )
    fig.tight_layout()
    return house.save(fig, out_dir / "yield.png")


def plot_noise(path: pathlib.Path = NOISE_BASELINE, out_dir: pathlib.Path = OUT_DIR):
    """What the comparator has to be, for each resolution worth considering."""
    header, rows = read_table(path)
    resolutions = sorted({r["n_bits"] for r in rows})
    fig, (ax1, ax2, ax3) = house.canvas(1, 3, size=NOISE_PANEL)

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

    house.bound(ax2, GROSS_ERROR_ONSET_LSB, "gross-error onset", axis="x", color=house.WARN)
    ax2.axhline(1.0 / float(header["conversions"]), color=house.INK_SOFT, lw=house.THIN, ls=":")
    ax2.set_xlabel("comparator noise  [LSB rms]")
    ax2.set_ylabel("P(missed by more than one code)")
    ax2.set_title("Where a wrong early bit starts costing 2^k")

    # The same fraction of an LSB, priced in volts. This is the axis a
    # comparator is designed against, and the only one resolution moves.
    ax3.set_xlabel("comparator noise  [LSB rms]")
    ax3.set_ylabel("the same noise, in microvolts")
    ax3.set_title("What that costs in volts")

    for ax in (ax1, ax2, ax3):
        ax.legend()

    fig.suptitle(
        f"Comparator noise against resolution ({header['conversions']} conversions per point)\n"
        f"degradation tracks the LSB, so resolution is bought in comparator volts",
    )
    fig.tight_layout()
    return house.save(fig, out_dir / "noise.png")


#: Every figure this module draws. Named once so the script and the test that
#: renders them cannot disagree about what "every figure" means.
#: Panels of the unit-size figure: the column to draw, the axis it is read
#: on, and whether it wants a log scale. Each panel answers one question, and
#: the questions are in the order the study answers them -- does it fit, does
#: it match, what does the switch cost, how fast does it settle.
UNIT_PANELS = (
    (
        ("block_group", "branches grouped"),
        ("block_inter", "branches interleaved"),
        "square array + ring + keep-away  [um]",
        False,
    ),
    (
        ("sigma_dnl_msb", "sigma(DNL) at the MSB"),
        ("noise_lsb", "kT/C, rms"),
        "error  [LSB]",
        True,
    ),
    (
        ("inject_scaled", "top switch narrowed to hold the clock"),
        ("inject_fixed", "top switch left at 8 um"),
        "charge on the top plate  [x today]",
        True,
    ),
    (
        ("tau_fixed_ns", "top switch left at 8 um"),
        ("tau_min_ns", "top switch narrowed"),
        "sampling loop, slowest corner  [ns]",
        True,
    ),
)

#: Half an LSB: what a converter's error budget is quoted against, and the
#: line both of the second panel's series have to sit under.
HALF_LSB = 0.5


def plot_unit(path: pathlib.Path = UNIT_BASELINE, out_dir: pathlib.Path = OUT_DIR):
    """What each candidate unit size costs, on one page.

    Four panels because four things move with the size and they do not move
    together: one of them binds today, two have margin to spare at every size
    in the sweep, and one gets *better* as the unit shrinks, which is the
    result that is hard to believe without seeing it.

    Today's size is drawn as a vertical bound in every panel, because every
    number here is only interesting next to the one the project already has.
    """
    header, rows = read_table(path, counts=())
    side = np.array([r["side_um"] for r in rows])
    today = sky130.mim_side()
    strip = float(header["strip"].rstrip("um"))

    # Narrowing the switch only means anything where the clock is still
    # today's. Above today's unit the array exceeds the loop on the pins
    # alone, so the narrowest switch the process draws is all there is and
    # the conversion slows instead -- the charge is lower there because the
    # part is slower, which is not a comparison anyone wants to read off a
    # line. So that series stops where the comparison does.
    clock = next(r["tau_min_ns"] for r in rows if r["side_um"] == today)
    held = np.array([r["tau_min_ns"] <= clock for r in rows])

    fig, axes = house.canvas(2, 2, size=YIELD_PANEL)
    for ax, (first, second, label, log) in zip(axes.flat, UNIT_PANELS, strict=True):
        for column, name in (first, second):
            y = np.array([r[column] for r in rows])
            x = side
            if column == "inject_scaled":
                x, y = side[held], y[held]
            (ax.semilogy if log else ax.plot)(x, y, "o-", label=name)
        house.bound(ax, today, f"{today:g} um today", axis="x")
        if first[0].startswith("block"):
            house.bound(ax, strip, f"the strip, {strip:g} um")
        if first[0] == "sigma_dnl_msb":
            house.bound(ax, HALF_LSB, "half an LSB")
        if first[0] == "inject_scaled":
            house.bound(ax, 1.0, "today")
        ax.set_xlabel("unit capacitor side, drawn  [um]")
        ax.set_ylabel(label)
        ax.legend()

    fig.suptitle(
        "What the unit capacitor's size costs, at "
        f"{header['bits']} bits into a {strip:g} um strip\n"
        "top left is the only panel that binds: at today's size the square "
        "array misses the strip whichever way its branches are placed.\n"
        "bottom left is why shrinking is not a trade -- a smaller array "
        "settles faster, and that buys a narrower switch, which injects less.\n"
        "that series stops at today's size because above it the clock cannot "
        "be held at any switch: the two pins alone exceed the loop.",
    )
    fig.tight_layout()
    return house.save(fig, out_dir / "unit.png")


FIGURES = (plot, plot_noise, plot_unit)


def draw_all(out_dir: pathlib.Path = OUT_DIR) -> list[pathlib.Path]:
    return [figure(out_dir=out_dir) for figure in FIGURES]


if __name__ == "__main__":
    for drawn in draw_all():
        print(drawn)
