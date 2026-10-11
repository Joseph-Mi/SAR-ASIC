"""Pictures of the system: what a conversion does, and what bounds it.

The sweeps next to this file answer a question by running the model over a
grid. These do something else -- they draw what the model already says, so
that a relationship the tests assert in one line can be looked at. Nothing
here is a result in its own right, and nothing here is asserted: every curve
is the same function the tests hold the design to, drawn.

They are cheap. Every panel comes from the golden model and the physics
modules, with no circuit simulation anywhere, so the whole set redraws in
seconds and can be regenerated whenever a model changes.

Nothing here chooses how a figure looks, and nothing here imports matplotlib:
the house style owns both.
"""

from __future__ import annotations

import pathlib

import numpy as np

import house
from dynamic import codes_from_curve
from interface import N_BITS
from junction import ABRUPT, LINEARLY_GRADED, Junction, input_at_decision, swing_gain
from metrics import inl, lsb_ideal
from power import average_reference_current, rate_a_pin_can_carry, reference_charge
from protocol import DONE, EVALUATE, SAMPLE, SETTLE, conversion_sequence
from sampling import coherent_cycles, level_dependent, sampled, sweep
from sar import VCM_FRACTION, ideal_units, sar_convert, top_plate_voltage
from settling import c_seen_by_reference, residual, sampling_loop_resistance, settle_time
from spectrum import RECORD, coherent_sine, harmonic_bins, power_spectrum
from timing import MIN_LEVEL_CYCLES, edges_guaranteed
from tinytapeout import I_PIN, R_PIN

OUT_DIR = pathlib.Path("build/figures")

VREF = 1.0

#: A unit capacitor of the order the process draws, farads. Every figure in
#: absolute units scales with it; the relationships do not.
C_UNIT = 8e-15

#: Resolution the waveform diagram is drawn at. Small enough that every step
#: of a conversion is a readable tick on the axis.
DIAGRAM_BITS = 4

#: The input the waveform diagram converts, as a fraction of the reference.
#: Off every threshold, and low enough that the search goes both ways.
DIAGRAM_INPUT = 0.3

#: Inputs the swing and charge figures are drawn at: near each rail, where a
#: junction is least linear and a conversion's cost is most extreme.
LOW_INPUT, HIGH_INPUT = 0.02, 0.98

#: Panel aspects, per panel.
WIDE_PANEL = (11.0, 2.6)
ROW_PANEL = (5.0, 4.2)
SQUARE_PANEL = (5.6, 4.2)

#: How tall a control line is drawn inside its lane, leaving a gap between.
LANE_FILL = 0.72

#: Phases of a conversion, in the order they happen, and the colour each is
#: shaded. Settling is unshaded: it is the resting state between the things
#: that happen.
PHASE_COLOURS = {
    SAMPLE: house.SERIES[2],
    SETTLE: None,
    EVALUATE: house.SERIES[0],
    DONE: house.SERIES[3],
}

#: Fractions of Nyquist the frequency sweep visits.
FRACTIONS = (0.01, 0.05, 0.1, 0.2, 0.35, 0.5, 0.7, 0.9)

#: Sampling memory to draw the frequency figure with: a few percent of the
#: inter-sample step surviving into the conversion, and a coefficient that
#: changes by this fraction across the input range.
MEMORY, MEMORY_SLOPE = 0.02, 1.0

#: Amplitude the frequency figure offers. Below the static figure's, because
#: the memory raises the amplitude the converter sees.
BACKED_OFF = 0.45

#: Junction sizes drawn against the array, as fractions of it.
JUNCTION_FRACTIONS = (0.05, 0.2, 0.5)

#: Comparator offset the junction figure shows the amplification of, volts.
SHOWN_OFFSET = 2e-3

#: Settling tolerance the bounds figure holds a path to, in LSB.
TOLERANCE_LSB = 0.5

#: Phases a conversion takes beyond its bit trials: the sample and the
#: handover.
OVERHEAD_PHASES = 2

#: Level durations the pin-timing panel draws, in system clocks.
LEVEL_CYCLES = range(0, 7)


def _units(n_bits: int = N_BITS):
    return ideal_units(n_bits, C_UNIT)


def conversion(out_dir: pathlib.Path = OUT_DIR) -> pathlib.Path:
    """One conversion, cycle by cycle: the phases, the word, the node, the flag.

    The picture the rest of the project is written against. Every testbench
    compares waveforms to this sequence, so this is what "correct" looks like.
    """
    from matplotlib.patches import Patch

    units = ideal_units(DIAGRAM_BITS)
    vin = DIAGRAM_INPUT * VREF
    vcm = VCM_FRACTION * VREF
    steps = conversion_sequence(vin, units, VREF)
    code, _ = sar_convert(vin, units, VREF)
    x = np.arange(len(steps))

    fig, (node, word, ctrl) = house.canvas(3, 1, size=WIDE_PANEL, sharex=True)

    # Sampling holds the node at the reference; afterwards it goes wherever
    # charge conservation puts it for the word on the array.
    top = [
        vcm if s.phase == SAMPLE else top_plate_voltage(vin, s.dac_b, units, VREF) for s in steps
    ]
    node.step(x, top, where="mid", color=house.SERIES[0], label="top plate")
    node.axhline(vcm, color=house.BOUND, lw=house.BOUND_WIDTH, ls="--", label="Vcm (decides here)")
    for i, s in enumerate(steps):
        if s.decision is not None:
            node.annotate(
                str(s.decision),
                (i, top[i]),
                textcoords="offset points",
                xytext=(0, 7),
                ha="center",
                fontsize=house.FONT_SMALL,
                color=house.INK,
            )
    node.margins(y=0.3)
    node.set_ylabel("volts")
    node.set_title(
        f"One conversion at {DIAGRAM_BITS} bits: vin = {vin:.3f} V, code {code}. "
        "A decision is taken where the node crosses Vcm."
    )

    word.step(x, [s.dac_b for s in steps], where="mid", color=house.SERIES[1])
    word.axhline(code, color=house.BOUND, lw=house.BOUND_WIDTH, ls=":")
    word.set_ylabel("dac_b")
    word.set_ylim(-0.5, 2**DIAGRAM_BITS - 0.5)
    house.note(word, "never all-ground while a sample is held", (0.02, 0.2))

    lanes = (("sample", [s.sample for s in steps]), ("cmp_clk", [s.cmp_clk for s in steps]))
    lanes += (("done", [int(s.phase == DONE) for s in steps]),)
    for lane, (_name, values) in enumerate(reversed(lanes)):
        colour = house.SERIES[(len(lanes) - 1 - lane) % len(house.SERIES)]
        ctrl.step(x, lane + LANE_FILL * np.array(values), where="mid", color=colour)
    ctrl.set_yticks([lane + LANE_FILL / 2 for lane in range(len(lanes))])
    ctrl.set_yticklabels([name for name, _ in reversed(lanes)])
    ctrl.set_xlabel("conversion clock step")
    ctrl.set_xticks(x)

    # The phase of every step, shaded across all three panels, so the lanes
    # below and the node above are read against the same state.
    for ax in (node, word, ctrl):
        for i, s in enumerate(steps):
            colour = PHASE_COLOURS[s.phase]
            if colour:
                ax.axvspan(i - 0.5, i + 0.5, color=colour, alpha=house.SHADE_ALPHA, lw=0)
    # The phases go in the legend rather than above the panel: annotated in
    # place they collide with the title, and there are only three to name.
    keys = [
        Patch(facecolor=colour, alpha=house.SHADE_ALPHA, label=phase)
        for phase, colour in PHASE_COLOURS.items()
        if colour
    ]
    node.legend(handles=node.get_legend_handles_labels()[0] + keys, loc="upper right", ncol=2)

    fig.tight_layout()
    return house.save(fig, out_dir / "conversion.png")


def frequency(out_dir: pathlib.Path = OUT_DIR) -> pathlib.Path:
    """What the converter does to a tone, and what a moving input costs.

    The left panel is one record read as a spectrum; the right is the whole
    sweep. Together they make the result visible: a constant sampling memory
    is a filter and puts nothing in a harmonic bin, while one that varies with
    the signal does, and more of it the faster the input moves.
    """
    units = _units()
    flat = MEMORY
    curved = level_dependent(MEMORY, MEMORY_SLOPE, VREF)

    fig, (spec, figures) = house.canvas(1, 2, size=SQUARE_PANEL)

    cycles = coherent_cycles(0.35, RECORD)
    offered = coherent_sine(RECORD, cycles, VREF, BACKED_OFF)
    for label, coefficient in (("constant memory", flat), ("level-dependent memory", curved)):
        codes = codes_from_curve(sampled(offered, coefficient), units, VREF)
        power = power_spectrum(codes)
        # DC carries the stimulus's own offset, not the converter's answer,
        # and no figure counts it, so it is not drawn either.
        decibels = 10 * np.log10(np.maximum(power[1:], power.max() * 1e-12) / power[cycles])
        spec.plot(np.arange(1, len(power)) / len(power), decibels, lw=house.THIN, label=label)
    for order, where in harmonic_bins(cycles, RECORD).items():
        spec.axvline(where / (RECORD // 2 + 1), color=house.INK_SOFT, lw=house.THIN, ls=":")
        spec.annotate(
            f"H{order}",
            (where / (RECORD // 2 + 1), 0.02),
            xycoords=("data", "axes fraction"),
            ha="center",
            fontsize=house.FONT_SMALL,
            color=house.INK_SOFT,
        )
    spec.set_xlabel("frequency  [fraction of Nyquist]")
    spec.set_ylabel("power relative to the tone  [dB]")
    spec.set_title(f"Output spectrum at {N_BITS} bits, input at 0.35 Nyquist")
    spec.legend(loc="upper right")

    for label, coefficient, style in (("constant", flat, "-"), ("level-dependent", curved, "--")):
        rows = sweep(FRACTIONS, coefficient, unit_caps=units, vref=VREF, amplitude_frac=BACKED_OFF)
        x = [r["fraction"] for r in rows]
        figures.plot(
            x, [r["sndr"] for r in rows], style, color=house.SERIES[0], label=f"SNDR, {label}"
        )
        figures.plot(
            x, [r["sfdr"] for r in rows], style, color=house.SERIES[2], label=f"SFDR, {label}"
        )
        figures.plot(
            x, [-r["thd"] for r in rows], style, color=house.SERIES[1], label=f"-THD, {label}"
        )
    figures.set_xscale("log")
    figures.set_xlabel("input frequency  [fraction of Nyquist]")
    figures.set_ylabel("decibels")
    figures.set_title("A filter costs no distortion; a signal-dependent one does")
    figures.legend(loc="lower left", ncol=2)
    house.note(
        figures,
        "where distortion dominates, the worst spur is the\nharmonic, so SFDR and -THD coincide",
        (0.03, 0.30),
    )

    fig.suptitle(
        "Sampling memory is linear until something in the recovery path is not:\n"
        "dashed curves carry a coefficient that varies across the input range, solid ones do not"
    )
    fig.tight_layout()
    return house.save(fig, out_dir / "frequency.png")


def bounds(out_dir: pathlib.Path = OUT_DIR) -> pathlib.Path:
    """The three bounds the design is held to, each with its margin shown.

    Settling against the conversion clock, a board's hold time against the
    sampling rule, and the conversion rate against what the reference pin can
    carry. Each panel shades the side of the bound that does not work.
    """
    units = _units()
    total = float(units.sum())
    lsb = lsb_ideal(N_BITS, VREF)
    tolerance = TOLERANCE_LSB * lsb

    fig, (settle, pins, rate) = house.canvas(1, 3, size=ROW_PANEL)

    # Two paths charge through the pin: sampling charges the whole array
    # through three resistances in series, the reference charges a quarter of
    # it at the first trial.
    paths = (
        ("sampling loop", sampling_loop_resistance(R_PIN, R_PIN, R_PIN) * total, VREF),
        ("reference, first trial", R_PIN * c_seen_by_reference(total / 2, total), VREF / 2),
    )
    slowest = max(settle_time(tau, step, tolerance) for _, tau, step in paths)
    t = np.linspace(0, slowest * 1.3, 400)
    for name, tau, step in paths:
        settle.semilogy(
            t * 1e9, residual(t, tau, step) / lsb, label=f"{name}, tau {tau * 1e9:.1f} ns"
        )
    settle.set_ylim(TOLERANCE_LSB / 1e3, 2 ** (N_BITS + 1))
    settle.axhspan(TOLERANCE_LSB, 2 ** (N_BITS + 1), color=house.BAD, alpha=house.SHADE_ALPHA, lw=0)
    house.bound(settle, TOLERANCE_LSB, f"{TOLERANCE_LSB} LSB", color=house.WARN)
    house.bound(settle, slowest * 1e9, "phase", axis="x", color=house.GOOD)
    settle.set_xlabel("time into the phase  [ns]")
    settle.set_ylabel("remaining error  [LSB]")
    settle.set_title("Settling sets the phase")
    settle.legend(loc="upper right")

    cycles = np.array(LEVEL_CYCLES)
    pins.step(
        cycles, [edges_guaranteed(int(c)) for c in cycles], where="mid", color=house.SERIES[0]
    )
    pins.axhspan(-0.5, 0.5, color=house.BAD, alpha=house.SHADE_ALPHA, lw=0)
    house.bound(pins, MIN_LEVEL_CYCLES, "minimum", axis="x")
    pins.set_xlabel("level held for  [system clocks]")
    pins.set_ylabel("clock edges certain to sample it")
    pins.set_title("A board's hold time")
    house.note(
        pins,
        "a one-cycle level offers one edge,\nand it can be the one in transition",
        (0.40, 0.32),
    )

    worst = max(reference_charge(vin, units, VREF) for vin in np.linspace(0, VREF, 32))
    phase = settle_time(sampling_loop_resistance(R_PIN, R_PIN, R_PIN) * total, VREF, tolerance)
    settling_limited = 1.0 / ((N_BITS + OVERHEAD_PHASES) * phase)
    pin_limited = rate_a_pin_can_carry(worst, I_PIN)
    # Drawn from a floor rather than as bars: a bar starts at zero, and zero
    # is off the left edge of a log axis, so every bar would reach the frame.
    floor = settling_limited / 10
    rate.set_xscale("log")
    rate.set_xlim(floor, pin_limited * 3)
    for y, value, colour in (
        (0, settling_limited, house.SERIES[0]),
        (1, pin_limited, house.SERIES[1]),
    ):
        rate.hlines(y, floor, value, color=colour, lw=6)
        rate.annotate(
            f"{value:.3g} /s",
            (value, y),
            textcoords="offset points",
            xytext=(6, 0),
            va="center",
            fontsize=house.FONT_SMALL,
            color=colour,
        )
    rate.set_ylim(-0.6, 1.6)
    rate.set_yticks([0, 1])
    rate.set_yticklabels(["settling", "reference pin current"])
    rate.set_xlabel("conversions per second the bound allows")
    rate.set_title("Which bound actually binds")
    house.note(
        rate,
        f"the pin allows {pin_limited / settling_limited:.0f}x the rate settling does",
        (0.03, 0.95),
    )

    fig.suptitle("Three bounds, and the margin against each")
    fig.tight_layout()
    return house.save(fig, out_dir / "bounds.png")


def junction(out_dir: pathlib.Path = OUT_DIR) -> pathlib.Path:
    """A voltage-dependent parasitic on the top plate: what it is, and what it
    does not do.

    The right-hand panel is the result. Thresholds do not move, so a figure of
    threshold shift against code is a flat line -- and with a comparator
    offset it is a flat line somewhere else, which is an offset and not a
    nonlinearity.
    """
    units = _units()
    total = float(units.sum())
    lsb = lsb_ideal(N_BITS, VREF)

    fig, (law, swing, shift) = house.canvas(1, 3, size=ROW_PANEL)

    bias = np.linspace(0.0, VREF, 200)
    for name, grading in (("abrupt", ABRUPT), ("linearly graded", LINEARLY_GRADED)):
        probe = Junction(c_zero=1.0, grading=grading)
        law.plot(bias, probe.capacitance(bias), label=name)
    law.axhline(1.0, color=house.BOUND, lw=house.BOUND_WIDTH, ls="--")
    law.set_xlabel("reverse bias across the junction  [V]")
    law.set_ylabel("capacitance, relative to zero bias")
    law.set_title("The parasitic is not a constant")
    law.legend()

    for vin, style in ((LOW_INPUT, "-"), (HIGH_INPUT, "--")):
        for fraction, colour in zip(JUNCTION_FRACTIONS, house.SERIES, strict=False):
            probe = Junction(c_zero=fraction * total)
            gains = [
                swing_gain(top_plate_voltage(vin, word, units, VREF), total, probe)
                for word in _trials(vin, units)
            ]
            swing.plot(
                range(1, len(gains) + 1),
                gains,
                style,
                color=colour,
                label=f"C_j0 = {fraction:g} C_total" if vin == LOW_INPUT else None,
            )
    swing.set_xlabel("bit trial")
    swing.set_ylabel("fraction of the swing the comparator sees")
    swing.set_title("What it does cost")
    swing.legend(loc="center right")
    house.note(swing, f"solid: vin = {LOW_INPUT:g} V\ndashed: vin = {HIGH_INPUT:g} V", (0.03, 0.62))

    codes = np.arange(2**N_BITS)
    big = Junction(c_zero=max(JUNCTION_FRACTIONS) * total)
    for label, offset, colour in (
        ("no comparator offset", 0.0, house.SERIES[2]),
        (f"comparator offset {SHOWN_OFFSET * 1e3:g} mV", SHOWN_OFFSET, house.SERIES[1]),
    ):
        moved = np.array(
            [
                input_at_decision(int(c), units, big, vref=VREF, node_offset=offset)
                - input_at_decision(int(c), units, Junction(c_zero=0.0), vref=VREF)
                for c in codes
            ]
        )
        shift.plot(codes, moved / lsb, color=colour, label=label)
    shift.plot(codes, inl(units, VREF), color=house.MODEL, ls=":", label="INL of the ideal array")
    shift.set_xlabel("code")
    shift.set_ylabel("threshold shift  [LSB]")
    shift.set_title("What it does not cost")
    shift.legend(loc="center left")
    house.note(
        shift,
        "flat is the result: the same shift at every\ncode is an offset, not a nonlinearity",
        (0.38, 0.60),
    )

    fig.suptitle(
        "A nonlinear parasitic on the floating node moves no threshold, because every "
        "decision is taken\nat the same node voltage -- so it holds the charge it was "
        "sampled with, whatever its law"
    )
    fig.tight_layout()
    return house.save(fig, out_dir / "junction.png")


def _trials(vin: float, unit_caps) -> list[int]:
    """The words a conversion puts on the array, from the protocol."""
    return [s.dac_b for s in conversion_sequence(vin, unit_caps, VREF) if s.phase == SETTLE]


def charge(out_dir: pathlib.Path = OUT_DIR) -> pathlib.Path:
    """What a conversion takes off the reference, and whether the pin notices.

    The left panel is the architecture showing through: a trial that fails
    hands its charge to ground, and a low code is a conversion whose trials
    mostly fail, so the cheapest conversions are at the top of the range.
    """
    units = _units()

    fig, (per_code, current) = house.canvas(1, 2, size=SQUARE_PANEL)

    inputs = np.linspace(0, VREF, 2**6, endpoint=False) + VREF / 2 ** (6 + 1)
    charges = np.array([reference_charge(float(v), units, VREF) for v in inputs])
    codes = [sar_convert(float(v), units, VREF)[0] for v in inputs]
    per_code.plot(codes, charges * 1e12, color=house.SERIES[0])
    per_code.set_xlabel("output code")
    per_code.set_ylabel("charge off the reference  [pC per conversion]")
    per_code.set_title("The cost of a conversion depends on its answer")
    house.note(
        per_code,
        f"{charges[0] / charges[-1]:.2f}x from the bottom of the\nrange to the top",
        (0.4, 0.95),
    )

    rates = np.logspace(3, 8, 200)
    current.loglog(
        rates, average_reference_current(charges.max(), rates) * 1e3, color=house.SERIES[0]
    )
    house.bound(current, I_PIN * 1e3, "pin current limit", color=house.BAD)
    total = float(units.sum())
    phase = settle_time(
        sampling_loop_resistance(R_PIN, R_PIN, R_PIN) * total,
        VREF,
        TOLERANCE_LSB * lsb_ideal(N_BITS, VREF),
    )
    settling_limited = 1.0 / ((N_BITS + OVERHEAD_PHASES) * phase)
    house.bound(current, settling_limited, "fastest settling allows", axis="x", color=house.GOOD)
    current.set_xlabel("conversions per second")
    current.set_ylabel("mean reference current  [mA]")
    current.set_title("The pin is budgeted for sag, not for average current")

    fig.suptitle(f"Charge off the reference at {N_BITS} bits, unit capacitor {C_UNIT * 1e15:g} fF")
    fig.tight_layout()
    return house.save(fig, out_dir / "charge.png")


#: Every figure this module draws, by the name of its file.
FIGURES = (conversion, frequency, bounds, junction, charge)


def draw_all(out_dir: pathlib.Path = OUT_DIR) -> list[pathlib.Path]:
    return [figure(out_dir) for figure in FIGURES]


if __name__ == "__main__":
    for path in draw_all():
        print(path)
