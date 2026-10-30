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

from sar import branch_slices


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

    `strength` is the total fractional change from one end of the array to the
    other. Centred, so it moves no total capacitance -- a gradient tilts
    matching without changing scale.

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


def interleaved(n_bits: int) -> np.ndarray:
    """Common-centroid placement: branch-order slot `j` sits at the physical
    position whose index is `j`'s bits reversed.

    Why reversal and not something cleverer: the branches are binary, so slot
    `j` belongs to branch `floor(log2(j + 1))` -- the branch boundary falls
    wherever the leading one-bit moves. Reversing puts that bit at the
    *bottom* of the physical index, so consecutive slots of one branch land
    as far apart as the array allows, and every branch ends up spread over
    the whole of it rather than owning a contiguous block. It needs no table,
    no parameters and no per-resolution tuning, which matters because the
    thing it is competing with is a scheme somebody has to draw correctly
    1024 times.

    What it buys is measured rather than claimed, in `studies/placement_
    study.py`: a gradient is cancelled to the extent that each branch's
    centroid sits on the array's, and the centroids this produces are
    reported there per branch.
    """
    slots = np.arange(2**n_bits)
    reversed_bits = np.zeros_like(slots)
    for bit in range(n_bits):
        reversed_bits |= ((slots >> bit) & 1) << (n_bits - 1 - bit)
    return reversed_bits


def centroids(n_bits: int, perm) -> np.ndarray:
    """Each branch's mean physical position, in the units `gradient` uses.

    Zero is the middle of the array and the ends are -0.5 and +0.5, so a
    branch's centroid *is* the fraction of the gradient its units see on
    average. A placement cancels a linear gradient exactly when every one of
    these is zero, which is what makes this the quantity to report rather
    than the DNL it produces.
    """
    perm = np.asarray(perm)
    n_units = 2**n_bits
    position = perm / (n_units - 1) - 0.5
    return np.array([position[s].mean() for s in branch_slices(n_bits)])


def gradient_dnl_msb(n_bits: int, perm) -> float:
    """DNL at the MSB transition per unit of end-to-end gradient, in LSB.

    Exact, and general over any placement: a branch's share of a linear slope
    is its unit count times its centroid, and the MSB transition is the MSB
    branch against every branch below it, so

        DNL(MSB)/s = w[N-1]*c[N-1] - sum(w[k]*c[k] for k < N-1)

    with `w[k] = 2**k`. Nothing is approximated -- the total capacitance is
    unchanged by a centred gradient, so the LSB it is measured in does not
    move either, and the dummy is in no branch and drops out.

    For grouped placement this closes to `(M**2 - 2M - 2) / (4(M-1))` with
    `M = 2**N`, which is 255.749 at ten bits. DD-17 quotes `(2**N - 1)/4`,
    255.75 -- the asymptotic form, right to three parts in a million here and
    wrong by 1.3% at four bits. Interleaved placement gives almost exactly 1
    LSB, approaching it from below, so the ratio between the two placements
    is `2**(N-2)`: a factor that *improves* with resolution, which is the
    opposite of how the decision is usually described.
    """
    centred = centroids(n_bits, perm)
    weighted = 2.0 ** np.arange(n_bits) * centred
    return float(weighted[-1] - weighted[:-1].sum())


#: Percent in a whole. A matching coefficient is quoted in percent-micrometres.
PERCENT = 100.0


def sigma_from_area(area, a_c: float) -> float:
    """Pelgrom: sigma_u/C_u = A_C / sqrt(area).

    `area` is the unit capacitor's area in um^2. `a_c` is the technology's
    capacitor matching coefficient in percent-micrometres, the usual unit for
    a quoted A_C. The result is a fraction, not a percentage.

    Deliberately no default, even though the process's coefficient is a known
    number. Which
    capacitor flavour, and which process corner, is a choice the study is
    making rather than one this function should make on its behalf -- and a
    silent default is how an assumption stops being visible in the result that
    depends on it.
    """
    return (a_c / PERCENT) / np.sqrt(area)


def area_for_sigma(sigma_rel: float, a_c: float) -> float:
    """Unit capacitor area, in um^2, that achieves a matching target.

    The inverse of sigma_from_area, and the direction the sizing decision
    actually runs: the yield sweep produces a sigma, and this turns it into
    silicon.
    """
    return (a_c / PERCENT / sigma_rel) ** 2
