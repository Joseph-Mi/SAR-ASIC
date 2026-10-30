"""What the corner acceptance measures, as a table that can be drawn.

The acceptance asserts a yes or a no per corner. That is the right shape for
a gate and the wrong shape for a reader: it cannot say how close the passing
corners came, and when one fails it cannot say what would fix it. This runs
the same block, at the same inputs, and records the numbers instead -- how
large the array is at each corner, what time constant that gives the sampling
loop, the clock the loop's own law asks for, and how many codes the loop gets
wrong at the clock every corner actually runs at.

Then it does the one thing the acceptance cannot do at all: it sweeps the
clock at the corner that fails. A gate that says "this corner is wrong" and a
sweep that says "it comes right at two and a half times the clock, and an
ideal reference fixes it at one" are different kinds of evidence, and only
the second one points at the reference pin.

The block is `bench.at_corner`, which the acceptance imports too -- so this
cannot quietly drift into drawing a different circuit. The reference-pin
diagnosis it produces is the open finding's, and the figure drawn from it is
`circuit_plots.plot_corners`.

Expensive: every row is a batch of closed-loop conversions with transistor
switches and the controller compiled into the deck, so the whole table is
about an hour. It is a committed artifact for that reason.
"""

from __future__ import annotations

import argparse
import pathlib
from dataclasses import replace

import cosim
import loop
from bench import SKY130_CORNERS, SLOWEST_SAMPLING, Block, at_corner
from interface import N_BITS
from measure import first_trial_error, law_clock, sampling_tau
from sar import VCM_FRACTION, ideal_units, sar_convert
from sweep import EDGE_OFFSET_LSB, VREF, carry_codes, lsb

REPO = next(p for p in pathlib.Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
CONTROLLER = REPO / "hdl" / "rtl" / "sar_fsm.v"
BASELINE = pathlib.Path(__file__).with_name("corner_baseline.txt")

FEMTO, PICO, NANO = 1e-15, 1e-12, 1e-9

#: Where in a code the inputs sit. Mid-code, because a criterion whose margin
#: is finer than the offset it is measuring reports the measurement.
MID_CODE = 0.5

#: Multiples of the shared clock the failing corner is retried at. They
#: bracket the answer rather than find it exactly: what the figure has to
#: show is that the corner comes right somewhere above twice the clock
#: sampling asks for, which is a different path binding and not a margin.
MULTIPLES = (1.0, 1.25, 1.5, 2.0, 2.5, 3.0)

#: The reference's series resistance when the board decouples it at the pin,
#: which is the fix DD-10 already requires for `vcm`. Run as a row of its own
#: at the shared clock: if the codes come right with the pin taken out of the
#: reference's path and nothing else changed, the reference pin is what the
#: corner is failing on.
IDEAL_REFERENCE = 0.0

COLUMNS = (
    "corner",
    "vdd",
    "temp",
    "caps",
    "cu_ff",
    "ctot_pf",
    "tau_ns",
    "own_clock_ns",
    "r_vref",
    "mult",
    "wrong",
    "of",
)


def inputs_at(n_bits: int) -> list[float]:
    """Mid-code inputs either side of every carry, and mid-scale.

    The acceptance's own inputs: the carries are where a conversion changes
    the most bits at once, so they are where a settling shortfall shows first.
    """
    step = lsb(n_bits)
    return [(k + side * MID_CODE) * step for k in carry_codes(n_bits) for side in (-1, +1)] + [
        MID_CODE * step
    ]


def wrong_codes(library, workdir: pathlib.Path, block: Block, clock: float) -> tuple[int, int]:
    """How many of the acceptance's codes the loop gets wrong, and of how many.

    The model is told the block's own measured offset, exactly as the
    acceptance tells it: what is being counted is error the converter has
    left once a calibration has removed the part it can.
    """
    offset = first_trial_error(workdir, block, VCM_FRACTION * VREF, clock)
    vins = inputs_at(N_BITS)
    got = loop.convert(vins, library, workdir, block, clock)
    units = ideal_units(N_BITS)
    want = [sar_convert(vin, units, VREF, cmp_offset=-offset)[0] for vin in vins]
    return sum(a != b for a, b in zip(got.codes, want, strict=True)), len(vins)


def row(corner, block: Block, clock: float, mult: float, wrong: int, of: int, tau: float) -> dict:
    return {
        "corner": corner.process,
        "vdd": corner.vdd,
        "temp": corner.temp,
        "caps": corner.caps,
        "cu_ff": block.unit.farads / FEMTO,
        "ctot_pf": block.unit.farads * 2**N_BITS / PICO,
        "tau_ns": tau / NANO,
        "own_clock_ns": clock / NANO,
        "r_vref": block.r_vref,
        "mult": mult,
        "wrong": wrong,
        "of": of,
    }


def sweep(workdir: pathlib.Path, library) -> list[dict]:
    """Every corner at the shared clock, then the failing one swept."""
    tolerance = EDGE_OFFSET_LSB * lsb(N_BITS)
    shared_block = at_corner(SLOWEST_SAMPLING)
    shared = law_clock(workdir, shared_block, tolerance)
    rows = []
    for corner in SKY130_CORNERS:
        block = at_corner(corner)
        tau = sampling_tau(workdir, block)
        wrong, of = wrong_codes(library, workdir, block, shared)
        rows.append(row(corner, block, shared, 1.0, wrong, of, tau))
        print(f"  {corner} at the shared clock: {wrong}/{of} wrong", flush=True)

    # The corner the acceptance xfails, retried two ways: longer, and with
    # the reference's pin taken out. One of them says what the other means.
    tau = sampling_tau(workdir, shared_block)
    for mult in MULTIPLES:
        if mult == 1.0:
            continue
        wrong, of = wrong_codes(library, workdir, shared_block, shared * mult)
        rows.append(row(SLOWEST_SAMPLING, shared_block, shared * mult, mult, wrong, of, tau))
        print(f"  slowest at {mult:g}x the clock: {wrong}/{of} wrong", flush=True)

    decoupled = replace(shared_block, r_vref=IDEAL_REFERENCE)
    wrong, of = wrong_codes(library, workdir, decoupled, shared)
    rows.append(row(SLOWEST_SAMPLING, decoupled, shared, 1.0, wrong, of, tau))
    print(f"  slowest with the reference at the array: {wrong}/{of} wrong", flush=True)
    return rows


def format_table(rows: list[dict]) -> str:
    """Fixed-width and fixed-precision, because this file is diffed."""
    widths = {c: max(len(c), len("-0.0000")) for c in COLUMNS}
    out = [
        f"# bits={N_BITS} inputs=mid-code either side of every carry, and mid-scale",
        f"# clock is shared across corners, from {SLOWEST_SAMPLING}",
        "  ".join(c.rjust(widths[c]) for c in COLUMNS),
    ]
    for r in rows:
        cells = []
        for c in COLUMNS:
            v = r[c]
            cells.append(
                (v if isinstance(v, str) else f"{v:g}" if isinstance(v, int) else f"{v:.4f}").rjust(
                    widths[c]
                )
            )
        out.append("  ".join(cells))
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=pathlib.Path, default=pathlib.Path("build/corners"))
    parser.add_argument("--out", type=pathlib.Path, default=BASELINE)
    args = parser.parse_args()

    args.work.mkdir(parents=True, exist_ok=True)
    library = cosim.build(CONTROLLER, args.work / "rtl", {"N_BITS": N_BITS})
    rows = sweep(args.work, library)
    table = format_table(rows)
    args.out.write_text(table)
    print(table, end="")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
