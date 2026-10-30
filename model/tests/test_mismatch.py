"""Mismatch generators. Statistical claims are checked at sample sizes large
enough that a passing run is evidence rather than luck."""

import numpy as np
import pytest

import sky130
from metrics import msb_dnl
from mismatch import (
    PERCENT,
    area_for_sigma,
    centroids,
    gradient,
    gradient_dnl_msb,
    interleaved,
    place,
    random_units,
    row_major,
    sigma_from_area,
)
from sar import branch_weights, ideal_units

RESOLUTIONS = (4, 8, 10)

#: How far `(2**N - 1)/4` sits from the exact gradient law at each
#: resolution. It is an asymptotic form, so it tightens as the array
#: grows, and naming the error per resolution is what stops it being
#: quoted as exact -- which is how it entered the record.
ASYMPTOTIC_ERROR = {4: 0.014, 8: 6e-5, 10: 3e-6}

#: The resolution the single-array tests use.
N_BITS = 8

#: A mismatch small enough to keep every array monotonic, one large enough to
#: move branch weights visibly, and a gradient strength across the array.
SIGMA = 0.01
SIGMA_LARGE = 0.02
TILT = 0.01

#: A batch size, and a sample large enough that its spread is the requested
#: one to within the tolerances below.
BATCH = 7
SAMPLE = 500
MEAN_TOLERANCE = 1e-3
SPREAD_TOLERANCE = 0.02
EXACT = 1e-9

#: Seeds, one per test, so no test's draws depend on another's.
SEED_SHAPE, SEED_SPREAD, SEED_ZERO, SEED_GRADIENT, SEED_PLACE, SEED_PERMUTE, SEED_REPEAT = (
    0,
    1,
    3,
    5,
    6,
    7,
    42,
)

#: Pelgrom's law checked at a unit area and four times it; a coefficient, a
#: second one, and areas to round-trip through it; a density.
UNIT_AREA, QUADRUPLE = 1.0, 4.0
A_C, A_C_OTHER = 1.0, 1.5
AREAS = (0.25, 1.0, 9.0)
DENSITY = 1.5

#: Matching targets the sizing decision might ask for.
TARGETS = (0.005, 0.010, 0.020)


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_batch_shape_is_trials_by_units(n_bits):
    rng = np.random.default_rng(SEED_SHAPE)
    assert random_units(n_bits, SIGMA, rng).shape == (2**n_bits,)
    assert random_units(n_bits, SIGMA, rng, trials=BATCH).shape == (BATCH, 2**n_bits)


def test_draws_have_the_requested_spread():
    """sigma_rel means sigma_u/C_u, so it must come back out of the sample."""
    rng = np.random.default_rng(SEED_SPREAD)
    u = random_units(max(RESOLUTIONS), SIGMA_LARGE, rng, trials=SAMPLE)
    assert np.isclose(u.mean(), 1.0, atol=MEAN_TOLERANCE)
    assert np.isclose(u.std(), SIGMA_LARGE, rtol=SPREAD_TOLERANCE)


def test_same_seed_gives_the_same_array():
    a = random_units(N_BITS, SIGMA, np.random.default_rng(SEED_REPEAT))
    b = random_units(N_BITS, SIGMA, np.random.default_rng(SEED_REPEAT))
    assert np.array_equal(a, b)


def test_zero_sigma_is_a_perfect_array():
    u = random_units(N_BITS, 0.0, np.random.default_rng(SEED_ZERO))
    assert np.array_equal(u, np.ones(2**N_BITS))


def test_gradient_tilts_without_changing_total():
    """A gradient redistributes capacitance; it does not add any.

    If it changed the total it would move full scale, and a full-scale shift
    is a gain error rather than the matching effect under study.
    """
    u = np.ones(2**N_BITS)
    g = gradient(u, TILT)
    assert np.isclose(g.sum(), u.sum())
    assert np.isclose(g[-1] - g[0], TILT, rtol=EXACT)


def test_gradient_of_zero_strength_changes_nothing():
    u = random_units(N_BITS, SIGMA, np.random.default_rng(SEED_GRADIENT))
    assert np.allclose(gradient(u, 0.0), u)


def test_row_major_placement_is_the_identity():
    u = random_units(N_BITS, SIGMA, np.random.default_rng(SEED_PLACE))
    assert np.array_equal(place(u, row_major(N_BITS)), u)


def test_placement_moves_mismatch_between_branches():
    """A permutation conserves total capacitance but not the branch weights.

    That is the entire mechanism a centroid scheme exploits: same units, same
    total, different DNL.
    """
    rng = np.random.default_rng(SEED_PERMUTE)
    u = random_units(N_BITS, SIGMA_LARGE, rng)
    shuffled = place(u, rng.permutation(2**N_BITS))
    assert np.isclose(shuffled.sum(), u.sum())
    assert not np.allclose(branch_weights(shuffled), branch_weights(u))


def test_pelgrom_is_a_square_root_law():
    """Four times the area is half the sigma. This is the whole reason unit
    caps are large, and the exchange rate the sizing decision is paying."""
    bigger = sigma_from_area(QUADRUPLE * UNIT_AREA, A_C)
    assert np.isclose(bigger, sigma_from_area(UNIT_AREA, A_C) / np.sqrt(QUADRUPLE))


def test_area_and_sigma_invert_each_other():
    for area in AREAS:
        assert np.isclose(area_for_sigma(sigma_from_area(area, A_C_OTHER), A_C_OTHER), area)


def test_the_coefficient_is_read_as_percent_not_fraction():
    """A_C is quoted in percent-micrometres and sigma_from_area returns a
    fraction, so a unit capacitor of one square micrometre must come back as
    the coefficient in percent. Getting that conversion wrong scales every
    area in the study by ten thousand and still looks plausible."""
    assert np.isclose(sigma_from_area(UNIT_AREA, sky130.CAP_A_C), sky130.CAP_A_C / PERCENT)


def test_the_sizing_direction_round_trips():
    """A matching target becomes an area, and that area has to give the target
    back. This is the direction the design decision actually runs."""
    for target in TARGETS:
        area = area_for_sigma(target, sky130.CAP_A_C)
        assert np.isclose(sigma_from_area(area, sky130.CAP_A_C), target)


#: The gradient the placement claims are checked at. Large enough that the
#: effect is far outside the arithmetic's noise, and well past any slope a die
#: this size would plausibly carry -- what is under test is the ratio between
#: the two placements, which is a property of the permutations and not of the
#: slope.
PLACEMENT_GRADIENT = 0.01


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_interleaving_is_a_permutation_of_the_whole_array(n_bits):
    """Every physical position used exactly once. A placement that drops or
    repeats one is not a layout, and bit reversal is easy to get subtly wrong
    at a resolution nobody tested."""
    assert sorted(interleaved(n_bits)) == list(range(2**n_bits))


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
@pytest.mark.parametrize("build", (row_major, interleaved))
def test_the_gradient_law_is_what_the_arrays_do(n_bits, build):
    """The closed form against the arrays it describes, for both placements.

    This is the number the placement decision turns on, so it is held to the
    model rather than to the sentence that states it. The sentence was wrong
    once already: DD-17 quotes the grouped figure as `(2**N - 1)/4`, which is
    the asymptotic form and is out by 1.3% at four bits.
    """
    perm = build(n_bits)
    units = place(gradient(ideal_units(n_bits), PLACEMENT_GRADIENT), perm)
    measured = float(msb_dnl(units)) / PLACEMENT_GRADIENT
    assert measured == pytest.approx(gradient_dnl_msb(n_bits, perm), rel=1e-9)


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_grouped_placement_amplifies_a_gradient_by_about_a_quarter_of_the_array(n_bits):
    """DD-17's figure is an approximation, and this is how good it is.

    Kept as a test rather than deleted, because the approximate form is the
    one that explains *why* -- a quarter of the array's units sit between the
    MSB branch's centroid and everything below it -- and the exact one does
    not explain anything. Both belong, with the error between them named.
    """
    exact = gradient_dnl_msb(n_bits, row_major(n_bits))
    asymptotic = (2**n_bits - 1) / 4
    assert exact == pytest.approx(asymptotic, rel=ASYMPTOTIC_ERROR[n_bits])


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_interleaving_leaves_about_one_lsb_and_gets_better_with_resolution(n_bits):
    """And it is about one LSB, not nothing.

    Worth asserting as a number rather than as "small": a reader who
    remembers "interleaving cancels the gradient" will not expect a residue
    at all. One LSB per unit of slope means a code survives any gradient
    short of 100%, where grouped loses one at a quarter of a percent.

    The advantage is `2**(N-2)`, so it *grows* with resolution -- at four bits
    interleaving is only four times better and at ten it is 256 times. The
    decision is therefore more forced at the resolution this part is, not
    less.
    """
    residue = abs(gradient_dnl_msb(n_bits, interleaved(n_bits)))
    assert residue < 1.0
    ratio = gradient_dnl_msb(n_bits, row_major(n_bits)) / residue
    assert ratio == pytest.approx(2 ** (n_bits - 2), rel=0.05)


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_what_interleaving_centres_is_the_weighted_centroid_and_not_the_centroid(n_bits):
    """The mechanism, asserted because the record had it wrong.

    DD-17 said interleaving puts every branch's centroid within 0.0005 of the
    array's. It does not, and not nearly: the LSB branch is a single unit and
    bit reversal puts it at physical position 0, the far end of the die, for
    a centroid of -0.5 -- the worst value there is. Only the top few branches
    are anywhere near the middle.

    What is actually centred is each branch's centroid *times its unit
    count*, and those come out antisymmetric from the second branch up, so
    they cancel in pairs. That is why a branch sitting at the very edge of
    the die costs nothing: it has one unit there, and one unit is one LSB.
    """
    centred = centroids(n_bits, interleaved(n_bits))
    assert centred[0] == pytest.approx(-0.5), "the LSB branch is not near the middle"

    weighted = 2.0 ** np.arange(n_bits) * centred
    assert weighted[1:] == pytest.approx(-weighted[1:][::-1], abs=1e-12)
    # Which is what leaves the residue just under one LSB. The weighted
    # centroids above the first cancel, so the branches below the MSB come to
    # `weighted[0] - weighted[-1]`, and the transition is the MSB's own term
    # less that: twice its own, less the lone unit stranded at the edge.
    assert gradient_dnl_msb(n_bits, interleaved(n_bits)) == pytest.approx(
        2 * weighted[-1] - weighted[0], abs=1e-9
    )
