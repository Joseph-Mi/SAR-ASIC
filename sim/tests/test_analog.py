"""The generated analog block, against the contract and the golden model.

Structure is checked everywhere. Behaviour needs the simulator, so those tests
skip without it: they replay the protocol model's cycles into the block, open
loop, and require the top plate to land where `top_plate_voltage` says and the
comparator to answer what the model decided -- real charge on real
capacitance, through ideal switches.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil

import pytest

import analog
import bench
import ngspice
from bench import Bench, Phase, Supplies
from interface import N_BITS, PORTS
from mismatch import SKY130_CAP_MIN_AREA_MIM
from protocol import EVALUATE, SAMPLE, conversion_sequence
from sar import VCM_FRACTION, ideal_units, top_plate_voltage

needs_ngspice = pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not on PATH")

#: The small resolution keeps a conversion quick; the target is what ships.
RESOLUTIONS = (4, N_BITS)

VDD = 1.8
VREF = 1.0

#: Ideal switches and capacitors leave only the simulator's own tolerances
#: between it and the arithmetic -- far under an LSB at any resolution here.
VOLTS_TOLERANCE = 1e-5

#: Fractions of VREF: both ends, either side of mid-scale, and points in
#: different halves. None sits exactly on a threshold: there the top plate
#: lands exactly on Vcm, which is a decision no real comparator defines, and
#: the model's choice of side is a convention the circuit need not share.
INPUTS = (0.0, 0.123, 0.4991, 0.5009, 0.61, 0.999)

#: Large, so a threshold it moved would be obvious.
PARASITIC_FRACTION = 0.3

UNIT_FARADS = 1e-15

#: A pin level the forced-input mode must ignore.
IGNORED_PIN = 0.37


def supplies(vin: float) -> Supplies:
    return Supplies(vdd=VDD, vref=VREF, vin=vin)


def replay(vin: float, n_bits: int, **bench_args) -> tuple[list, Bench]:
    """The protocol model's cycles for one conversion, as bench phases."""
    steps = conversion_sequence(vin, ideal_units(n_bits), VREF)
    phases = [Phase(sample=s.sample, dac_b=s.dac_b, cmp_clk=s.cmp_clk) for s in steps]
    return steps, Bench(phases, supplies(vin), n_bits, **bench_args)


def declared(n_bits: int = N_BITS) -> list[str]:
    return ngspice.ports(ngspice.subckt(analog.subckt(n_bits), analog.NAME))


def test_the_block_declares_exactly_the_interface():
    expected = []
    for port in PORTS:
        if port.width == 1:
            expected.append(port.name)
        else:
            expected += [f"{port.name}[{k}]" for k in range(port.width)]
    assert sorted(declared()) == sorted(expected)


def test_the_array_is_binary_weighted_with_one_dummy():
    multipliers = analog.branch_multipliers(N_BITS)
    assert multipliers[:-1] == [2**k for k in range(N_BITS)]
    assert multipliers[-1] == 1
    assert sum(multipliers) == 2**N_BITS


def test_every_ideal_capacitor_is_its_branch_in_units():
    text = analog.subckt(N_BITS, analog.Ideal(UNIT_FARADS))
    values = [float(v) for v in re.findall(r"^Cu\w+ top \S+ (\S+)$", text, re.M)]
    assert values == pytest.approx([UNIT_FARADS * m for m in analog.branch_multipliers(N_BITS)])


def test_a_mim_unit_is_the_smallest_drawable_square():
    unit = analog.Mim()
    assert unit.side**2 == pytest.approx(SKY130_CAP_MIN_AREA_MIM)
    text = analog.subckt(N_BITS, unit)
    assert len(re.findall(rf"^Xu\w+ top \S+ {analog.PDK_MIM} ", text, re.M)) == N_BITS + 1


def test_a_bench_must_start_by_sampling():
    with pytest.raises(ValueError):
        bench.deck(Bench([Phase(sample=0)]))


@needs_ngspice
@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_the_top_plate_lands_where_the_model_says_every_cycle(n_bits, tmp_path):
    """Sampling holds it at Vcm; every later cycle, charge conservation in the
    circuit must agree with charge conservation in the model."""
    units = ideal_units(n_bits)
    for fraction in INPUTS:
        vin = fraction * VREF
        steps, b = replay(vin, n_bits)
        got = ngspice.run(bench.deck(b), tmp_path)["m_top"]
        want = [
            VCM_FRACTION * VREF
            if s.phase == SAMPLE
            else top_plate_voltage(vin, s.dac_b, units, VREF)
            for s in steps
        ]
        assert got == pytest.approx(want, abs=VOLTS_TOLERANCE), f"vin={vin}"


@needs_ngspice
@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_the_comparator_answers_what_the_model_decided(n_bits, tmp_path):
    """Strobed, cmp_out is the model's decision and cmp_out_n its complement.
    Unstrobed, both sit high: precharged, and equal."""
    for fraction in INPUTS:
        vin = fraction * VREF
        steps, b = replay(vin, n_bits)
        got = ngspice.run(bench.deck(b), tmp_path)
        high = [
            (p > VDD / 2, n > VDD / 2) for p, n in zip(got["m_cmp"], got["m_cmp_n"], strict=True)
        ]
        for step, (out, out_n) in zip(steps, high, strict=True):
            if step.phase == EVALUATE:
                assert (out, out_n) == (bool(step.decision), not step.decision), f"vin={vin}"
            else:
                assert out and out_n, f"vin={vin}: not precharged in {step.phase}"


@needs_ngspice
def test_a_top_plate_parasitic_divides_the_swing_and_moves_no_decision(tmp_path):
    n_bits = RESOLUTIONS[0]
    units = ideal_units(n_bits)
    c_par = PARASITIC_FRACTION * units.sum() * UNIT_FARADS
    vin = INPUTS[1] * VREF
    steps, b = replay(vin, n_bits, unit=analog.Ideal(UNIT_FARADS), c_par=c_par)
    got = ngspice.run(bench.deck(b), tmp_path)
    trials = [i for i, s in enumerate(steps) if s.phase != SAMPLE]
    want = [
        top_plate_voltage(vin, steps[i].dac_b, units, VREF, c_par=c_par / UNIT_FARADS)
        for i in trials
    ]
    assert [got["m_top"][i] for i in trials] == pytest.approx(want, abs=VOLTS_TOLERANCE)
    decided = [int(got["m_cmp"][i] > VDD / 2) for i, s in enumerate(steps) if s.phase == EVALUATE]
    assert decided == [s.decision for s in steps if s.phase == EVALUATE]


@needs_ngspice
@pytest.mark.parametrize("force_hi", [1, 0])
def test_forced_input_samples_a_rail_instead_of_the_pin(force_hi, tmp_path):
    n_bits = RESOLUTIONS[0]
    msb = 1 << (n_bits - 1)
    rail = VREF if force_hi else 0.0
    phases = [
        Phase(sample=1, force_en=1, force_hi=force_hi),
        Phase(dac_b=msb, force_en=1, force_hi=force_hi),
    ]
    b = Bench(phases, supplies(IGNORED_PIN * VREF), n_bits)
    got = ngspice.run(bench.deck(b), tmp_path)["m_top"][1]
    assert got == pytest.approx(
        top_plate_voltage(rail, msb, ideal_units(n_bits), VREF), abs=VOLTS_TOLERANCE
    )


PDK_LIBRARY = (
    pathlib.Path(os.environ.get("PDK_ROOT", "/nonexistent"))
    / os.environ.get("PDK", "sky130A")
    / "libs.tech/combined/sky130.lib.spice"
)


@needs_ngspice
@pytest.mark.skipif(not PDK_LIBRARY.exists(), reason="sky130 model library not found")
def test_mim_units_keep_the_binary_ratios(tmp_path):
    """With the PDK's capacitor the ratios, not the farads, are what must hold:
    the MSB trial moves the top plate by half the reference."""
    n_bits = RESOLUTIONS[0]
    msb = 1 << (n_bits - 1)
    b = Bench([Phase(sample=1), Phase(dac_b=msb)], supplies(0.0), n_bits, unit=analog.Mim())
    deck = f".lib {PDK_LIBRARY} tt\n" + bench.deck(b)
    got = ngspice.run(deck, tmp_path)["m_top"]
    assert got[1] - got[0] == pytest.approx(VREF / 2, rel=1e-3)
