"""How every figure in this repository looks.

Contract: nothing else chooses a colour, a font, a weight, a type size, a
backend or a save option. A script asks for a canvas, draws on it, and hands
it back to be saved; it chooses only how many panels it needs and their
aspect, and the look lives here. So one edit restyles every figure at once, and two
pictures of the same quantity cannot end up in different palettes -- which is
what makes a set of figures readable as a set rather than as a pile.

The surface is dark because these are read on a screen, next to a terminal and
an editor that are also dark, and a white rectangle in that company is the
brightest thing on the display. The series colours are chosen for contrast
against that surface, not against paper: the palette a light theme wants is
too dark here, and inverting a light figure gives muddy fills and grey text.

matplotlib is imported inside each function rather than at module scope. The
digital half's checks install only the pinned Python dependencies, matplotlib
is not among them, and a module-scope import would make this file -- and
everything that reads a constant from it -- un-importable there.
"""

from __future__ import annotations

import pathlib

#: Preferred faces, best first. A humanist sans reads better at small sizes
#: than the geometric default, and every name here is one the tool image
#: carries, so the first is the one that gets used and the rest are what keep
#: a figure legible somewhere else.
FONT_STACK = ("Lato", "Ubuntu Sans", "Liberation Sans", "DejaVu Sans")
MONO_STACK = ("Ubuntu Mono", "Liberation Mono", "DejaVu Sans Mono")

#: The page, the panel, and the ink on them.
SURFACE = "#121417"
PANEL = "#1a1d21"
INK = "#e9e7e4"
INK_SOFT = "#9aa0a6"
RULE = "#3c4147"
GRID = "#262a2f"

#: Series colours, in the order they are handed out. Distinguishable from each
#: other and from the surface, and ordered so a two-series figure gets the
#: pair furthest apart in hue.
SERIES = (
    "#6cb6ff",
    "#ffa657",
    "#56d364",
    "#e3b341",
    "#ff9bce",
    "#56d4dd",
    "#b39dff",
    "#ff7b72",
)

#: Colours that carry a meaning rather than an index. A figure that marks a
#: limit, a pass and a failure uses these, so the same thing is the same
#: colour in every figure.
GOOD = "#56d364"
WARN = "#e3b341"
BAD = "#ff7b72"
BOUND = "#c9d1d9"
MODEL = INK_SOFT

#: Weights. A bound is thinner than a measurement, and a guide thinner again,
#: so the eye reads the data first.
LINE = 1.6
BOUND_WIDTH = 1.1
THIN = 0.7

#: Type sizes.
FONT_SMALL = 8
FONT_LABEL = 9.5
FONT_TITLE = 12

#: How solid a shaded region is, and how solid a grid line.
SHADE_ALPHA = 0.14
GRID_ALPHA = 0.55

#: Pixels per inch. High enough that a screenshot of a panel stays readable.
DPI = 160

#: Default canvas, inches, for one panel. Multi-panel canvases scale from it.
PANEL_SIZE = (7.0, 4.2)


def rc() -> dict[str, object]:
    """Every rcParam the house style sets.

    Returned rather than applied so a caller can see the whole of it, and so
    the test that asserts a figure script sets nothing of its own has
    something to compare against.
    """
    from cycler import cycler

    return {
        "font.family": "sans-serif",
        "font.sans-serif": list(FONT_STACK),
        "font.monospace": list(MONO_STACK),
        "font.size": FONT_LABEL,
        "figure.facecolor": SURFACE,
        "figure.edgecolor": SURFACE,
        "figure.dpi": DPI,
        "figure.titlesize": FONT_TITLE,
        "figure.titleweight": "semibold",
        "savefig.facecolor": SURFACE,
        "savefig.edgecolor": SURFACE,
        "savefig.dpi": DPI,
        "savefig.bbox": "tight",
        "axes.facecolor": PANEL,
        "axes.edgecolor": RULE,
        "axes.labelcolor": INK,
        "axes.titlecolor": INK,
        "axes.titlesize": FONT_LABEL + 1,
        "axes.titleweight": "semibold",
        "axes.labelsize": FONT_LABEL,
        "axes.linewidth": THIN,
        "axes.grid": True,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.prop_cycle": cycler(color=list(SERIES)),
        "grid.color": GRID,
        "grid.linewidth": THIN,
        "grid.alpha": GRID_ALPHA,
        "text.color": INK,
        "xtick.color": INK_SOFT,
        "ytick.color": INK_SOFT,
        "xtick.labelsize": FONT_SMALL,
        "ytick.labelsize": FONT_SMALL,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "lines.linewidth": LINE,
        "lines.markersize": 4.0,
        "lines.markeredgewidth": 0.0,
        "legend.frameon": True,
        "legend.facecolor": PANEL,
        "legend.edgecolor": RULE,
        "legend.framealpha": 0.9,
        "legend.fontsize": FONT_SMALL,
        "legend.labelcolor": INK,
    }


def use() -> None:
    """Apply the style, and pick a backend that needs no display.

    Every figure here is written to a file from a script or a test, so there
    is never a window to open and a default backend that looks for one fails
    in a container.
    """
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams.update(rc())


def canvas(rows: int = 1, cols: int = 1, size=PANEL_SIZE, **kwargs):
    """A styled figure and its axes, sized from the panel count.

    `size` is one panel; the canvas grows with the grid, so a four-panel
    figure has panels the same size as a one-panel figure rather than four
    cramped ones.
    """
    use()
    import matplotlib.pyplot as plt

    width, height = size
    return plt.subplots(rows, cols, figsize=(width * cols, height * rows), **kwargs)


def bound(ax, value: float, label: str | None = None, axis: str = "y", color: str = BOUND) -> None:
    """A limit, drawn as a limit: dashed, thinner than the data, and labelled
    on the axis it constrains.

    Bounds recur across these figures -- a tolerance, a rail, a rate the pin
    allows -- and a bound that looks like a series is read as one.
    """
    line = ax.axhline if axis == "y" else ax.axvline
    line(value, color=color, lw=BOUND_WIDTH, ls="--", zorder=1.5)
    if label:
        if axis == "y":
            ax.annotate(
                label,
                (0.995, value),
                xycoords=("axes fraction", "data"),
                ha="right",
                va="bottom",
                fontsize=FONT_SMALL,
                color=color,
            )
        else:
            # Offset off the line rather than centred on it: a vertical bound
            # is usually drawn through data, and a label sitting on the rule
            # is unreadable against it.
            ax.annotate(
                label,
                (value, 0.99),
                xycoords=("data", "axes fraction"),
                textcoords="offset points",
                xytext=(-4, 0),
                ha="right",
                va="top",
                rotation=90,
                fontsize=FONT_SMALL,
                color=color,
            )


def note(ax, text: str, where=(0.02, 0.96), color: str = INK_SOFT) -> None:
    """A remark placed in the panel it belongs to, in the quieter ink."""
    ax.annotate(
        text,
        where,
        xycoords="axes fraction",
        ha="left",
        va="top",
        fontsize=FONT_SMALL,
        color=color,
    )


def save(fig, path) -> pathlib.Path:
    """Write the figure and release it.

    The only place a figure is written. Closing it here is what keeps a script
    that draws several from holding them all open.
    """
    import matplotlib.pyplot as plt

    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target)
    plt.close(fig)
    return target
