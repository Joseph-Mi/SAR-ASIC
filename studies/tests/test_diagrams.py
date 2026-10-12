"""The figures, held to drawing at all.

A figure script is the one kind of code that fails silently: nobody runs it
between the day it is written and the day someone wants the picture, and by
then the model under it has moved. These render every figure into a temporary
directory, so a renamed function or a changed signature anywhere beneath them
fails a run rather than a request.

What they do not check is whether a picture is any good. That is what looking
at it is for.
"""

from __future__ import annotations

import pytest

import diagrams

#: A figure that rendered to nothing is a blank canvas with a title on it.
#: Any real plot is far larger than this, in bytes.
MIN_BYTES = 10_000


@pytest.fixture(autouse=True)
def drawing():
    pytest.importorskip("matplotlib")


@pytest.mark.parametrize("figure", diagrams.FIGURES, ids=lambda f: f.__name__)
def test_every_figure_draws(figure, tmp_path):
    drawn = figure(tmp_path)
    assert drawn.is_file()
    assert drawn.stat().st_size > MIN_BYTES, f"{drawn.name} came out suspiciously small"


def test_drawing_them_all_draws_each_one_once(tmp_path):
    drawn = diagrams.draw_all(tmp_path)
    assert len(drawn) == len(diagrams.FIGURES)
    assert len({path.name for path in drawn}) == len(drawn)
    assert all(path.is_file() for path in drawn)


def test_no_figure_is_defined_and_then_never_drawn():
    """A figure left out of the set is one nothing renders and nothing checks,
    which is the state this module exists to stay out of."""
    public = {
        name
        for name, value in vars(diagrams).items()
        if callable(value)
        and not name.startswith("_")
        and getattr(value, "__module__", None) == diagrams.__name__
        and name != "draw_all"
    }
    assert public == {figure.__name__ for figure in diagrams.FIGURES}
