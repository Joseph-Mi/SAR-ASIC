"""What a device is, measured rather than read off a model card.

A compact model states hundreds of parameters and uses a subset of them in
ways no name makes obvious. Several of the numbers this project needs -- what
an off diffusion presents to the node it sits on, what a switch's resistance
is at the bias it really runs at -- are emergent, not declared, and a grep that
finds a plausible value finds one the simulator does not use.

So they are measured from the device the simulator builds, through the same
netlister the benches use. That last part is not incidental: a device written
out by hand is a device without the finger splitting the models need, and it
answers a different question at the same bias.

Contract: every function here builds a deck, runs it, and returns a number.
Nothing is cached and nothing is asserted; the tests that call these decide
what the numbers have to be.
"""

from __future__ import annotations

import numpy as np

import ngspice

#: Frequency a capacitance is read at. The devices are linear at the
#: amplitudes used here, so one frequency is the whole measurement.
PROBE_HZ = 1e6

#: Volts across a switch while its resistance is read: small enough to keep it
#: in triode, large enough to leave the solver's floor.
TRIODE_STEP = 0.01

#: Where the depletion fit searches for a built-in potential, volts, and how
#: finely. Silicon's is a few tenths; the range is wide enough to find a value
#: outside that without being told to expect one.
POTENTIAL_RANGE = (0.1, 2.0)
POTENTIAL_STEPS = 381


def _run(lines: list[str], workdir, name: str) -> float:
    return ngspice.run("\n".join(lines) + "\n", workdir)[name][0]


def on_resistance(
    workdir,
    devices,
    width: float,
    length: float,
    passing: float,
    supply: float,
    temp: float = 27.0,
    width_p: float = 0.0,
) -> float:
    """A pass switch's resistance while it passes `passing`, ohms.

    An NMOS alone, or a transmission gate when `width_p` is given: the PMOS
    sits across it with its gate at ground and its well at the supply, so the
    two conduct over opposite halves of the range.

    The gate is at the supply and the body at ground, so the voltage being
    passed sets both the gate drive left over and the body effect against it.
    That is why the bias matters: the same switch passing a different level is
    a different resistance, and at the slow corner the difference is orders.
    """
    lines = [
        "* pass switch resistance at the level it passes",
        *devices.header(),
        *devices.models(),
        devices.nmos("swn", "d", "g", "s", "0", width, length),
        f"Vg g 0 {supply:g}",
        f"Vs s 0 {passing:g}",
        f"Vd d 0 {passing + TRIODE_STEP:g}",
    ]
    if width_p > 0.0:
        lines += [
            devices.pmos("swp", "d", "gp", "s", "vdd", width_p, length),
            "Vgp gp 0 0",
            f"Vdd vdd 0 {supply:g}",
        ]
    lines += [
        f".temp {temp:g}",
        ".control",
        "set nomodcheck",
        "op",
        f"let ron = {TRIODE_STEP:g}/abs(i(Vd))",
        "print ron",
        ".endc",
        ".end",
    ]
    return _run(lines, workdir, "ron")


def diffusion_curve(
    workdir,
    devices,
    width: float,
    length: float,
    biases,
    temp: float = 27.0,
) -> list[float]:
    """What an off device's drain presents, farads, at each reverse bias.

    Gate and source are held at the body's potential, so the device is off and
    what remains on the drain is the diffusion and whatever is permanently
    tied to it. That total is what a node connected there actually sees, which
    is the quantity a charge budget needs.
    """
    lines = [
        "* drain-node capacitance of an off device against reverse bias",
        *devices.header(),
        *devices.models(),
        devices.nmos("sw", "d", "g", "s", "0", width, length),
        "Vg g 0 0",
        "Vs s 0 0",
        "Vd d 0 dc 0 ac 1",
        f".temp {temp:g}",
        ".control",
        "set nomodcheck",
    ]
    for i, bias in enumerate(biases):
        lines += [
            f"alter Vd dc = {bias:g}",
            f"ac lin 1 {PROBE_HZ:g} {PROBE_HZ:g}",
            f"let c{i} = abs(i(Vd))/(2*pi*{PROBE_HZ:g})",
            f"print c{i}",
        ]
    lines += [".endc", ".end"]
    found = ngspice.run("\n".join(lines) + "\n", workdir)
    return [found[f"c{i}"][0] for i in range(len(biases))]


def fit_depletion(biases, capacitances) -> tuple[float, float, float, float]:
    """Fit C(V) = c_zero / (1 + V/phi_b)**grading to a measured curve.

    Returns the three parameters and the relative error left over, so a caller
    can refuse a fit that did not work rather than quoting one that did not.

    The law is linear in its logarithm once the built-in potential is fixed,
    so the potential is searched and the other two fall out of a straight-line
    fit at each candidate. That needs no starting guess and cannot wander off,
    which matters because the result is a declared constant.
    """
    bias = np.asarray(biases, dtype=float)
    measured = np.asarray(capacitances, dtype=float)
    if np.any(measured <= 0.0):
        raise ValueError("a capacitance curve cannot pass through zero")

    best = None
    for potential in np.linspace(*POTENTIAL_RANGE, POTENTIAL_STEPS):
        x = np.log1p(bias / potential)
        slope, intercept = np.polyfit(x, np.log(measured), 1)
        predicted = np.exp(intercept) * np.exp(slope * x)
        error = float(np.sqrt(np.mean((predicted - measured) ** 2)) / measured.mean())
        if best is None or error < best[3]:
            best = (float(np.exp(intercept)), float(potential), float(-slope), error)
    return best
