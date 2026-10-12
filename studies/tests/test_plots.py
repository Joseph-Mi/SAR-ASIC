"""The committed sweeps' figures, held to drawing at all.

The same guard the explanatory diagrams have, for the same reason: a figure
script is the one kind of code nobody runs between writing it and wanting it,
so between those two moments the model underneath it moves and nothing says
so. These render both figures from the committed artifacts into a temporary
directory.

What they do not check is whether a picture is any good. That is what looking
at it is for.
"""

from __future__ import annotations

import pytest

import plots

#: A figure that rendered to nothing is a blank canvas with a title on it.
#: Any real plot is far larger than this, in bytes.
MIN_BYTES = 10_000


@pytest.fixture(autouse=True)
def drawing():
    pytest.importorskip("matplotlib")


@pytest.mark.parametrize("figure", plots.FIGURES, ids=lambda f: f.__name__)
def test_every_figure_draws(figure, tmp_path):
    drawn = figure(out_dir=tmp_path)
    assert drawn.is_file()
    assert drawn.stat().st_size > MIN_BYTES, f"{drawn.name} came out suspiciously small"


def test_drawing_them_all_draws_each_one_once(tmp_path):
    drawn = plots.draw_all(tmp_path)
    assert len(drawn) == len(plots.FIGURES)
    assert len({path.name for path in drawn}) == len(drawn)
    assert all(path.is_file() for path in drawn)


def test_each_figure_reads_the_artifact_under_review(tmp_path):
    """Not a fresh run of the study. A plot of numbers nobody committed is a
    picture of something that was never reviewed, and the two diverge silently
    once a seed or a sweep point moves."""
    for figure in plots.FIGURES:
        assert "path" in figure.__code__.co_varnames[: figure.__code__.co_argcount]


def test_no_figure_is_defined_and_then_never_drawn():
    """A figure left out of the set is one nothing renders and nothing checks,
    which is the state this module exists to stay out of."""
    public = {
        name
        for name, value in vars(plots).items()
        if callable(value)
        and not name.startswith("_")
        and getattr(value, "__module__", None) == plots.__name__
        and name not in ("draw_all", "main", "read_table")
    }
    assert public == {figure.__name__ for figure in plots.FIGURES}
