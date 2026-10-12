"""What a latch comparator is, as the rest of the design has to tolerate it.

A sign function is not a comparator. A StrongARM latch separates its outputs
by regenerating a difference exponentially -- the cross-coupled pair's loop
gain multiplies whatever the input pair handed it, so the separation grows by
e every time constant. Three consequences follow, and all three reach the
converter:

  it takes time        and the time grows as the logarithm of how small the
                       difference is, so the hardest decision is also the
                       slowest one
  it has a floor       a strobe of finite length leaves anything below
                       `resolution` unseparated, which is the metastability
                       the interface carries two wires to detect
  it is not centred    offset and noise sit at its input, where the converter
                       has already divided the swing down

Contract: every voltage here is at the comparator's own terminals, not
referred to the converter's input. The array divides the top plate's excursion
by its parasitic before the comparator sees it, so a specification written
here is converted once, at the end, rather than carried divided through every
expression.
"""

from __future__ import annotations

import math

from sar import branch_weights, dac_voltage, n_bits_of


def resolution(tau: float, strobe: float, swing: float) -> float:
    """The smallest difference a latch separates within `strobe`, volts.

    Regeneration takes a difference to `swing` in tau*ln(swing/difference), so
    what the strobe allows is that solved the other way round. It falls
    exponentially with the time given, which is why a comparator that is fast
    enough at all is usually fast enough by a wide margin -- and why one that
    is not fails suddenly.
    """
    if tau <= 0.0:
        raise ValueError(f"{tau} s is not a regeneration time constant")
    if strobe < 0.0:
        raise ValueError(f"{strobe} s is not a strobe length")
    if swing <= 0.0:
        raise ValueError(f"{swing} V is not a separation to reach")
    return swing * math.exp(-strobe / tau)


def decision_time(difference: float, tau: float, swing: float) -> float:
    """How long the latch needs to separate `difference` to `swing`, seconds.

    The quantity a strobe length is sized from. A difference at or above the
    swing is already separated and needs no time at all.
    """
    if tau <= 0.0:
        raise ValueError(f"{tau} s is not a regeneration time constant")
    if swing <= 0.0:
        raise ValueError(f"{swing} V is not a separation to reach")
    if difference <= 0.0:
        raise ValueError("a difference of zero never separates")
    return max(0.0, tau * math.log(swing / difference))


def margins(vin: float, unit_caps, vref: float = 1.0) -> list[float]:
    """What the comparator is asked to resolve at each trial, volts.

    The difference between the input and the trial's DAC voltage, MSB first.
    It is large early and small late -- a binary search halves it every trial
    by construction -- so the last trial is the one that sets the
    specification, and it is the only one worth quoting.

    Returned at the comparator's terminals for an array with nothing on its
    top plate. A parasitic divides all of them by the same factor.
    """
    caps = branch_weights(unit_caps)
    total = sum(unit_caps)
    settled = 0
    found = []
    for k in range(n_bits_of(unit_caps) - 1, -1, -1):
        trial = settled | (1 << k)
        guess = dac_voltage(trial, caps, total, vref)
        found.append(abs(vin - guess))
        if vin >= guess:
            settled = trial
    return found


def worst_margin(n_bits: int, vref: float = 1.0) -> float:
    """The smallest difference the converter ever presents, volts.

    Half an LSB: the last trial decides between two adjacent codes, and an
    input exactly between them is the hardest question the converter can ask.
    Every comparator figure -- offset, noise, resolution -- is a fraction of
    this, which is what makes it the one number a specification starts from.
    """
    if n_bits < 1:
        raise ValueError(f"{n_bits} is not a resolution")
    return vref / 2 ** (n_bits + 1)


def margin_after(margin: float, offset: float, noise_rms: float, sigmas: float) -> float:
    """What is left of a decision's margin once the comparator is subtracted.

    A static offset eats the margin directly; noise eats it at whatever
    confidence the design is held to, which is what `sigmas` buys. Positive
    means the decision is made correctly to that confidence, and negative
    means the comparator decides the bit rather than the input does.

    Offset is the term to subtract *after* calibration, not before: a constant
    offset shifts every threshold by the same amount and so moves no code
    relative to its neighbours, and this design can measure it in the field.
    What belongs here is the residue calibration leaves.
    """
    if sigmas < 0.0:
        raise ValueError(f"{sigmas} is not a confidence in standard deviations")
    if noise_rms < 0.0:
        raise ValueError(f"{noise_rms} V is not a noise")
    return margin - abs(offset) - sigmas * noise_rms


def noise_for_margin(margin: float, sigmas: float) -> float:
    """The noise a margin will carry, volts rms, at a given confidence.

    The specification read the other way round, which is the direction a
    comparator is designed in: the converter fixes the margin, the confidence
    is chosen, and what falls out is the number the latch has to meet.
    """
    if margin <= 0.0:
        raise ValueError(f"{margin} V is not a margin")
    if sigmas <= 0.0:
        raise ValueError(f"{sigmas} is not a confidence in standard deviations")
    return margin / sigmas


def swing_division(c_total: float, c_parasitic: float) -> float:
    """What the array leaves of a top-plate excursion by the time the
    comparator sees it.

    The one conversion between a specification written at the comparator and
    one written at the converter's input: divide the margin by this, or
    multiply the offset and noise by its inverse.
    """
    if c_total <= 0.0:
        raise ValueError(f"{c_total} F is not an array")
    if c_parasitic < 0.0:
        raise ValueError(f"{c_parasitic} F is not a parasitic")
    return c_total / (c_total + c_parasitic)
