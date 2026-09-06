"""How much comparator noise a resolution tolerates.

The mismatch study reads the array's transfer function and never converts.
Comparator noise does not move that curve: it corrupts the decisions taken
against it. A binary-weighted SAR carries no redundancy, so a wrong decision on
bit k is never revisited and costs 2**k codes, which makes the error
distribution heavy-tailed rather than a widening of the quantiser's own.
Measuring it therefore means running conversions, one at a time.

The array is ideal here on purpose. Mismatch is the other study's axis, and a
point that moved both would not say which one moved the result.

Noise is swept in LSB rather than volts so a single sweep serves every
resolution. Converting back is where resolution stops being free: the LSB
halves with every added bit, so the same comparator is worth one bit less each
time, and the volts column is what a comparator design is actually held to.

What each point reports:

  rms_err        error between the noisy code and the code the same array
                 would have produced undisturbed, in LSB
  p_wrong        fraction of conversions that came back a different code
  p_gross        fraction that missed by more than one code -- an early bit
                 decided wrongly, not a boundary flickering
  max_err        worst single conversion seen
  enob_rms       resolution the error leaves, against a perfect quantiser.
                 Named apart from the mismatch study's enob, which is measured
                 by transform on the array's own transfer curve: these isolate
                 different causes and adding them is not meaningful.
"""

from __future__ import annotations

import argparse
import pathlib
from dataclasses import dataclass, field

import numpy as np

from sar import ideal_units, sar_convert

BASELINE = pathlib.Path(__file__).with_name("noise_baseline.txt")

#: RMS error of a perfect quantiser, in LSB. The floor every point is read
#: against, and what makes the reported resolution equal the nominal one when
#: the comparator contributes nothing.
QUANTISATION_RMS_LSB = 1.0 / np.sqrt(12.0)

#: Comparator noise, in LSB, below which every mistake is a neighbouring code.
#: Above it an early bit starts deciding wrongly, and no later trial revisits
#: it, so the error costs a power of two rather than one.
GROSS_ERROR_ONSET_LSB = 0.5

VREF = 1.0


@dataclass(frozen=True)
class NoiseStudy:
    """Every knob, named once."""

    resolutions: tuple[int, ...] = (8, 10, 12)
    noises_lsb: tuple[float, ...] = (0.0, 0.125, 0.25, 0.5, 1.0, 2.0)
    conversions: int = 2000
    seed: int = 20260906
    columns: tuple[str, ...] = field(
        default=(
            "n_bits",
            "noise_lsb",
            "noise_uv",
            "rms_err",
            "p_wrong",
            "p_gross",
            "max_err",
            "enob_rms",
        )
    )


def rng_for(study: NoiseStudy, n_bits: int, noise_lsb: float) -> np.random.Generator:
    """A stream determined by the point's coordinates, not by its index."""
    key = (study.seed, n_bits, int(round(noise_lsb * 1e12)))
    return np.random.default_rng(np.random.SeedSequence(key))


def effective_bits(n_bits: int, rms_err_lsb: float) -> float:
    """Resolution left once the comparator's errors join the quantiser's own.

    The two are independent, so they add in power. A comparator contributing
    nothing returns the nominal resolution exactly.
    """
    total = np.sqrt(QUANTISATION_RMS_LSB**2 + rms_err_lsb**2)
    return n_bits - np.log2(total / QUANTISATION_RMS_LSB)


def run_point(study: NoiseStudy, n_bits: int, noise_lsb: float) -> dict:
    rng = rng_for(study, n_bits, noise_lsb)
    units = ideal_units(n_bits)
    lsb = VREF / 2**n_bits
    noise_v = noise_lsb * lsb

    errors = np.empty(study.conversions)
    for i in range(study.conversions):
        vin = rng.uniform(0.0, VREF)
        clean, _ = sar_convert(vin, units, VREF)
        noisy, _ = sar_convert(vin, units, VREF, cmp_noise_rms=noise_v, rng=rng)
        errors[i] = noisy - clean

    rms = float(np.sqrt(np.mean(errors**2)))
    return {
        "n_bits": n_bits,
        "noise_lsb": noise_lsb,
        "noise_uv": noise_v * 1e6,
        "rms_err": rms,
        "p_wrong": float(np.mean(errors != 0)),
        "p_gross": float(np.mean(np.abs(errors) > 1)),
        "max_err": float(np.max(np.abs(errors))),
        "enob_rms": effective_bits(n_bits, rms),
    }


def sweep(study: NoiseStudy) -> list[dict]:
    return [
        run_point(study, n_bits, noise)
        for n_bits in study.resolutions
        for noise in study.noises_lsb
    ]


def format_table(study: NoiseStudy, rows: list[dict]) -> str:
    """Fixed-width and fixed-precision, because this file is diffed."""
    widths = {c: max(len(c), 13) for c in study.columns}
    out = [
        f"# conversions={study.conversions} seed={study.seed} vref={VREF}",
        "  ".join(c.rjust(widths[c]) for c in study.columns),
    ]
    for row in rows:
        cells = [
            (f"{row[c]:d}" if isinstance(row[c], int) else f"{row[c]:.6f}").rjust(widths[c])
            for c in study.columns
        ]
        out.append("  ".join(cells))
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--conversions", type=int, default=NoiseStudy.conversions)
    parser.add_argument("--seed", type=int, default=NoiseStudy.seed)
    parser.add_argument("--out", type=pathlib.Path, default=BASELINE)
    args = parser.parse_args()

    study = NoiseStudy(conversions=args.conversions, seed=args.seed)
    table = format_table(study, sweep(study))
    args.out.write_text(table)
    print(table, end="")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
