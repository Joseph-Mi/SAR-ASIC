"""What the unit capacitor should be drawn at, and what each size costs.

The open question this answers is not what the unit is worth -- that is read
out of the process (`sky130.mim_unit`) and checked against the capacitor
ngspice builds. It is what side it should be *drawn* at, which nobody has
decided: 4 um2 was taken for the smallest the process would draw and is not,
since no deck states a minimum area for the MiM and the only size rule is a
minimum width of one micrometre.

Nothing here is simulated and nothing is random. Every column is arithmetic on
facts declared elsewhere -- the process's own capacitance and drawing rules,
the pin resistance the platform specifies, the laws in `model/` -- so this is
a table of consequences rather than a measurement, and it is committed so that
a change in any of those facts shows up as a diff in it.

What each point reports:

  c_unit, c_total  the array the size buys, at the typical capacitance corner
  sigma_rel        matching of one unit, Pelgrom on the declared coefficient
  sigma_dnl_msb    what that is worth at the transition where it is worst
  noise_lsb        kT/C against the LSB it has to hide under
  block_group      the square array plus its dummy ring and the keep-away,
  block_inter      branches grouped and branches interleaved
  swing_gain       what the top switch's diffusion leaves the comparator
  tau_fixed_ns     the sampling loop at the slowest corner, switch left as is
  w_top_um         the narrowest top switch that still holds today's clock
  tau_min_ns       the loop at that switch, which is today's unless the
                   process minimum was reached first
  inject_scaled    the switch's charge on the array at that width, against
                   today's design
  inject_fixed     the same with the top switch left at the width it is

Two of those need saying plainly.

**The trade is not matching.** Every size here leaves the MSB's spread far
inside half an LSB and kT/C far under the LSB. What moves is area and what the
switch's charge is worth on a smaller array -- and those pull opposite ways,
because a smaller array settles faster, which buys back a narrower top switch,
which injects less. `inject_scaled` is that design; `inject_fixed` is what
happens if the switch is left alone and the conversion is run faster instead.

**The parasitic here is a floor, not the number.** `swing_gain` counts the top
switch's own diffusion and nothing else. The comparator's input pair and the
routing over the array are both on that node and neither is declared anywhere
yet, so the real division is worse than this column says. It is reported
because it moves with the size being chosen, and the rest does not.
"""

from __future__ import annotations

import argparse
import pathlib
from dataclasses import dataclass, field

import sky130
import study_points
import template
import tinytapeout
from interface import N_BITS
from metrics import sigma_dnl_msb_analytic
from noise import sampled_noise_lsb
from settling import sampling_loop_resistance

BASELINE = pathlib.Path(__file__).with_name("unit_baseline.txt")

#: Which corner the resistances are read at. The clock is set by the slowest
#: sampling corner (M3 Step 6), so that is the one a size has to survive.
CORNER = "worst"

#: The capacitance corner the farads are quoted at. The spread across corners
#: is wide and is the same multiplier on every row, so it moves no decision
#: and is left out of a table that exists to compare rows.
CAP_CORNER = "typical"

#: Micro and nano, so the table reads in the units a person says out loud.
FEMTO, PICO, NANO = 1e15, 1e12, 1e9


@dataclass(frozen=True)
class Study:
    """Every knob, named once."""

    #: Sides to draw the unit at, micrometres. The process's own minimum
    #: width is the floor and is included, because the question is whether
    #: anything stops the array going there.
    sides: tuple[float, ...] = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)
    n_bits: int = N_BITS
    vref: float = 1.0
    #: How many units the array holds, and how wide a dummy ring surrounds it.
    ring: int = 1
    columns: tuple[str, ...] = field(
        default=(
            "side_um",
            "c_unit_fF",
            "c_total_pF",
            "sigma_rel",
            "sigma_dnl_msb",
            "noise_lsb",
            "block_group",
            "block_inter",
            "swing_gain",
            "tau_fixed_ns",
            "w_top_um",
            "tau_min_ns",
            "inject_scaled",
            "inject_fixed",
        )
    )


def units(study: Study) -> int:
    """How many unit capacitors the array is, the dummy aside."""
    return 2**study.n_bits


def total_capacitance(side: float, study: Study) -> float:
    """The array at that unit size, farads."""
    return units(study) * sky130.mim_capacitance(side, side, CAP_CORNER)


def top_switch_ohms(width: float) -> float:
    """What the top switch presents at that width, ohms.

    Scaled from the width it was measured at, because resistance goes as one
    over width and the measurement is of this switch passing this design's
    common mode -- a resistance without its bias beside it is not a number,
    which is why the declared one carries both.
    """
    if width <= 0.0:
        raise ValueError(f"{width} um is not a width")
    return sky130.TOP_SWITCH_OHMS[CORNER] * sky130.TOP_SWITCH_WIDTH / width


def sampling_tau(side: float, width: float, study: Study) -> float:
    """The sampling loop's time constant, seconds.

    Both pins are in the loop and the switch is between them, so the array
    charges through all three in series.
    """
    resistance = sampling_loop_resistance(
        tinytapeout.R_PIN, top_switch_ohms(width), tinytapeout.R_PIN
    )
    return resistance * total_capacitance(side, study)


def narrowest_top_switch(side: float, study: Study) -> float:
    """The narrowest top switch that still settles inside today's time
    constant, micrometres.

    The point of asking. A smaller array settles faster at the same switch,
    so the speed can be given back as a narrower switch instead -- and the
    switch's width is what its charge on the top plate is proportional to.
    Returns the process minimum in both of the cases that end there: when
    the arithmetic asks for less than the process will draw, and when a unit
    larger than today's leaves the loop no room at all -- the pins are fixed
    at 500 ohms each and a big enough array exceeds the budget before the
    switch is reached. The narrowest switch is the best either can do, and
    `tau_min_ns` is then what the clock actually becomes.
    """
    budget = reference_tau(study) / total_capacitance(side, study)
    allowance = budget - 2 * tinytapeout.R_PIN
    if allowance <= 0.0:
        return sky130.W_MIN
    width = sky130.TOP_SWITCH_OHMS[CORNER] * sky130.TOP_SWITCH_WIDTH / allowance
    return max(width, sky130.W_MIN)


def reference_tau(study: Study) -> float:
    """Today's sampling loop, which every size is held to."""
    return sampling_tau(sky130.mim_side(), sky130.TOP_SWITCH_WIDTH, study)


def injection_ratio(side: float, width: float, study: Study) -> float:
    """What the top switch's charge is worth on the top plate, against today.

    A ratio and not a figure in LSB, deliberately. The step is the charge the
    channel holds divided by the array it lands on; the charge goes as the
    switch's width, so the whole of it is `width / c_total` and the constant
    cancels. Quoting it absolutely would need an oxide capacitance this
    project has not measured, and would say no more than this does.
    """
    reference = sky130.TOP_SWITCH_WIDTH / total_capacitance(sky130.mim_side(), study)
    return (width / total_capacitance(side, study)) / reference


def run_point(study: Study, side: float) -> dict:
    """One candidate size, and everything that follows from it."""
    if side < sky130.MIM_WIDTH_MIN:
        raise ValueError(f"{side} um is below the {sky130.MIM_WIDTH_MIN} um the process draws")
    total = total_capacitance(side, study)
    sigma_rel = sky130.CAP_A_C / (100.0 * side)
    narrow = narrowest_top_switch(side, study)
    parasitic = sky130.diffusion_capacitance(narrow)
    blocks = {
        shared: sky130.mim_keep_out(
            sky130.mim_array_extent(units(study), side, ring=study.ring, shared=shared)
        )
        for shared in (True, False)
    }
    return {
        "side_um": side,
        "c_unit_fF": sky130.mim_capacitance(side, side, CAP_CORNER) * FEMTO,
        "c_total_pF": total * PICO,
        "sigma_rel": sigma_rel,
        "sigma_dnl_msb": sigma_dnl_msb_analytic(study.n_bits, sigma_rel),
        "noise_lsb": sampled_noise_lsb(total, study.n_bits, study.vref),
        "block_group": blocks[True],
        "block_inter": blocks[False],
        "swing_gain": total / (total + parasitic),
        "tau_fixed_ns": sampling_tau(side, sky130.TOP_SWITCH_WIDTH, study) * NANO,
        "w_top_um": narrow,
        "tau_min_ns": sampling_tau(side, narrow, study) * NANO,
        "inject_scaled": injection_ratio(side, narrow, study),
        "inject_fixed": injection_ratio(side, sky130.TOP_SWITCH_WIDTH, study),
    }


def sweep(study: Study) -> list[dict]:
    return [run_point(study, side) for side in study.sides]


def format_table(study: Study, rows: list[dict]) -> str:
    """The table, with the facts it was computed from in its header.

    The strip is in the header rather than in a column because it is the same
    number on every row and it is what two of the columns are read against:
    a block wider than it does not fit, and the table would otherwise have to
    be read beside a document to be read at all.
    """
    _, height = template.analog_strip()
    widths = study_points.column_widths(study.columns)
    out = [
        f"# bits={study.n_bits} vref={study.vref} ring={study.ring} "
        f"strip={height:g}um corner={CORNER} cap_corner={CAP_CORNER}",
        "  ".join(c.rjust(widths[c]) for c in study.columns),
    ]
    for row in rows:
        out.append("  ".join(f"{row[c]:.6f}".rjust(widths[c]) for c in study.columns))
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sides", type=float, nargs="+", default=Study.sides)
    parser.add_argument("--bits", type=int, default=Study.n_bits)
    parser.add_argument("--vref", type=float, default=Study.vref)
    parser.add_argument("--ring", type=int, default=Study.ring)
    parser.add_argument("--out", type=pathlib.Path, default=BASELINE)
    args = parser.parse_args()

    study = Study(sides=tuple(args.sides), n_bits=args.bits, vref=args.vref, ring=args.ring)
    if study != Study() and args.out == BASELINE:
        parser.error(
            f"refusing to write {BASELINE.name} from a non-default study -- the "
            "committed baseline is what the regression test compares against. "
            "Pass --out to write an exploratory run somewhere else."
        )

    table = format_table(study, sweep(study))
    args.out.write_text(table)
    print(table, end="")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
