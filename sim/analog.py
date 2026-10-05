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

import sky130
from devices import Generic, Sky130
from interface import N_BITS, PORTS

NAME = "sar_analog"

#: An on switch has to settle the array well inside one protocol phase, and an
#: off one has to hold the floating top plate for a whole conversion. These
#: are far past both, so neither ever limits a result; finite switches are a
#: realism step of their own, measured against this.
IDEAL_RON = 1.0
IDEAL_ROFF = 1e12

#: How fast an ideal bottom-plate switch settles its own capacitance, in
#: seconds -- a hundredth of any edge a bench drives. Each branch's switch is
#: scaled to its branch, so this holds for every branch. It is a time rather
#: than a resistance because a resistance that is "small" for one unit is
#: vanishing for the largest branch: a bottom plate switched between two ideal
#: sources in far under a picosecond is an event the solver cannot always
#: resolve while transistors elsewhere are mid-transition.
IDEAL_UNIT_TAU = 1e-12

#: The comparator's hold capacitor. It is driven by an ideal difference
#: amplifier, so its size sets nothing but the solver's view of it.
HOLD_FARADS = 1e-15

#: Hysteresis on the ideal switches' control, so a control sitting exactly at
#: its threshold cannot chatter. Controls here are clean 0/1 levels.
SWITCH_VT = 0.5
SWITCH_VH = 0.2


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

    area: float = sky130.CAP_MIN_AREA_MIM

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

    An input switch is a transmission gate: an NMOS and a PMOS side by side,
    driven by opposite lines. Vin spans the reference, and an NMOS alone
    conducts less the higher the voltage it passes -- near the top of the
    range it has barely more gate drive than its threshold, and a sample of a
    high input does not settle. The PMOS conducts best exactly there. Set
    `w_unit_p` to zero for an NMOS alone.
    """

    #: The top switch returns the whole array to Vcm, in series with the input
    #: and common-mode pins; sized so its on-resistance at the slowest corner
    #: stays under one pin's, and no wider -- its channel charge, released onto
    #: the top plate, grows with it.
    w_top: float = 8.0
    w_unit: float = 0.5
    w_unit_p: float = 1.0
    length: float = 0.15
    #: The switches that drive each bottom plate during conversion, per unit:
    #: an NMOS to ground and a PMOS to the reference, always both.
    w_dac_n: float = 0.5
    w_dac_p: float = 1.0


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
    bottom_n_line_load: float = 0.0


#: The phase generator's buffer depths. The input switches' gates are the
#: largest load in the block -- one unit's width for every unit of the array --
#: so their line gets the deeper taper. Even depths keep the polarity; the
#: PMOS line's buffer is one stage shorter, and starts one taper step larger,
#: to end inverted at the same size.
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

#: The same for a PMOS switch's line, mirrored: a PMOS is off when its gate is
#: high, so its line reads as off only above a switching point pulled up
#: toward the supply less the PMOS threshold, by a strong PMOS against an NMOS
#: weakened by length.
SENSE_P_W_P = 4.0
SENSE_P_W_N = 0.42
SENSE_P_L_N = 1.0

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


def _nor(dev, name: str, inputs: list[str], y: str, g: GateSizes) -> list[str]:
    """PMOS in series from the supply, one per input, and NMOS in parallel to
    ground: the output is high only when every input is low. Each PMOS is as
    many times wider as there are in the stack, so the stack pulls up as hard
    as one inverter's PMOS."""
    stack = len(inputs)
    lines, above = [], "vdd"
    for k, a in enumerate(inputs):
        below = y if k == stack - 1 else f"{name}_m{k}"
        lines.append(dev.pmos(f"{name}p{k}", below, a, above, "vdd", stack * g.w_p, g.length))
        above = below
    return lines + [
        dev.nmos(f"{name}n{k}", y, a, "vss", "vss", g.w_n, g.length) for k, a in enumerate(inputs)
    ]


def _buffer(dev, name: str, a: str, y: str, stages: int, g: GateSizes, first: int = 0) -> list[str]:
    """A tapered chain of `stages` inverters, the first `first` taper steps up."""
    lines, node = [], a
    for i in range(stages):
        nxt = y if i == stages - 1 else f"{name}_s{i}"
        lines += _inverter(dev, f"{name}{i}", node, nxt, g, g.fanout ** (first + i))
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


def _still_on_p(dev, name: str, line: str, out: str, g: GateSizes) -> list[str]:
    """`out` is high until `line` has risen to where its PMOS switch is off.

    A skewed inverter reads the line against its high switching point; its
    output is already high while the switch is on, and two plain inverters
    sharpen it without changing that.
    """
    return [
        dev.pmos(f"{name}sp", f"{name}_hi", line, "vdd", "vdd", SENSE_P_W_P, g.length),
        dev.nmos(f"{name}sn", f"{name}_hi", line, "vss", "vss", SENSE_P_W_N, SENSE_P_L_N),
        *_buffer(dev, f"{name}r", f"{name}_hi", out, 2, g),
    ]


def _generator(scheme: NonOverlap) -> list[str]:
    """Three phases from `sample`, each able to change only after the one it
    must follow has finished, because it takes that one's own line as input.

    phi_top follows `sample` through a buffer. phi_bot is high while `sample`
    or phi_top is high and phi_conv is low: it cannot fall before the top
    switch's line has fallen, nor rise before phi_conv's has. phi_bot_n, the
    input switches' PMOS line, is its complement from the same source. phi_conv
    is high while `sample` is low and both input lines are off: it cannot rise
    before the input switches have let go on both sides. phi_bot and phi_conv,
    each gated by the other, are the cross-coupled pair.

    Every "has fallen" is read by an off-detector on the line the switches'
    gates hang on, so a phase waits for the line itself -- its wire, its load,
    its corner -- to reach the level where its switch is off, not for a
    delay someone sized to be long enough.
    """
    dev, g = scheme.devices, scheme.gates
    loads = [
        (line, c)
        for line, c in (
            ("phi_top", scheme.top_line_load),
            ("phi_bot", scheme.bottom_line_load),
            ("phi_bot_n", scheme.bottom_n_line_load),
        )
        if c
    ]
    complement = (
        []
        if not scheme.switches.w_unit_p
        else [
            *_buffer(dev, "bbotn", "bot_pre", "phi_bot_n", BOTTOM_BUFFER_STAGES - 1, g, first=1),
            *_still_on_p(dev, "sbotn", "phi_bot_n", "botn_on", g),
        ]
    )
    conversion = (
        _nor(dev, "nor_cnv", ["sample", "bot_on", "botn_on"], "cnv_pre", g)
        if scheme.switches.w_unit_p
        else _nor(dev, "nor_cnv", ["sample", "bot_on"], "cnv_pre", g)
    )
    return [
        *_buffer(dev, "btop", "sample", "phi_top", TOP_BUFFER_STAGES, g),
        *[f"C{line}_line {line} vss {c:.6e}" for line, c in loads],
        *_still_on(dev, "stop", "phi_top", "top_on", g),
        *_still_on(dev, "sbot", "phi_bot", "bot_on", g),
        *_still_on(dev, "scnv", "phi_conv", "cnv_on", g),
        *_nor(dev, "nor_held", ["sample", "top_on"], "held_n", g),
        *_nor(dev, "nor_bot", ["held_n", "cnv_on"], "bot_pre", g),
        *_buffer(dev, "bbot", "bot_pre", "phi_bot", BOTTOM_BUFFER_STAGES, g),
        *complement,
        *conversion,
        *_buffer(dev, "bcnv", "cnv_pre", "phi_conv", CONVERT_BUFFER_STAGES, g),
    ]


def _dac_switches(scheme: NonOverlap, tag: str, bottom: str, bit: str | None, units: int):
    """A branch's bottom plate driven to the reference or to ground by
    transistors: an NMOS to ground, a PMOS to the reference, each its unit
    width times the branch's units.

    Their gates are the conversion enable combined with the branch's bit,
    formed as smooth functions of both lines, as the gate a logic cell drives
    would be. An ideal switch here changes resistance by a dozen decades in
    no time at all, and with a transistor on the array conducting at the same
    instant the solver cannot always follow. The dummy has only the switch to
    ground.
    """
    sw, dev = scheme.switches, scheme.devices
    enable = "v(c_cnv,vss)"
    selected = "0" if bit is None else f"v({bit},vss)/v(vdd,vss)"
    lines = [
        f"Bgn{tag} gate_n{tag} vss V = v(vdd,vss)*{enable}*(1-{selected})",
        dev.nmos(f"dn{tag}", bottom, f"gate_n{tag}", "vss", "vss", sw.w_dac_n, sw.length, units),
    ]
    if bit is not None:
        lines += [
            f"Bgp{tag} gate_p{tag} vss V = v(vdd,vss)*(1-{enable}*{selected})",
            dev.pmos(
                f"dp{tag}", bottom, f"gate_p{tag}", "vref", "vdd", sw.w_dac_p, sw.length, units
            ),
        ]
    return lines


#: Ideal capacitors of a round size: with ideal switches only the ratios reach
#: a result, so the farads are arbitrary until a realism step makes them count.
DEFAULT_UNIT = Ideal(1e-15)

#: The on-resistance of an ideal bottom-plate switch sized for one unit. A
#: larger unit settles proportionally slower, and still far inside an edge.
IDEAL_RON_UNIT = IDEAL_UNIT_TAU / DEFAULT_UNIT.farads

#: An ideal unit of about sky130's smallest MiM: its minimum area at a typical
#: density. Where transistors touch the array its size counts -- a switch's
#: charge and resistance act against the array's capacitance -- and a unit too
#: light for its switches exaggerates every effect.
MIM_SIZED = Ideal(8e-15)


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
    return f"X{name} {top} {bottom} {sky130.MIM} w={unit.side:.6g} l={unit.side:.6g} m={units}"


def subckt(
    n_bits: int = N_BITS,
    unit: Ideal | Mim | None = None,
    c_par: float = 0.0,
    ron_unit: float = IDEAL_RON_UNIT,
    ron_top: float = IDEAL_RON,
    sampling: Gapped | NonOverlap | None = None,
) -> str:
    """The analog block, as one `.subckt`.

    `unit` is `Ideal(farads)` or `Mim()`. `c_par` adds that many farads from
    the top plate to `vss`, the parasitic the golden model's top-plate voltage
    accounts for.

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
    # The generator's lines are driven by transistors and cross a threshold
    # gradually. A step taken on one at one exact voltage turns every switch it
    # controls at one instant -- a discontinuity the solver cannot step past
    # when the jump it causes couples back to the line through the switches'
    # gates. Switches on such a line read it as a fraction of the supply, and
    # switch on their own hysteresis.
    level = lambda node: f"v({node},vss)/v(vdd,vss)"  # noqa: E731

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
            lines.append("Ephi_bot_n phi_bot_n vss vdd phi_bot 1")
            converting = low("phi_bot")
        else:
            lines += _generator(sampling)
            converting = level("phi_conv")
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
            if sw.w_unit_p:
                lines.append(
                    sampling.devices.pmos(
                        f"inp{tag}", bottom, "phi_bot_n", "vs", "vdd", sw.w_unit_p, sw.length, units
                    )
                )
        if isinstance(sampling, NonOverlap):
            lines += _dac_switches(
                sampling, tag, bottom, None if is_dummy else f"dac_b[{k}]", units
            )
            continue
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
