"""DD-17's evidence: what placement does to a gradient, and what it costs to
get it wrong.

The array has two independent imperfections and only one of them is Pelgrom's.
Random unit-to-unit variation is what `yield_study.py` sweeps, and at the unit
this process draws it is far inside half an LSB. A *gradient* -- a systematic
slope across the die from etch or oxide thickness -- is not random, does not
average out over units, and is amplified or cancelled by nothing except which
physical position each branch's units occupy.

So this study sweeps the gradient, not sigma, and compares two placements:

  grouped      each branch owns a contiguous block of the array (`row_major`)
  interleaved  branch-order slot j sits at physical position bit-reverse(j)

Both see **the same drawn arrays** at each gradient -- one draw, placed two
ways -- so the difference between the two rows of a point is the permutation
and nothing else. Comparing two independently drawn populations would put the
Monte Carlo's own noise into the quantity being measured, and the effect here
is large enough that it would not have mattered, which is exactly the kind of
reasoning that makes a study unreproducible later.

What each point reports:

  dnl_msb     mean DNL at the MSB transition, in LSB. The random part averages
              to zero over trials, so this is the gradient's own term -- the
              number the placement decision turns on
  sigma_dnl   its spread, which is Pelgrom's and should be the same for both
              placements: a permutation cannot change how uncorrelated noise
              adds up
  p_missing   fraction of arrays with a code that cannot be produced. The
              yield criterion, since such a part is scrap
  max_inl     mean worst-case INL magnitude
  enob        effective bits of the arrays that are not scrap

Points are seeded from the gradient alone, so adding one leaves the others
untouched and a table written twice is byte-identical.
"""

from __future__ import annotations

import argparse
import pathlib
from dataclasses import dataclass, field

import numpy as np

import sky130
import study_points
from dynamic import enob_of
from metrics import has_missing_codes, inl, msb_dnl
from mismatch import (
    gradient,
    interleaved,
    place,
    random_units,
    row_major,
    sigma_from_area,
)

BASELINE = pathlib.Path(__file__).with_name("placement_baseline.txt")

#: The placements compared, by the permutation each one is.
PLACEMENTS = {"grouped": row_major, "interleaved": interleaved}


@dataclass(frozen=True)
class Study:
    """Every knob, named once."""

    n_bits: int = 10
    #: End-to-end fractional change across the array, **signed**, and the
    #: sign is not a formality. Which end of the die is thicker is arbitrary,
    #: and the two signs have different consequences under grouped placement:
    #: a positive slope makes the MSB branch the large one, so the MSB step
    #: comes out wide and DNL is positive, which costs linearity; a negative
    #: slope makes it the small one, so the step narrows and at
    #: DNL = -1 LSB the code disappears entirely and the part is scrap.
    #: A sweep of one sign measures the gentler half and reports no missing
    #: codes at any gradient, which is how a placement that loses parts
    #: passes a study. The range brackets the onset -- grouped reaches -1 LSB
    #: near a quarter of a percent -- from both sides.
    gradients: tuple[float, ...] = (
        -0.050,
        -0.020,
        -0.010,
        -0.005,
        -0.004,
        -0.003,
        -0.002,
        -0.001,
        0.0,
        0.001,
        0.002,
        0.003,
        0.004,
        0.005,
        0.010,
        0.020,
        0.050,
    )
    trials: int = 10000
    #: ENOB costs an FFT per array rather than a matmul per batch, so it is
    #: measured on a subset, as the yield sweep does.
    enob_trials: int = 100
    chunk: int = 2000
    seed: int = 20261030
    columns: tuple[str, ...] = field(
        default=(
            "placement",
            "gradient",
            "dnl_msb",
            "sigma_dnl",
            "p_missing",
            "max_inl",
            "enob",
        )
    )

    @property
    def sigma_rel(self) -> float:
        """The random variation the arrays are drawn with: this process's
        matching coefficient at the unit DD-16 keeps.

        Held fixed rather than swept, because what is under test here is the
        part Pelgrom does not describe. `yield_study.py` sweeps the other axis.
        """
        return sigma_from_area(sky130.mim_side() ** 2, sky130.CAP_A_C)


def run_point(study: Study, strength: float) -> list[dict]:
    """One gradient, both placements, from one set of drawn arrays."""
    rng = study_points.rng_for(study.seed, study.n_bits, strength)
    found = {name: {"msb": [], "worst_inl": [], "enob": [], "scrapped": 0} for name in PLACEMENTS}
    perms = {name: build(study.n_bits) for name, build in PLACEMENTS.items()}

    drawn = 0
    while drawn < study.trials:
        block = min(study.chunk, study.trials - drawn)
        # Drawn once and sloped once, in physical order: the gradient is a
        # property of the die, so both placements must see the same die.
        units = gradient(random_units(study.n_bits, study.sigma_rel, rng, block), strength)
        for name, perm in perms.items():
            placed = place(units, perm)
            seen = found[name]
            scrap = has_missing_codes(placed)
            seen["scrapped"] += int(scrap.sum())
            seen["msb"].append(msb_dnl(placed))
            seen["worst_inl"].append(np.max(np.abs(inl(placed)), axis=-1))
            if len(seen["enob"]) < study.enob_trials:
                wanted = study.enob_trials - len(seen["enob"])
                seen["enob"].extend(enob_of(u) for u in placed[~scrap][:wanted])
        drawn += block

    rows = []
    for name, seen in found.items():
        msb = np.concatenate(seen["msb"])
        rows.append(
            {
                "placement": name,
                "gradient": strength,
                "dnl_msb": float(np.mean(msb)),
                "sigma_dnl": float(np.std(msb)),
                "p_missing": seen["scrapped"] / study.trials,
                "max_inl": float(np.mean(np.concatenate(seen["worst_inl"]))),
                "enob": float(np.mean(seen["enob"])) if seen["enob"] else float("nan"),
            }
        )
    return rows


def sweep(study: Study) -> list[dict]:
    return [row for strength in study.gradients for row in run_point(study, strength)]


def format_table(study: Study, rows: list[dict]) -> str:
    """Fixed-width and fixed-precision, because this file is diffed."""
    widths = study_points.column_widths(study.columns)
    out = [
        f"# bits={study.n_bits} trials={study.trials} seed={study.seed} "
        f"sigma_rel={study.sigma_rel:.6f} unit={sky130.mim_side():g}um",
        "  ".join(c.rjust(widths[c]) for c in study.columns),
    ]
    for row in rows:
        cells = []
        for c in study.columns:
            v = row[c]
            cells.append((v if isinstance(v, str) else f"{v:.6f}").rjust(widths[c]))
        out.append("  ".join(cells))
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bits", type=int, default=Study.n_bits)
    parser.add_argument("--trials", type=int, default=Study.trials)
    parser.add_argument("--enob-trials", type=int, default=Study.enob_trials)
    parser.add_argument("--seed", type=int, default=Study.seed)
    parser.add_argument("--gradients", type=float, nargs="+", default=Study.gradients)
    parser.add_argument("--out", type=pathlib.Path, default=BASELINE)
    args = parser.parse_args()

    study = Study(
        n_bits=args.bits,
        gradients=tuple(args.gradients),
        trials=args.trials,
        enob_trials=args.enob_trials,
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
