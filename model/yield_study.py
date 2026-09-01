"""M1's sizing sweep: how well must unit capacitors match, and at what resolution.

The axis is sigma_u/C_u, not capacitor area. Area is one Pelgrom step away
(`mismatch.area_for_sigma`), and that step needs a matching coefficient sky130
does not publish reliably. Keeping the sweep in sigma means a revised
coefficient re-reads the same results instead of invalidating them.

What each point reports:

  sigma_dnl_msb   spread of DNL at the MSB transition, simulated
  analytic        sqrt(2**N - 1) * sigma_rel, the closed form it must match
  p_missing       fraction of arrays with a code that cannot be produced;
                  the yield criterion, since such a part is scrap
  max_inl         mean worst-case INL magnitude over the trials

Every point is seeded from its own parameters rather than from its position in
the sweep, so adding or reordering points leaves every other point's numbers
untouched. A study whose results move when you extend it is a study nobody can
compare against last week's.
"""

from __future__ import annotations

import argparse
import pathlib
from dataclasses import dataclass, field

import numpy as np

from metrics import has_missing_codes, inl, msb_dnl, sigma_dnl_msb_analytic
from mismatch import gradient, random_units

BASELINE = pathlib.Path(__file__).with_name("yield_baseline.txt")


@dataclass(frozen=True)
class Study:
    """Every knob, named once."""

    resolutions: tuple[int, ...] = (8, 10)
    sigmas: tuple[float, ...] = (0.005, 0.010, 0.015, 0.020, 0.030, 0.040)
    trials: int = 2000
    gradient_strength: float = 0.0
    seed: int = 20260901
    columns: tuple[str, ...] = field(
        default=("n_bits", "sigma_rel", "sigma_dnl_msb", "analytic", "p_missing", "max_inl")
    )


def rng_for(study: Study, n_bits: int, sigma_rel: float) -> np.random.Generator:
    """A stream determined by the point's coordinates, not by its index."""
    key = (study.seed, n_bits, int(round(sigma_rel * 1e12)))
    return np.random.default_rng(np.random.SeedSequence(key))


def run_point(study: Study, n_bits: int, sigma_rel: float) -> dict:
    units = random_units(n_bits, sigma_rel, rng_for(study, n_bits, sigma_rel), study.trials)
    if study.gradient_strength:
        units = gradient(units, study.gradient_strength)
    return {
        "n_bits": n_bits,
        "sigma_rel": sigma_rel,
        "sigma_dnl_msb": float(np.std(msb_dnl(units))),
        "analytic": sigma_dnl_msb_analytic(n_bits, sigma_rel),
        "p_missing": float(np.mean(has_missing_codes(units))),
        "max_inl": float(np.mean(np.max(np.abs(inl(units)), axis=-1))),
    }


def sweep(study: Study) -> list[dict]:
    return [
        run_point(study, n_bits, sigma) for n_bits in study.resolutions for sigma in study.sigmas
    ]


def format_table(study: Study, rows: list[dict]) -> str:
    """Fixed-width and fixed-precision, because this file is diffed."""
    widths = {c: max(len(c), 13) for c in study.columns}
    out = [
        f"# trials={study.trials} seed={study.seed} gradient={study.gradient_strength}",
        "  ".join(c.rjust(widths[c]) for c in study.columns),
    ]
    for row in rows:
        cells = []
        for c in study.columns:
            v = row[c]
            cells.append(
                f"{v:d}".rjust(widths[c]) if isinstance(v, int) else f"{v:.6f}".rjust(widths[c])
            )
        out.append("  ".join(cells))
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trials", type=int, default=Study.trials)
    parser.add_argument("--out", type=pathlib.Path, default=BASELINE)
    args = parser.parse_args()

    study = Study(trials=args.trials)
    table = format_table(study, sweep(study))
    args.out.write_text(table)
    print(table, end="")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
