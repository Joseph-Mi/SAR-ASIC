"""Capacitor arrays with the imperfections a real one has.

Everything random in the mismatch study is drawn here and nowhere else, so a
result is reproducible from a seed and a study is readable without knowing how
the arrays were built.

Three effects, kept separate because they are physically separate and you will
want them on and off independently:

  random    uncorrelated unit-to-unit variation -- what Pelgrom describes
  gradient  a systematic slope across the die, from etch or oxide thickness
  place     which physical unit a branch owns, i.e. the layout

Placement is a permutation of the unit array, which is what makes a layout
scheme a value rather than a rewrite: build the array, apply the gradient to it
in physical order, then permute into branch order. Row-major placement is the
identity permutation and is the thing every centroid scheme has to beat.
"""

from __future__ import annotations

import numpy as np


def random_units(n_bits: int, sigma_rel: float, rng, trials: int | None = None):
    """Units drawn as C_u * (1 + N(0, sigma_rel)).

    Multiplicative because matching is specified as a ratio: sigma_rel is
    sigma_u/C_u, so the unit capacitance itself scales out and the array is
    returned normalised to C_u = 1.

    Returns (2**n_bits,) when trials is None, else (trials, 2**n_bits).
    """
    shape = (2**n_bits,) if trials is None else (trials, 2**n_bits)
    return 1.0 + rng.normal(0.0, sigma_rel, shape)


def gradient(units, strength: float):
    """Apply a linear slope across the array, in physical order.

    `strength` is the total fractional change from one end to the other, so
    0.01 means the last unit is 1% larger than the first. Centred, so it moves
    no total capacitance -- a gradient tilts matching without changing scale.

    Applied before placement. A gradient is a property of the die, not of the
    branch that happens to own the unit.
    """
    units = np.asarray(units, dtype=float)
    n_units = units.shape[-1]
    position = np.arange(n_units) / (n_units - 1) - 0.5
    return units * (1.0 + strength * position)


def place(units, perm):
    """Reorder physical units into branch order. `perm` is the layout."""
    return np.asarray(units, dtype=float)[..., np.asarray(perm)]


def row_major(n_bits: int) -> np.ndarray:
    """The identity placement: branch order is physical order.

    The baseline, not a recommendation. Its whole purpose is to be the thing a
    real placement scheme is compared against under the same gradient.
    """
    return np.arange(2**n_bits)


def sigma_from_area(area, a_c: float) -> float:
    """Pelgrom: sigma_u/C_u = A_C / sqrt(area).

    `area` is the unit capacitor's area in um^2. `a_c` is the technology's
    capacitor matching coefficient in percent-micrometres, the usual unit for
    a quoted A_C. The result is a fraction, not a percentage.

    There is deliberately no default for `a_c`. sky130's open PDK does not
    publish a trustworthy capacitor matching coefficient, so any value used
    here is an assumption the caller is making and has to be able to defend.
    Passing it explicitly is what keeps that assumption visible in the study
    that depends on it.
    """
    return (a_c / 100.0) / np.sqrt(area)


def area_for_sigma(sigma_rel: float, a_c: float) -> float:
    """Unit capacitor area, in um^2, that achieves a matching target.

    The inverse of sigma_from_area, and the direction the sizing decision
    actually runs: the yield sweep produces a sigma, and this turns it into
    silicon.
    """
    return (a_c / 100.0 / sigma_rel) ** 2


def cap_for_area(area, density: float) -> float:
    """Unit capacitance in fF from area in um^2, given a density in fF/um^2.

    Separate from the Pelgrom step because density and matching are two
    independent properties of a capacitor flavour. Comparing MiM against VPP
    means changing both, and conflating them hides which one won.
    """
    return area * density
