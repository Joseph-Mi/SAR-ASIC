"""Where the designed block's code transitions actually sit, at each corner.

The corner acceptance answers "are the codes right", which is the right
question for a gate and the wrong one for a diagnosis: when a code is wrong it
cannot say by how much, and when every code is right it cannot say how nearly
they were not. This locates the transitions themselves, by bisecting the real
controller running the real block, so the error has a magnitude and a shape.

It exists because a finding was built on a proxy and the proxy was wrong.
`measure.first_trial_error` reads the top plate at the *first* trial, where
the plate's excursion scales with the input -- so its error varies strongly
across the range and looks like a gain error of about 0.7 LSB. A threshold is
decided by the *last* trials, where the plate has converged to within an LSB
of Vcm, and there the error is nearly constant: measured end to end it moves
0.094 LSB, of which 0.055 survives a one-point calibration. The proxy
measures a real quantity that is not the one deciding codes, and reading it as
though it were cost this project a wrong diagnosis and two wrong fixes.

Expensive: every bisection round is a batch of closed-loop conversions with
transistor switches and the controller compiled into the deck. It is a
committed artifact for that reason, and `make thresholds` regenerates it.
"""

from __future__ import annotations

import argparse
import math
import pathlib

import cosim
import loop
from bench import SKY130_CORNERS, Block, at_corner
from interface import N_BITS
from measure import first_trial_error, law_clock
from ngspice import BATCH
from sar import VCM_FRACTION, ideal_units, sar_convert
from sweep import EDGE_OFFSET_LSB, VREF, lsb

REPO = next(p for p in pathlib.Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
CONTROLLER = REPO / "hdl" / "rtl" / "sar_fsm.v"
BASELINE = pathlib.Path(__file__).with_name("threshold_baseline.txt")

#: How far either side of the model's threshold the search starts, in LSB.
#: Wider than the short loop's bench uses, because the offset at the slow
#: corner is about half an LSB on its own and a window that does not bracket
#: the answer reports its own edge, which reads exactly like a measurement.
WINDOW = 1.0

#: How finely it ends, in LSB. The floor under everything here: a claim finer
#: than this is reading the grid rather than the circuit.
RESOLUTION = 0.0125

#: The transitions located. Spread over the range rather than exhaustive --
#: every one of the 1023 would be a thousand conversions a round -- and
#: weighted to the ends, where a gain error would show if there were one.
#: 896 is here because the acceptance cannot reach it: `sweep.carry_codes` is
#: the powers of two and the top code, so it probes every carry *width* from
#: one bit to ten and every one of them with no upper branch already on.
#: 896 is 0b1110000000 -- eight bits changing while branches 8 and 9 are
#: already at the reference, which is the hardest case for the reference path
#: and outside that set.
CODES = (1, 64, 128, 256, 512, 768, 896, 1000, 1023)

#: Conversions per input, of which only the last is read.
#:
#: A conversion's code depends on the input of the conversion *before* it,
#: which Step 4b predicts (sampling kicks vcm by charge proportional to the
#: change in input) and which is measured here at ss/-40/typical on this
#: corner's own clock: a +895 LSB jump between conversions costs three codes,
#: +384 and +128 cost one each, and jumps of +0.125, -0.5 and -127 cost
#: nothing. The first conversion after a reset is always wrong, by three
#: codes at this input.
#:
#: Bisecting every code in one batch jumps hundreds of LSB between
#: neighbours, so the first version of this measured that kick layered on the
#: thresholds. A low reading walks the search upward, and it reported code
#: 896 at 896.125 -- 0.69 LSB away from every other threshold at that corner,
#: and over the half-LSB budget -- where the settled answer is 895.81.
#: Repeating each input makes it its own predecessor, so the kick is zero by
#: construction rather than by hope.
#:
#: Three rather than two because the last two are the check: they share a
#: predecessor, so they must agree, and `locate` raises when they do not
#: instead of averaging over an instrument that is still moving.
SETTLE = 3

COLUMNS = ("corner", "vdd", "temp", "caps", "code", "loop_lsb", "model_lsb", "error_lsb")


def locate(
    workdir: pathlib.Path,
    block: Block,
    library,
    clock: float,
    codes=CODES,
    n_bits: int = N_BITS,
    centre: float = 0.0,
) -> dict[int, float]:
    """Where each of `codes` transitions, in LSB, for this block.

    All of them are bisected at once, one batch of conversions per round
    rather than per threshold: what this costs is ngspice runs, and advancing
    every search together makes that the number of rounds instead of their
    product.

    Each input is converted `SETTLE` times and only the last read, because a
    conversion's code depends on the input before it and bisecting every code
    together is the worst case for that. See `SETTLE`.

    `centre` shifts the search, in LSB, and is how a block whose offset
    exceeds the window is measured at all -- pass the offset and the window
    brackets what is left of the error rather than the offset itself. The
    generic designed block sits 3.4 LSB low, so a search centred on the ideal
    grid never reaches it.

    Refuses an answer at the edge of its own window rather than returning it.
    A search that does not bracket its answer converges on whichever end it
    was walking toward, and reports a column of identical numbers with a
    spread of exactly zero -- which reads like a beautifully consistent
    measurement and is the shape of the window. This happened here before the
    check existed.
    """
    step = lsb(n_bits, VREF)
    low = {k: (k + centre - WINDOW) * step for k in codes}
    high = {k: (k + centre + WINDOW) * step for k in codes}
    per_round = 1 + SETTLE * len(codes)
    if per_round > BATCH:
        raise ValueError(
            f"a round is {per_round} conversions against a batch of {BATCH}: "
            "`loop.convert` runs each batch from reset, so a round split across "
            "two batches puts a reset in the middle of it and the conversion "
            "after that reset is read as a measurement. Shorten `codes`."
        )
    for _ in range(math.ceil(math.log2(2 * WINDOW / RESOLUTION))):
        mid = {k: (low[k] + high[k]) / 2 for k in codes}
        # One throwaway in front: the batch runs from reset and the first
        # conversion after a reset is wrong, so no reading sits in that slot.
        order = [mid[codes[0]]] + [mid[k] for k in codes for _ in range(SETTLE)]
        read = loop.convert(order, library, workdir, block, clock).codes[1:]
        for i, k in enumerate(codes):
            repeats = read[SETTLE * i : SETTLE * (i + 1)]
            if repeats[-1] != repeats[-2]:
                raise ValueError(
                    f"code {k} is not settled after {SETTLE} conversions of the "
                    f"same input: {repeats}. The last two share a predecessor -- "
                    "themselves -- so they can only differ if the input has not "
                    "settled within the clock. Raise SETTLE, or the clock is too "
                    "short for this corner."
                )
            # At or above the code means the transition is at or below here.
            if repeats[-1] >= k:
                high[k] = mid[k]
            else:
                low[k] = mid[k]
    found = {k: (low[k] + high[k]) / 2 / step for k in codes}
    stuck = {k: v - k for k, v in found.items() if abs(v - k - centre) > WINDOW - 2 * RESOLUTION}
    if stuck:
        raise ValueError(
            f"the search reached its own window at {sorted(stuck)}: thresholds "
            f"{ {k: round(v, 4) for k, v in stuck.items()} } LSB off the model against a "
            f"window of +-{WINDOW} LSB centred on {centre:+g}. Widen it, or centre it "
            "on the block's measured offset -- an answer at the edge is the edge."
        )
    return found


def model_threshold(k: int, n_bits: int = N_BITS) -> float:
    """Where the model puts the same transition, read the way the loop's is."""
    step = lsb(n_bits, VREF)
    units = ideal_units(n_bits)
    fine = RESOLUTION / 10
    points = int(2 * WINDOW / fine) + 1
    return next(
        k + (-WINDOW + i * fine)
        for i in range(points)
        if sar_convert((k + (-WINDOW + i * fine)) * step, units, VREF)[0] >= k
    )


def sweep(workdir: pathlib.Path, library, corners=SKY130_CORNERS) -> list[dict]:
    rows = []
    for corner in corners:
        block = at_corner(corner)
        step = lsb(N_BITS, VREF)
        clock = law_clock(workdir, block, EDGE_OFFSET_LSB * step)
        # Centred on this corner's own offset, so the window brackets what is
        # left of the error rather than the offset. Corners differ by several
        # LSB of offset and one window centred on the ideal grid does not fit
        # them all.
        offset = first_trial_error(workdir, block, VCM_FRACTION * VREF, clock) / step
        found = locate(workdir, block, library, clock, centre=offset)
        for k in CODES:
            rows.append(
                {
                    "corner": corner.process,
                    "vdd": corner.vdd,
                    "temp": corner.temp,
                    "caps": corner.caps,
                    "code": k,
                    "loop_lsb": found[k],
                    "model_lsb": model_threshold(k),
                    "error_lsb": found[k] - model_threshold(k),
                }
            )
        print(f"  {corner}: located {len(CODES)} thresholds at {clock * 1e9:.2f} ns", flush=True)
    return rows


def residual_after_offset(rows: list[dict], corner: str, caps: str) -> float:
    """What a one-point calibration at mid-scale leaves, in LSB.

    The quantity the acceptance's half-LSB criterion has to clear, and the
    one the record got wrong: it is the *spread* of the errors and not the
    errors themselves, because an offset common to every threshold is what
    the calibration removes.
    """
    here = [r for r in rows if r["corner"] == corner and r["caps"] == caps]
    mid = next(r["error_lsb"] for r in here if r["code"] == 2 ** (N_BITS - 1))
    return max(abs(r["error_lsb"] - mid) for r in here)


def format_table(rows: list[dict]) -> str:
    """Fixed-width and fixed-precision, because this file is diffed."""
    widths = {c: max(len(c), len("-0.000000")) for c in COLUMNS}
    out = [
        f"# bits={N_BITS} window={WINDOW} resolution={RESOLUTION} clock=law_clock per corner",
        "  ".join(c.rjust(widths[c]) for c in COLUMNS),
    ]
    for r in rows:
        cells = []
        for c in COLUMNS:
            v = r[c]
            cell = v if isinstance(v, str) else f"{v:d}" if isinstance(v, int) else f"{v:.6f}"
            cells.append(cell.rjust(widths[c]))
        out.append("  ".join(cells))
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=pathlib.Path, default=pathlib.Path("build/thresholds"))
    parser.add_argument("--out", type=pathlib.Path, default=BASELINE)
    args = parser.parse_args()

    args.work.mkdir(parents=True, exist_ok=True)
    library = cosim.build(CONTROLLER, args.work / "rtl", {"N_BITS": N_BITS})
    rows = sweep(args.work, library)
    table = format_table(rows)
    args.out.write_text(table)
    print(table, end="")
    for corner in SKY130_CORNERS:
        left = residual_after_offset(rows, corner.process, corner.caps)
        print(f"{corner.process}/{corner.caps}: {left:.4f} LSB survives a one-point calibration")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
