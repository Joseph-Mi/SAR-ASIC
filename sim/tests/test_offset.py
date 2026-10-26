"""What the committed offset spread has to be true of, and the three ways this
measurement reports a confident zero.

The spread itself costs tens of minutes of simulation, so it lives in a
committed baseline and is read here rather than redrawn. What is checked is
that it is a spread at all, that the file was written by the study it claims,
and that a seed still names one part -- the last on a sizing cheap enough to
simulate in a test, because what that proves is the plumbing and not the
designed latch.
"""

from __future__ import annotations

import shutil

import numpy as np
import pytest

import offset
import strongarm
from devices import Generic, Sky130, pdk_library
from strongarm import Drive, Sizes

needs_simulator = pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not on PATH")
needs_pdk = pytest.mark.skipif(not pdk_library().exists(), reason="sky130 model library not found")

#: A sizing and a strobe the seed can be checked through in seconds. The
#: question is whether a seed names a part, which no part of the answer to
#: depends on which latch is drawn.
CHEAP = Sizes(
    w_in=4.0,
    l_in=0.5,
    w_tail=8.0,
    l_tail=0.5,
    w_latch_n=1.0,
    w_latch_p=2.0,
    l_latch=0.15,
    w_pre=2.0,
    l_pre=0.15,
    c_load=10e-15,
)
CHEAP_DRIVE = Drive(1.8, 2e-9, 27, 1.0)
CHEAP_COMMON = 0.5

#: How far either side of a tie the seed is checked at. Close enough that what
#: the process drew is most of what decides the answer.
ASKED_AT = 1e-3


def baseline() -> tuple[dict[str, str], list[dict[str, str]]]:
    """The committed table, as its header's settings and a row per corner."""
    lines = offset.BASELINE.read_text().splitlines()
    header = dict(part.split("=", 1) for part in lines[0].lstrip("#").split())
    columns = lines[1].split()
    rows = [line.split() for line in lines[2:] if line.strip()]
    return header, [dict(zip(columns, row, strict=True)) for row in rows]


def test_the_committed_spread_is_a_spread_and_not_one_part():
    """This measurement has two ways to report a spread of exactly zero that
    both look like a finished Monte Carlo: the process' matching terms left
    switched off, and a seeded run of many draws, which is one part measured
    many times. Neither raises, and neither is distinguishable from a design
    that matches perfectly, so the committed number is checked for being a
    spread at all."""
    _, rows = baseline()
    flat = {row["corner"]: float(row["sigma_mv"]) for row in rows if float(row["sigma_mv"]) <= 0.0}
    assert not flat, f"corners whose offset does not vary between parts: {sorted(flat)}"


def test_the_baseline_was_drawn_by_the_study_that_reads_it():
    """A table written by an exploratory run is indistinguishable from the
    committed one once it is in the file, so the file carries what drew it."""
    header, rows = baseline()
    assert int(header["draws"]) == offset.OffsetStudy.draws
    assert int(header["seed"]) == offset.OffsetStudy.seed
    assert {row["corner"] for row in rows} == {corner[0] for corner in offset.CORNERS}
    assert all(int(row["draws"]) == offset.OffsetStudy.draws for row in rows)


def test_every_draw_is_its_own_part_and_not_its_position():
    """Seeds come from what a draw is, so inserting one leaves the rest alone.
    A seed taken from a draw's index would renumber every part after it and
    silently redraw a population the committed table already describes."""
    study = offset.OffsetStudy()
    corner, other = offset.CORNERS
    drawn = [offset.seed_for(study.seed, corner, draw) for draw in range(study.draws)]
    assert len(set(drawn)) == len(drawn), "two draws simulate the same part"
    assert drawn[:3] == [offset.seed_for(study.seed, corner, draw) for draw in range(3)]
    assert offset.seed_for(study.seed, other, 0) != drawn[0], "a corner redraws the same part"


def test_a_seeded_run_of_many_draws_is_refused():
    """The simulator re-seeds on every redraw, so one is a part measured many
    times with a spread of zero. The deck refuses rather than explaining."""
    with pytest.raises(ValueError, match="same part"):
        strongarm.deck(CHEAP, Generic(), strongarm.around(0.5, [0.0]), CHEAP_DRIVE, draws=2, seed=1)


@needs_simulator
@needs_pdk
def test_a_seed_names_one_part_and_another_seed_names_another(tmp_path):
    """What the whole measurement rests on, and it is checked on the process'
    own models because the matching terms are theirs: a generic device has no
    spread to be repeatable about, so the same test there would pass without
    exercising anything.

    Asked twice, a seed returns the same devices -- which is what lets a
    second pass refine the first's bracket rather than measure a different
    part -- and a different seed returns different ones, without which a
    population would be one part drawn over and over.
    """
    asked = strongarm.around(CHEAP_COMMON, [-ASKED_AT, 0.0, ASKED_AT])
    drawn = [
        strongarm.separations(
            tmp_path, CHEAP, Sky130(), asked, CHEAP_DRIVE, mismatch=True, seed=seed
        )
        for seed in (1, 1, 2)
    ]
    assert np.array_equal(drawn[0], drawn[1]), "a seed did not name one part"
    assert not np.array_equal(drawn[0], drawn[2]), "two seeds named the same part"
