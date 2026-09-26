"""The analog block as a netlist, generated from the contract.

Contract: the subcircuit this emits declares exactly the terminals the
interface declares, by name, with the bus expanded one terminal per bit. It is
the behavioural stand-in for the analog block: the capacitor array is real
capacitance, the comparator is a decision on the top-plate voltage, and every
switch is ideal unless a sampling scheme puts transistors in -- so any
disagreement with the golden model is architecture, or exactly the device a
test chose to add. The netlist is generated rather than drawn because the array's
size is the resolution's, and a drawing would restate it.

Digital inputs are read against half the supply, the way a CMOS gate reads
them. Every control expression is referred to `vss`, so the block works
whatever potential the testbench puts there.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from devices import Generic, Sky130
from interface import N_BITS, PORTS
from mismatch import SKY130_CAP_MIN_AREA_MIM

NAME = "sar_analog"

#: An on switch has to settle the array well inside one protocol phase, and an
#: off one has to hold the floating top plate for a whole conversion. These
#: are far past both, so neither ever limits a result; finite switches are a
#: realism step of their own, measured against this.
IDEAL_RON = 1.0
IDEAL_ROFF = 1e12

#: The comparator's hold capacitor. It is driven by an ideal difference
#: amplifier, so its size sets nothing but the solver's view of it.
HOLD_FARADS = 1e-15

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


@dataclass(frozen=True)
class MosSwitches:
    """Transistor sizes, in micrometres, for the switches sampling uses.

    Minimum length: it is the shortest channel, so the least charge for a
    given resistance. The top switch passes Vcm and the input switches Vin;
    each input switch is its unit width times its branch's units, so every
    branch settles alike, as with the ideal ones.
    """

    w_top: float = 2.0
    w_unit: float = 0.5
    length: float = 0.15


@dataclass(frozen=True)
class GateSizes:
    """Logic gate sizes, in micrometres, for the phase generator. The PMOS is
    wider to match the NMOS's drive; each buffer stage is `fanout` times the
    last, the usual taper for driving a large load quickly."""

    w_n: float = 0.5
    w_p: float = 1.0
    length: float = 0.15
    fanout: int = 4


@dataclass(frozen=True)
class Gapped:
    """Transistor sampling switches, the two phases made from `sample` by ideal
    delays: the input switches open `gap` seconds after the top switch, or
    before it if `gap` is negative. The experiment, not the design: it sets the
    order by fiat to show what the order does."""

    gap: float
    devices: Generic | Sky130 = Generic()
    switches: MosSwitches = MosSwitches()


@dataclass(frozen=True)
class NonOverlap:
    """Transistor sampling switches, the phases made from `sample` by a
    transistor-level generator in which each phase can only change once the
    phase it must follow has finished changing. The design."""

    devices: Generic | Sky130 = Generic()
    switches: MosSwitches = MosSwitches()
    gates: GateSizes = GateSizes()
    #: Extra capacitance on the switches' gate lines, in farads: a long wire,
    #: or a slow corner, made explicit.
    top_line_load: float = 0.0
    bottom_line_load: float = 0.0


#: The phase generator's buffer depths. The input switches' gates are the
#: largest load in the block -- one unit's width for every unit of the array --
#: so their line gets the deeper taper. Even depths keep the polarity.
TOP_BUFFER_STAGES = 2
BOTTOM_BUFFER_STAGES = 4
CONVERT_BUFFER_STAGES = 2

#: The off-detector's inverter: a strong NMOS against a weak PMOS pulls its
#: switching point from mid-supply down toward the NMOS threshold -- no lower,
#: since the NMOS must be off for the output to rise. A line is read as off
#: only below that, which is below where the top switch (passing Vcm) has
#: stopped conducting. Reading at the usual mid-supply point instead lets the
#: next phase start while a slow line is still halfway down and its switch
#: still on. The PMOS is weakened by length rather than width: it is already
#: as narrow as the process draws.
SENSE_W_N = 2.0
SENSE_W_P = 0.42
SENSE_L_P = 1.0

#: An ideal delay's characteristic impedance, matched at its far end so the
#: delayed edge arrives once and clean.
DELAY_IMPEDANCE = 50.0


def _delayed(source: str, out: str, delay: float) -> list[str]:
    """`out` follows `source` after `delay` seconds, through an ideal line."""
    if delay <= 0:
        return [f"E{out} {out} vss {source} vss 1"]
    return [
        f"T{out} {source} vss {out}_t vss Z0={DELAY_IMPEDANCE} TD={delay:.9g}",
        f"R{out}_t {out}_t vss {DELAY_IMPEDANCE}",
        f"E{out} {out} vss {out}_t vss 1",
    ]


def _inverter(dev, name: str, a: str, y: str, g: GateSizes, scale: float = 1.0) -> list[str]:
    return [
        dev.pmos(f"{name}p", y, a, "vdd", "vdd", g.w_p * scale, g.length),
        dev.nmos(f"{name}n", y, a, "vss", "vss", g.w_n * scale, g.length),
    ]


def _nor(dev, name: str, a: str, b: str, y: str, g: GateSizes) -> list[str]:
    """Two PMOS in series from the supply, two NMOS in parallel to ground: the
    output is high only when both inputs are low."""
    return [
        dev.pmos(f"{name}pa", f"{name}_m", a, "vdd", "vdd", 2 * g.w_p, g.length),
        dev.pmos(f"{name}pb", y, b, f"{name}_m", "vdd", 2 * g.w_p, g.length),
        dev.nmos(f"{name}na", y, a, "vss", "vss", g.w_n, g.length),
        dev.nmos(f"{name}nb", y, b, "vss", "vss", g.w_n, g.length),
    ]


def _buffer(dev, name: str, a: str, y: str, stages: int, g: GateSizes) -> list[str]:
    lines, node = [], a
    for i in range(stages):
        nxt = y if i == stages - 1 else f"{name}_s{i}"
        lines += _inverter(dev, f"{name}{i}", node, nxt, g, g.fanout**i)
        node = nxt
    return lines


def _still_on(dev, name: str, line: str, out: str, g: GateSizes) -> list[str]:
    """`out` is high until `line` has fallen to where its switch is off.

    A skewed inverter reads the line against its low switching point, and a
    plain one restores the polarity.
    """
    return [
        dev.pmos(f"{name}sp", f"{name}_lo", line, "vdd", "vdd", SENSE_W_P, SENSE_L_P),
        dev.nmos(f"{name}sn", f"{name}_lo", line, "vss", "vss", SENSE_W_N, g.length),
        *_inverter(dev, f"{name}r", f"{name}_lo", out, g),
    ]


def _generator(scheme: NonOverlap) -> list[str]:
    """Three phases from `sample`, each able to change only after the one it
    must follow has finished, because it takes that one's own line as input.

    phi_top follows `sample` through a buffer. phi_bot is high while `sample`
    or phi_top is high and phi_conv is low: it cannot fall before the top
    switch's line has fallen, nor rise before phi_conv's has. phi_conv is high
    while `sample` and phi_bot are both low: it cannot rise before the input
    switches' line has fallen. phi_bot and phi_conv, each gated by the other,
    are the cross-coupled pair.

    Every "has fallen" is read by an off-detector on the line the switches'
    gates hang on, so a phase waits for the line itself -- its wire, its load,
    its corner -- to reach the level where its switch is off, not for a
    delay someone sized to be long enough.
    """
    dev, g = scheme.devices, scheme.gates
    loads = [
        (line, c)
        for line, c in (("phi_top", scheme.top_line_load), ("phi_bot", scheme.bottom_line_load))
        if c
    ]
    return [
        *_buffer(dev, "btop", "sample", "phi_top", TOP_BUFFER_STAGES, g),
        *[f"C{line}_line {line} vss {c:.6e}" for line, c in loads],
        *_still_on(dev, "stop", "phi_top", "top_on", g),
        *_still_on(dev, "sbot", "phi_bot", "bot_on", g),
        *_still_on(dev, "scnv", "phi_conv", "cnv_on", g),
        *_nor(dev, "nor_held", "sample", "top_on", "held_n", g),
        *_nor(dev, "nor_bot", "held_n", "cnv_on", "bot_pre", g),
        *_buffer(dev, "bbot", "bot_pre", "phi_bot", BOTTOM_BUFFER_STAGES, g),
        *_nor(dev, "nor_cnv", "sample", "bot_on", "cnv_pre", g),
        *_buffer(dev, "bcnv", "cnv_pre", "phi_conv", CONVERT_BUFFER_STAGES, g),
    ]


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


def subckt(
    n_bits: int = N_BITS,
    unit: Ideal | Mim | None = None,
    c_par: float = 0.0,
    ron_unit: float = IDEAL_RON,
    ron_top: float = IDEAL_RON,
    sampling: Gapped | NonOverlap | None = None,
) -> str:
    """The analog block, as one `.subckt`.

    `unit` is `Ideal(farads)` or `Mim()`. `c_par` adds that many farads from
    the top plate to `vss`, the parasitic `top_plate_voltage` accounts for.

    `ron_unit` is the on-resistance of a bottom-plate switch sized for one
    unit. Branch k's switches are 2^k units wide, so 2^k times less resistive:
    every branch then settles with the same time constant, the way a real
    array is sized, and no branch lags the rest. The dummy's are one unit.
    `ron_top` is the top-plate sampling switch, which charges the whole array.

    `sampling` replaces the ideal top and input switches with transistors and
    says how their two phases are made: by ideal delays (`Gapped`), or by the
    phase generator (`NonOverlap`). Left as None, every switch is ideal and
    opens on `sample` alone.
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
        f".model sw_top sw vt={SWITCH_VT} vh={SWITCH_VH} ron={ron_top} roff={IDEAL_ROFF}",
        # Forced-input mode chooses what the array samples: the pin, or a rail.
        f"Bc_vin c_vin vss V = {low('force_en')}",
        f"Bc_fhi c_fhi vss V = {high('force_en')}*{high('force_hi')}",
        f"Bc_flo c_flo vss V = {high('force_en')}*{low('force_hi')}",
        "S_vin vs vin c_vin vss sw_ideal",
        "S_fhi vs vref c_fhi vss sw_ideal",
        "S_flo vs vss c_flo vss sw_ideal",
    ]
    if sampling is None:
        converting = low("sample")
        lines += [
            # Sampling: top plate to Vcm, every bottom plate to the sampled input.
            f"Bc_smp c_smp vss V = {high('sample')}",
            "S_top top vcm c_smp vss sw_top",
        ]
    else:
        sw = sampling.switches
        dev = sampling.devices
        lines += dev.models()
        if isinstance(sampling, Gapped):
            lines += _delayed("sample", "phi_top", -sampling.gap)
            lines += _delayed("sample", "phi_bot", sampling.gap)
            converting = low("phi_bot")
        else:
            lines += _generator(sampling)
            converting = high("phi_conv")
        lines.append(dev.nmos("top", "top", "phi_top", "vcm", "vss", sw.w_top, sw.length))
    lines.append(f"Bc_cnv c_cnv vss V = {converting}")

    for k, units in enumerate(branch_multipliers(n_bits)):
        is_dummy = k == n_bits
        tag = "d" if is_dummy else str(k)
        bottom = f"b{tag}"
        model = f"sw_b{tag}"
        lines.append(
            f".model {model} sw vt={SWITCH_VT} vh={SWITCH_VH} "
            f"ron={ron_unit / units:.9g} roff={IDEAL_ROFF}"
        )
        lines.append(_capacitor(f"u{tag}", "top", bottom, units, unit))
        if sampling is None:
            lines.append(f"S_in{tag} {bottom} vs c_smp vss {model}")
        else:
            sw = sampling.switches
            lines.append(
                sampling.devices.nmos(
                    f"in{tag}", bottom, "phi_bot", "vs", "vss", sw.w_unit, sw.length, units
                )
            )
        if is_dummy:
            lines.append(f"S_gnd{tag} {bottom} vss c_cnv vss {model}")
            continue
        bit = f"dac_b[{k}]"
        lines += [
            f"Bc_ref{tag} c_ref{tag} vss V = v(c_cnv,vss)*{high(bit)}",
            f"Bc_gnd{tag} c_gnd{tag} vss V = v(c_cnv,vss)*{low(bit)}",
            f"S_ref{tag} {bottom} vref c_ref{tag} vss {model}",
            f"S_gnd{tag} {bottom} vss c_gnd{tag} vss {model}",
        ]

    if c_par:
        lines.append(f"Cpar top vss {c_par:.6e}")

    # The comparator: precharged, both outputs high, while the strobe is low;
    # while it is high, cmp_out is high when the top plate sat below Vcm at the
    # strobe's rising edge -- the guess was still low, keep the bit. The
    # decision is taken on that edge and held, as a latch takes it: a
    # comparator that kept looking would give the array the evaluate phase to
    # settle in too, and hide exactly the settling a real one exposes. A top
    # plate exactly at Vcm is a decision no real comparator defines, so none
    # is promised here.
    strobe = high("cmp_clk")
    keep = "u(v(held,vss))"
    lines += [
        "Ediff diff vss vcm top 1",
        f"Bc_trk c_trk vss V = {low('cmp_clk')}",
        "S_trk diff held c_trk vss sw_ideal",
        f"Chold held vss {HOLD_FARADS:.6e}",
        f"Bcmp cmp_out vss V = v(vdd,vss)*(1-{strobe}+{strobe}*{keep})",
        f"Bcmpn cmp_out_n vss V = v(vdd,vss)*(1-{strobe}*{keep})",
        ".ends",
    ]
    return "\n".join(lines) + "\n"
