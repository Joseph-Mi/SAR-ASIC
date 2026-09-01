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
  enob            effective bits of the arrays that are not scrap -- what the
                  resolution on the datasheet is actually worth

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

from dynamic import enob_of
from metrics import has_missing_codes, inl, msb_dnl, sigma_dnl_msb_analytic
from mismatch import gradient, random_units

BASELINE = pathlib.Path(__file__).with_name("yield_baseline.txt")


@dataclass(frozen=True)
class Study:
    """Every knob, named once."""

    resolutions: tuple[int, ...] = (8, 10, 12)
    sigmas: tuple[float, ...] = (0.005, 0.010, 0.015, 0.020, 0.030, 0.040)
    trials: int = 10000
    # ENOB costs an FFT per array rather than a matmul per batch, so it is
    # measured on a subset. The spread across arrays is small next to the
    # spread across sigma, which is the axis being read.
    enob_trials: int = 100
    gradient_strength: float = 0.0
    # Trials are generated in blocks so peak memory does not grow with the
    # trial count -- every column reduces to one scalar per trial anyway. The
    # draw is a single sequential stream, so block size does not change any
    # result; it only decides how much of it exists at once.
    chunk: int = 2000
    seed: int = 20260901
    columns: tuple[str, ...] = field(
        default=(
            "n_bits",
            "sigma_rel",
            "sigma_dnl_msb",
            "analytic",
            "p_missing",
            "max_inl",
            "enob",
        )
    )


def rng_for(study: Study, n_bits: int, sigma_rel: float) -> np.random.Generator:
    """A stream determined by the point's coordinates, not by its index."""
    key = (study.seed, n_bits, int(round(sigma_rel * 1e12)))
    return np.random.default_rng(np.random.SeedSequence(key))


def run_point(study: Study, n_bits: int, sigma_rel: float) -> dict:
    rng = rng_for(study, n_bits, sigma_rel)
    msb, worst_inl, enob_seen = [], [], []
    scrapped = 0

    drawn = 0
    while drawn < study.trials:
        block = min(study.chunk, study.trials - drawn)
        units = random_units(n_bits, sigma_rel, rng, block)
        if study.gradient_strength:
            units = gradient(units, study.gradient_strength)

        scrap = has_missing_codes(units)
        scrapped += int(scrap.sum())
        msb.append(msb_dnl(units))
        worst_inl.append(np.max(np.abs(inl(units)), axis=-1))
        if len(enob_seen) < study.enob_trials:
            wanted = study.enob_trials - len(enob_seen)
            enob_seen.extend(enob_of(u) for u in units[~scrap][:wanted])
        drawn += block

    return {
        "n_bits": n_bits,
        "sigma_rel": sigma_rel,
        "sigma_dnl_msb": float(np.std(np.concatenate(msb))),
        "analytic": sigma_dnl_msb_analytic(n_bits, sigma_rel),
        "p_missing": scrapped / study.trials,
        "max_inl": float(np.mean(np.concatenate(worst_inl))),
        "enob": float(np.mean(enob_seen)) if enob_seen else float("nan"),
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
    parser.add_argument("--enob-trials", type=int, default=Study.enob_trials)
    parser.add_argument("--seed", type=int, default=Study.seed)
    parser.add_argument("--gradient", type=float, default=Study.gradient_strength)
    parser.add_argument("--resolutions", type=int, nargs="+", default=Study.resolutions)
    parser.add_argument("--sigmas", type=float, nargs="+", default=Study.sigmas)
    parser.add_argument("--out", type=pathlib.Path, default=BASELINE)
    args = parser.parse_args()

    study = Study(
        resolutions=tuple(args.resolutions),
        sigmas=tuple(args.sigmas),
        trials=args.trials,
        enob_trials=args.enob_trials,
        gradient_strength=args.gradient,
        seed=args.seed,
    )
    if study != Study() and args.out == BASELINE:
        parser.error(
            f"refusing to write {BASELINE.name} from a non-default study -- the "
            "committed baseline is what the regression test compares against. "
            "Pass --out to write an exploratory run somewhere else."
        )

    table = format_table(study, sweep(study))
    args.out.write_text(table)
    print(table, end="")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
