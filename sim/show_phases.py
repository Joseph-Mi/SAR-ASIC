"""Watch the sampling phases hand over: the generator, drawn.

DD-11 is three sentences of prose and one picture, and this is the picture.
What it has to show is not that the lines move but that each one waits: the
top switch's line is *off* before the input switches' lines begin to fall, and
the input switches' are off before the conversion line rises. A delay chain
would produce a figure that looks much like this one and would be a different
circuit, so the off-detectors are drawn beside the lines they watch -- they
are what makes the order a property of the circuit rather than of a timing
estimate.

Drawn around the handover rather than over the whole run, because at the scale
of a sampling phase the whole interesting part is a few hundred picoseconds
and every line looks simultaneous.

Nothing is asserted here. `test_sampling_phases.py` asserts the order, at
every supply and temperature corner and with a line deliberately slowed; this
draws one run of it so the guarantee can be looked at.

Nothing here chooses how the figure looks, and nothing here imports
matplotlib: the house style owns both, so this picture matches every other in
the repository and this file stays importable where the drawing library is
not installed.
"""

from __future__ import annotations

import argparse
import pathlib

import numpy as np

import analog
import bench
import house
import ngspice
from bench import Bench, Block, Phase, Supplies
from devices import Sky130
from interface import N_BITS

REPO = next(p for p in pathlib.Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
OUT_DIR = REPO / "build" / "show"

VREF = 1.0
VDD = 1.8
PS = 1e-12

#: The process corner the generator is drawn at. sky130's own models rather
#: than the simulator's generic ones, because the gates here are sized in
#: this process -- the off-detector is a skewed inverter whose switching
#: point has to sit below where the top switch conducts, and where that point
#: sits is a property of the process's thresholds and of nothing else. Drawn
#: at typical; `test_sampling_phases.py` is what holds the order at the rest.
CORNER = "tt"

#: One panel of this figure, inches. Two stacked panels share one time axis
#: over a window a few hundred picoseconds wide, so the canvas is wide.
PANEL = (11.0, 3.8)

#: The phase lines, in the order they act, and what each one switches.
LINES = (
    ("sample", "sample", "the one input wire"),
    ("phi_top", "phi_top", "top switch"),
    ("phi_bot", "phi_bot", "input switches, NMOS"),
    ("phi_bot_n", "phi_bot_n", "input switches, PMOS"),
    ("phi_conv", "phi_conv", "conversion switches"),
)

#: The off-detectors, and the line each one watches. A detector is high while
#: the switch on its line is still conducting, so the phase it guards is held
#: until it falls -- which is the whole mechanism, and the reason this panel
#: is drawn at all.
DETECTORS = (
    ("top_on", "phi_top", "top switch still on"),
    ("bot_on", "phi_bot", "input NMOS still on"),
    ("botn_on", "phi_bot_n", "input PMOS still on"),
    ("cnv_on", "phi_conv", "conversion still on"),
)

#: Where a line counts as off, as a fraction of the supply. Below this the
#: switch on it is not conducting; it is the level the order is defined at
#: and the one `test_sampling_phases.py` measures the crossings at.
OFF_LEVEL = 0.1

#: The crossings the figure marks, as (name, node, level as a fraction of
#: the supply, edge, label). These are the two guarantees DD-11 exists to
#: make, read off the same lines at the same levels
#: `test_sampling_phases.py` asserts them at. They are also what makes this
#: deck measure something: `ngspice.run` refuses a deck that measures nothing,
#: which is the right rule -- a run with no number in it cannot be checked.
MARKS = (
    ("top_off", "phi_top", OFF_LEVEL, "fall", "top switch off"),
    ("bot_moving", "phi_bot", 1 - OFF_LEVEL, "fall", "input switches start to move"),
    ("bot_off", "phi_bot", OFF_LEVEL, "fall", "input switches off"),
    ("cnv_moving", "phi_conv", OFF_LEVEL, "rise", "conversion starts to move"),
)

#: How far either side of the top line's fall the window reaches, as a
#: multiple of the handover it is drawn to show.
LEAD, TRAIL = 0.25, 0.35

#: A guess at the handover's width, seconds, used only to find the window
#: before the waveform is known. The window is refitted to the lines once
#: they are in hand.
HANDOVER = 400e-12


def nodes() -> list[str]:
    """Every node the figure draws, as the deck spells them."""
    inside = [f"xdut.{n}" for _, n, _ in LINES[1:]]
    inside += [f"xdut.{n}" for n, _, _ in DETECTORS]
    return ["sample", *inside]


def record(
    out: pathlib.Path, vdd: float, temp: float, corner: str = CORNER
) -> tuple[np.ndarray, dict, dict]:
    """One sample, one conversion and back, keeping every line.

    Returns the time base, every line's waveform, and the crossings `MARKS`
    names -- the waveform to draw and the numbers to draw on it.
    """
    table = out.with_suffix(".txt")
    probed = nodes()
    vectors = " ".join(f"v({n})" for n in probed)
    measures = [
        f"meas tran {name} when v(xdut.{node})={level * vdd:.6g} {edge}=1"
        for name, node, level, edge, _ in MARKS
    ]
    b = Bench(
        [Phase(sample=1), Phase(), Phase(sample=1)],
        Block(
            Supplies(vdd=vdd, vref=VREF, vin=0.5 * VREF),
            N_BITS,
            unit=analog.MIM_SIZED,
            sampling=analog.NonOverlap(devices=Sky130(corner)),
            temp=temp,
        ),
        probes={},
        read=[],
        # Bare name: ngspice runs in the output's folder, and a folder's path
        # may hold characters a deck line cannot carry.
        extra_control=[f"wrdata {table.name} {vectors}", *measures],
    )
    found = ngspice.run(bench.deck(b), out.parent)
    rows = np.loadtxt(table)
    wave = {n.removeprefix("xdut."): rows[:, 2 * i + 1] for i, n in enumerate(probed)}
    return rows[:, 0], wave, {k: v[0] for k, v in found.items()}


def handover(time: np.ndarray, wave: dict, vdd: float) -> tuple[float, float]:
    """The window around the sample-to-convert handover, in seconds.

    Found from the lines rather than from the phase length: what is worth
    looking at starts when the top line leaves the rail and ends when the
    conversion line reaches it, and both of those move with the corner.
    """
    top, conv = wave["phi_top"], wave["phi_conv"]
    falling = np.nonzero(top < (1 - OFF_LEVEL) * vdd)[0]
    risen = np.nonzero(conv > (1 - OFF_LEVEL) * vdd)[0]
    if not falling.size:
        raise ValueError("the top line never left the rail -- nothing handed over")
    start = time[falling[0]]
    end = time[risen[0]] if risen.size else start + HANDOVER
    width = max(end - start, HANDOVER)
    return start - LEAD * width, end + TRAIL * width


def draw(
    time: np.ndarray, wave: dict, marks: dict, vdd: float, corner: str, out: pathlib.Path
) -> pathlib.Path:
    """The lines, and the detectors that hold each one back."""
    begin, finish = handover(time, wave, vdd)
    window = (time >= begin) & (time <= finish)
    t = time[window] / PS

    fig, (phases, guards) = house.canvas(2, 1, size=PANEL, sharex=True)

    for i, (name, node, what) in enumerate(LINES):
        phases.plot(
            t,
            wave[node][window],
            color=house.SERIES[i % len(house.SERIES)],
            lw=house.LINE,
            label=f"{name} -- {what}",
        )
    house.bound(phases, OFF_LEVEL * vdd, f"off, {OFF_LEVEL:g} of the supply")
    # The crossings, ruled through both panels: the order is a claim about
    # when these happen relative to each other, so they are drawn as the
    # figure's own x gridlines rather than annotated on one curve.
    for name, _node, _level, _edge, label in MARKS:
        when = marks[name] / PS
        for ax in (phases, guards):
            ax.axvline(when, color=house.RULE, lw=house.THIN, zorder=0.5)
        phases.annotate(
            label,
            (when, 1.0),
            xycoords=("data", "axes fraction"),
            textcoords="offset points",
            xytext=(-4, -2),
            ha="right",
            va="top",
            rotation=90,
            fontsize=house.FONT_SMALL,
            color=house.INK_SOFT,
        )
    phases.set_ylabel("volts")
    phases.legend(loc="center right", fontsize=house.FONT_SMALL)
    phases.set_title("The handover, sampling to conversion: each line waits for the one before it")

    for i, (node, watches, what) in enumerate(DETECTORS):
        guards.plot(
            t,
            wave[node][window],
            color=house.SERIES[i % len(house.SERIES)],
            lw=house.LINE,
            label=f"{node} -- {what} (watches {watches})",
        )
    guards.set_ylabel("volts")
    guards.set_xlabel("time  [ps]")
    guards.legend(loc="center right", fontsize=house.FONT_SMALL)
    guards.set_title(
        "And what each one is waiting on: a detector is high while the switch "
        "on its line still conducts,\nso the phase it guards cannot move until "
        "it falls"
    )

    fig.suptitle(
        f"Bottom-plate sampling: the phases are made on chip from one "
        f"wire (DD-11)\n"
        f"sky130 {corner}, {vdd:g} V, with the array at the unit the process "
        f"draws\n"
        "the top switch passes a constant Vcm, so its charge is an offset;\n"
        "the input switches' depends on Vin, so it is distortion -- and "
        "sealing the top plate first\n"
        "lands it on plates that are about to be driven anyway.",
    )
    fig.tight_layout()
    return house.save(fig, out)


def show(
    vdd: float = VDD, temp: float = bench.NOMINAL_TEMP, corner: str = CORNER, out=None
) -> pathlib.Path:
    """Run and draw; returns where the figure went."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = pathlib.Path(out).resolve() if out else OUT_DIR / "phases.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    time, wave, marks = record(out, vdd, temp, corner)
    return draw(time, wave, marks, vdd, corner, out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vdd", type=float, default=VDD)
    parser.add_argument("--temp", type=float, default=bench.NOMINAL_TEMP)
    parser.add_argument("--corner", default=CORNER)
    parser.add_argument("--out", help="figure path (default build/show/phases.png)")
    args = parser.parse_args()
    print(show(args.vdd, args.temp, args.corner, args.out))


if __name__ == "__main__":
    main()
