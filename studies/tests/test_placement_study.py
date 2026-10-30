"""The placement sweep: that it reproduces, and that it says what DD-17 says.

The sweep is the evidence for a decision that is about to be executed 1024
times in silicon, so the claims are asserted against the committed numbers
rather than read off them. Two of the claims in the record did not survive
being checked, which is the reason this file exists at all.
"""

from __future__ import annotations

import pytest

from mismatch import gradient_dnl_msb, interleaved, row_major
from placement_study import BASELINE, Study, format_table, sweep

#: What counts as "the gradient a grouped array cannot survive", in LSB of
#: DNL at the MSB transition. At -1 the step from one code to the next has
#: shrunk to nothing and the code is unreachable, so the part is scrap.
MISSING = -1.0

#: How much of a population may be scrap before a placement is unusable.
#: Deliberately generous: the point is that one placement scraps most of a
#: wafer where the other scraps none, not where exactly the line is.
TOLERABLE_SCRAP = 0.01


@pytest.fixture(scope="module")
def study():
    return Study()


@pytest.fixture(scope="module")
def rows(study):
    return sweep(study)


@pytest.fixture(scope="module")
def committed():
    """The baseline, by placement and gradient."""
    lines = [ln for ln in BASELINE.read_text().splitlines() if not ln.startswith("#")]
    columns = lines[0].split()
    out = {}
    for line in lines[1:]:
        cells = line.split()
        row = dict(zip(columns, cells, strict=True))
        out[(row["placement"], float(row["gradient"]))] = {
            k: v if k == "placement" else float(v) for k, v in row.items()
        }
    return out


def test_committed_baseline_still_reproduces(study, rows):
    """The whole point of committing the artifact. A diff here means either
    the model changed or the seeding did, and both are things to look at."""
    assert format_table(study, rows) == BASELINE.read_text()


def test_both_placements_see_the_same_arrays_at_every_gradient(committed):
    """The comparison is paired, and this is what says so.

    A permutation cannot change how uncorrelated unit-to-unit variation adds
    up at the MSB transition -- that is Pelgrom's term and it depends on the
    unit count, not on where the units are. So the two placements must report
    the same spread at every gradient, and if they ever do not, the two rows
    of a point were drawn from different populations and nothing else in this
    table is a comparison.
    """
    for (_, strength), row in committed.items():
        other = committed[("interleaved" if row["placement"] == "grouped" else "grouped", strength)]
        assert row["sigma_dnl"] == pytest.approx(other["sigma_dnl"], rel=0.1), (
            f"the two placements saw different populations at gradient {strength}"
        )


def test_grouped_placement_loses_codes_where_the_law_says_it_will(committed):
    """The onset, measured against the closed form that predicts it.

    DNL at the MSB reaches -1 at `s = -1 / gradient_dnl_msb`, which is a
    quarter of a percent at ten bits. The sweep brackets it, so the fraction
    of scrap parts must be negligible on the shallow side and substantial on
    the steep side.
    """
    onset = 1.0 / gradient_dnl_msb(Study.n_bits, row_major(Study.n_bits))
    shallow = max(s for _, s in committed if s < 0 and abs(s) < onset)
    steep = min(s for _, s in committed if s < 0 and abs(s) > onset)
    assert committed[("grouped", shallow)]["p_missing"] < TOLERABLE_SCRAP
    assert committed[("grouped", steep)]["p_missing"] > 0.5


def test_interleaving_keeps_every_code_at_every_gradient_swept(committed):
    """And the other half of the decision: nothing is scrap, anywhere.

    The sweep reaches a 5% end-to-end slope, which is more than an order of
    magnitude past where grouped placement has already lost the whole
    population.
    """
    scrap = {s: r["p_missing"] for (p, s), r in committed.items() if p == "interleaved"}
    assert max(scrap.values()) == 0.0, f"interleaved placement scrapped parts at {scrap}"


def test_the_measured_slope_is_the_closed_form(committed):
    """The table against `gradient_dnl_msb`, which the figure also draws.

    Checked at the steepest gradient, where the deterministic term is far
    above the Monte Carlo's own noise. Mean DNL over ten thousand arrays is
    the gradient's term alone -- the random part averages out -- so this is
    the arithmetic and the arrays agreeing on the number the decision rests
    on.
    """
    steepest = max(s for _, s in committed)
    for name, build in (("grouped", row_major), ("interleaved", interleaved)):
        law = gradient_dnl_msb(Study.n_bits, build(Study.n_bits))
        assert committed[(name, steepest)]["dnl_msb"] == pytest.approx(law * steepest, rel=0.05)


def test_the_resolution_the_part_keeps_is_the_resolution_it_claims(committed):
    """What the decision buys, stated in the unit a datasheet uses.

    Grouped placement reports no ENOB at all once it is scrapping parts --
    the model declines to characterise a non-monotonic converter rather than
    reporting a number for it -- and where it does report one it has already
    lost bits. Interleaved holds ten bits across the whole sweep.
    """
    interleave = [r["enob"] for (p, _), r in committed.items() if p == "interleaved"]
    assert min(interleave) > Study.n_bits - 0.1

    steepest = max(s for _, s in committed)
    assert committed[("grouped", steepest)]["enob"] < Study.n_bits - 2
