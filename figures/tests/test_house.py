"""The house style, and the rule that nothing goes around it.

A style is only a style while everything uses it. One script that sets its own
colours is how a repository ends up with two palettes, and the second one is
always discovered in a review of something else. So the rule is mechanical and
checked here rather than remembered.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

import pytest

import house

REPO = next(p for p in pathlib.Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
HOUSE = "figures/house.py"

#: The file that states the rule has to name the calls it forbids, so it is
#: exempt from its own scan. Nothing else is.
DECLARES_THE_RULE = str(pathlib.Path(__file__).resolve().relative_to(REPO))

#: Calls that decide how a figure is written or how the drawing library
#: behaves. Each belongs in exactly one file.
RESERVED = {
    ".savefig(": "writing a figure",
    "rcParams": "setting a drawing default",
    "matplotlib.use(": "choosing a backend",
}

#: A colour written into the source. The palette is named, so a literal is
#: either a second palette or a one-off, and both are what this rule exists
#: to stop.
HEX_COLOUR = re.compile(r'"#[0-9a-fA-F]{3,8}"')

#: Contrast ratio a line must clear against the surface it is drawn on. The
#: accessibility guidelines ask this of a graphical object; text asks more,
#: and the text here is not drawn in a series colour.
MIN_CONTRAST = 3.0

#: Panels to ask for when checking a canvas scales with its grid.
ROWS, COLS = 2, 3


def sources() -> list[str]:
    """Every Python file git would keep, tests included."""
    return subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()


def _relative_luminance(colour: str) -> float:
    """The luminance the contrast guidelines define, for a #rrggbb string."""
    channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(one: str, other: str) -> float:
    light, dark = sorted((_relative_luminance(one), _relative_luminance(other)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


@pytest.mark.parametrize("call", sorted(RESERVED))
def test_only_the_house_style_decides_how_a_figure_is_written(call):
    """Every figure in the repository is written by one function, so a restyle
    is one edit and no figure can quietly opt out of it."""
    allowed = {HOUSE, DECLARES_THE_RULE}
    guilty = sorted(p for p in sources() if p not in allowed and call in (REPO / p).read_text())
    assert not guilty, f"{RESERVED[call]} outside the house style: {guilty}"


def test_no_figure_script_writes_a_colour_of_its_own():
    """The palette is named. A literal is a second palette, and the second one
    is never updated with the first."""
    guilty = []
    for path in sources():
        if path == HOUSE or "/tests/" in path or path.startswith("tests/"):
            continue
        found = HEX_COLOUR.findall((REPO / path).read_text())
        if found:
            guilty.append(f"{path}: {sorted(set(found))}")
    assert not guilty, "colours written outside the palette:\n" + "\n".join(guilty)


@pytest.mark.parametrize("colour", house.SERIES)
def test_every_series_colour_is_legible_on_the_surface(colour):
    """A palette picked for paper goes muddy on a dark panel. This is the
    check that the dark one was actually chosen for the dark surface."""
    assert contrast(colour, house.PANEL) >= MIN_CONTRAST, colour


def test_the_ink_is_legible_on_the_surface():
    assert contrast(house.INK, house.PANEL) >= MIN_CONTRAST
    assert contrast(house.INK_SOFT, house.PANEL) >= MIN_CONTRAST


def test_the_surface_is_dark():
    """The whole point of the palette. A light surface would make every colour
    above the wrong choice at once."""
    assert _relative_luminance(house.SURFACE) < _relative_luminance(house.INK)
    assert _relative_luminance(house.PANEL) < _relative_luminance(house.INK)


def test_no_two_series_colours_are_the_same():
    assert len(set(house.SERIES)) == len(house.SERIES)


def test_the_meaningful_colours_are_not_reused_for_a_series_slot_that_contradicts_them():
    """Good and bad have to read as good and bad, so neither may be the colour
    a neighbouring series happens to get."""
    assert house.GOOD != house.BAD
    assert contrast(house.GOOD, house.PANEL) >= MIN_CONTRAST
    assert contrast(house.BAD, house.PANEL) >= MIN_CONTRAST


def test_the_style_names_a_face_the_tools_have():
    """A missing font does not fail: matplotlib falls back and the figure
    comes out in something else, which is the kind of drift nobody sees."""
    pytest.importorskip("matplotlib")
    from matplotlib import font_manager

    available = {f.name for f in font_manager.fontManager.ttflist}
    assert set(house.FONT_STACK) & available, f"none of {house.FONT_STACK} is installed"
    assert set(house.MONO_STACK) & available, f"none of {house.MONO_STACK} is installed"


def test_applying_the_style_sets_what_it_declares():
    pytest.importorskip("matplotlib")
    import matplotlib

    house.use()
    for key, value in house.rc().items():
        got = matplotlib.rcParams[key]
        # Some settings are normalised to a list of alternatives on the way in.
        want = [value] if isinstance(got, list) and not isinstance(value, list) else value
        assert got == want, key


def test_a_canvas_grows_with_its_panels():
    """So a four-panel figure has panels the size of a one-panel figure,
    rather than four cramped ones."""
    pytest.importorskip("matplotlib")
    import matplotlib.pyplot as plt

    fig, axes = house.canvas(ROWS, COLS)
    width, height = fig.get_size_inches()
    assert axes.shape == (ROWS, COLS)
    assert width == pytest.approx(house.PANEL_SIZE[0] * COLS)
    assert height == pytest.approx(house.PANEL_SIZE[1] * ROWS)
    plt.close(fig)


def test_saving_writes_the_file_and_lets_go_of_it(tmp_path):
    """A script drawing several figures would otherwise hold them all open."""
    pytest.importorskip("matplotlib")
    import matplotlib.pyplot as plt

    fig, _ = house.canvas()
    target = house.save(fig, tmp_path / "nested" / "figure.png")
    assert target.is_file() and target.stat().st_size > 0
    assert not plt.get_fignums()
