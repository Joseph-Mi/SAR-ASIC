"""Draw the committed sweep.

Reads `yield_baseline.txt` rather than re-running the study, so a plot always
shows exactly the numbers under review. Regenerating the artifact and looking
at a picture of something else is the failure mode this avoids.

matplotlib is imported inside the drawing function. It ships in the container
but is not in requirements.txt, and CI installs only requirements.txt -- so
importing it at module scope would make this file un-importable in CI for no
benefit.
"""

from __future__ import annotations

import pathlib

import numpy as np

from yield_study import BASELINE

OUT_DIR = pathlib.Path("build/model")

# What each panel plots, and whether small values matter enough to need a log
# axis. p_missing spans four decades and is read near zero; the rest are read
# across their whole range.
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

        ax.set_xlabel("unit capacitor matching  sigma_u/C_u  [%]")
        ax.set_ylabel(label)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)

    fig.suptitle(
        f"Binary-weighted SAR: mismatch vs linearity, yield and resolution "
        f"({trials} arrays per point)"
    )
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "yield.png"
    fig.savefig(target, dpi=140)
    return target


if __name__ == "__main__":
    print(plot())
