"""The analog block as an ideal-switch netlist, generated from the contract.

Contract: the subcircuit this emits declares exactly the terminals the
interface declares, by name, with the bus expanded one terminal per bit. It is
the behavioural stand-in for the analog block: the capacitor array is real
capacitance, but every switch is ideal and the comparator is a decision on the
top-plate voltage, so any disagreement with the golden model is architecture,
not a device. The netlist is generated rather than drawn because the array's
size is the resolution's, and a drawing would restate it.

Digital inputs are read against half the supply, the way a CMOS gate reads
them. Every control expression is referred to `vss`, so the block works
whatever potential the testbench puts there.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from interface import N_BITS, PORTS
from mismatch import SKY130_CAP_MIN_AREA_MIM
from sar import VCM_FRACTION

NAME = "sar_analog"

#: An on switch has to settle the array well inside one protocol phase, and an
#: off one has to hold the floating top plate for a whole conversion. These
#: are far past both, so neither ever limits a result; finite switches are a
#: realism step of their own, measured against this.
IDEAL_RON = 1.0
IDEAL_ROFF = 1e12

#: Hysteresis on the ideal switches' control, so a control sitting exactly at
#: its threshold cannot chatter. Controls here are clean 0/1 levels.
SWITCH_VT = 0.5
SWITCH_VH = 0.2

PDK_MIM = "sky130_fd_pr__cap_mim_m3_1"


@dataclass(frozen=True)
class Ideal:
    """A unit capacitor as a plain SPICE capacitor of `farads`."""

    farads: float


@dataclass(frozen=True)
class Mim:
    """A unit capacitor as the PDK's MiM device at the smallest drawable area.

    Square, so its perimeter is the smallest that area allows: perimeter is
    where the fringe term lives, and a unit that differs from its neighbours in
    shape differs in value.
    """

    area: float = SKY130_CAP_MIN_AREA_MIM

    @property
    def side(self) -> float:
        return math.sqrt(self.area)


#: Ideal capacitors of a round size: with ideal switches only the ratios reach
#: a result, so the farads are arbitrary until a realism step makes them count.
DEFAULT_UNIT = Ideal(1e-15)


def terminals(n_bits: int = N_BITS) -> list[str]:
    """Every terminal, in declaration order, the bus expanded MSB first.

    The bus is as wide as the resolution, so at a resolution other than the
    target's -- a small array a test can convert quickly -- it narrows with it.
    """
    names = []
    for port in PORTS:
        if port.width == 1:
            names.append(port.name)
        else:
            names.extend(f"{port.name}[{k}]" for k in reversed(range(n_bits)))
    return names


def branch_multipliers(n_bits: int = N_BITS) -> list[int]:
    """Units per branch, LSB branch first, then the dummy."""
    return [2**k for k in range(n_bits)] + [1]


def _capacitor(name: str, top: str, bottom: str, units: int, unit) -> str:
    if isinstance(unit, Ideal):
        return f"C{name} {top} {bottom} {unit.farads * units:.6e}"
    return f"X{name} {top} {bottom} {PDK_MIM} w={unit.side:.6g} l={unit.side:.6g} m={units}"


def subckt(n_bits: int = N_BITS, unit: Ideal | Mim | None = None, c_par: float = 0.0) -> str:
    """The analog block, as one `.subckt`.

    `unit` is `Ideal(farads)` or `Mim()`. `c_par` adds that many farads from
    the top plate to `vss`, the parasitic `top_plate_voltage` accounts for.
    """
    unit = DEFAULT_UNIT if unit is None else unit
    ports = terminals(n_bits)
    half = "0.5*v(vdd,vss)"
    high = lambda node: f"u(v({node},vss)-{half})"  # noqa: E731
    low = lambda node: f"u({half}-v({node},vss))"  # noqa: E731

    lines = [
        f"* {NAME}: ideal switches, behavioural comparator",
        f".subckt {NAME} {' '.join(ports)}",
        f".model sw_ideal sw vt={SWITCH_VT} vh={SWITCH_VH} ron={IDEAL_RON} roff={IDEAL_ROFF}",
        # The common mode the top plate is sampled to and compared against.
        f"Bvcm vcm vss V = {VCM_FRACTION}*v(vref,vss)",
        # Forced-input mode chooses what the array samples: the pin, or a rail.
        f"Bc_vin c_vin vss V = {low('force_en')}",
        f"Bc_fhi c_fhi vss V = {high('force_en')}*{high('force_hi')}",
        f"Bc_flo c_flo vss V = {high('force_en')}*{low('force_hi')}",
        "S_vin vs vin c_vin vss sw_ideal",
        "S_fhi vs vref c_fhi vss sw_ideal",
        "S_flo vs vss c_flo vss sw_ideal",
        # Sampling: top plate to Vcm, every bottom plate to the sampled input.
        f"Bc_smp c_smp vss V = {high('sample')}",
        f"Bc_cnv c_cnv vss V = {low('sample')}",
        "S_top top vcm c_smp vss sw_ideal",
    ]

    for k, units in enumerate(branch_multipliers(n_bits)):
        is_dummy = k == n_bits
        tag = "d" if is_dummy else str(k)
        bottom = f"b{tag}"
        lines.append(_capacitor(f"u{tag}", "top", bottom, units, unit))
        lines.append(f"S_in{tag} {bottom} vs c_smp vss sw_ideal")
        if is_dummy:
            lines.append(f"S_gnd{tag} {bottom} vss c_cnv vss sw_ideal")
            continue
        bit = f"dac_b[{k}]"
        lines += [
            f"Bc_ref{tag} c_ref{tag} vss V = {low('sample')}*{high(bit)}",
            f"Bc_gnd{tag} c_gnd{tag} vss V = {low('sample')}*{low(bit)}",
            f"S_ref{tag} {bottom} vref c_ref{tag} vss sw_ideal",
            f"S_gnd{tag} {bottom} vss c_gnd{tag} vss sw_ideal",
        ]

    if c_par:
        lines.append(f"Cpar top vss {c_par:.6e}")

    # The comparator: precharged, both outputs high, while the strobe is low;
    # while it is high, cmp_out is high when the top plate sits below Vcm --
    # the guess is still low, keep the bit. A top plate exactly at Vcm is a
    # decision no real comparator defines, so none is promised here.
    strobe = high("cmp_clk")
    keep = "u(v(vcm,vss)-v(top,vss))"
    lines += [
        f"Bcmp cmp_out vss V = v(vdd,vss)*(1-{strobe}+{strobe}*{keep})",
        f"Bcmpn cmp_out_n vss V = v(vdd,vss)*(1-{strobe}*{keep})",
        ".ends",
    ]
    return "\n".join(lines) + "\n"
