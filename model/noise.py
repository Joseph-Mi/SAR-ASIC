"""Noise the array traps at the instant it stops sampling.

A switch is a resistor, and a resistor charging a capacitor leaves a voltage
on it whose mean square is kT/C however large the resistance is: a slower
switch is noisier per unit bandwidth and bandlimits by exactly as much, and
the two cancel. So this is a function of the array alone, and the only way to
spend against it is capacitance.

It is sampled once per conversion and held, so it behaves as an input offset
that is redrawn every conversion -- unlike comparator noise, which is redrawn
at every trial and can therefore cost an early bit and with it a power of two.
The two are separate terms in a budget and are not interchangeable.

Contract: capacitances in farads, temperatures in kelvin, voltages in volts.
"""

from __future__ import annotations

import math

#: Boltzmann's constant, joules per kelvin.
BOLTZMANN = 1.380649e-23

#: Room temperature, kelvin. A noise figure moves as the root of this, so the
#: hot corner is worth about a percent and is not what decides an array.
ROOM = 300.0


def sampled_noise(c_total: float, temperature: float = ROOM) -> float:
    """Volts rms the array holds after sampling, from the switch alone."""
    if c_total <= 0.0:
        raise ValueError(f"{c_total} F is not an array")
    if temperature <= 0.0:
        raise ValueError(f"{temperature} K is not a temperature")
    return math.sqrt(BOLTZMANN * temperature / c_total)


def sampled_noise_lsb(
    c_total: float,
    n_bits: int,
    vref: float = 1.0,
    temperature: float = ROOM,
) -> float:
    """The same, against the least significant bit it has to hide under.

    The figure that decides whether it matters: the volts are fixed by the
    array, and the LSB halves with every bit added, so the same array is
    quieter at a coarse resolution and louder at a fine one by the same
    factor.
    """
    return sampled_noise(c_total, temperature) / (vref / 2**n_bits)


def capacitance_for_noise(
    lsb_fraction: float,
    n_bits: int,
    vref: float = 1.0,
    temperature: float = ROOM,
) -> float:
    """The array a noise budget asks for, farads.

    Solved the other way round, because this is the direction a resolution
    decision runs: a target is chosen and the array follows from it. It goes
    as the square of the resolution the target is set at, which is why a
    noise-limited converter gets expensive two bits at a time.
    """
    if lsb_fraction <= 0.0:
        raise ValueError(f"{lsb_fraction} is not a noise budget")
    return BOLTZMANN * temperature / (lsb_fraction * vref / 2**n_bits) ** 2
