"""What the shared top plate reads, trial by trial.

`sar_convert` says which way each decision went. The circuit simulation sees a
voltage, not a decision, so the model has to say what that voltage is -- and
the decisions have to be readable back out of it, or the two descriptions of
one converter have quietly become two converters.
"""

import numpy as np
import pytest

from sar import (
    VCM_FRACTION,
    branch_weights,
    dac_voltage,
    ideal_units,
    n_bits_of,
    sar_convert,
    top_plate_voltage,
)

RESOLUTIONS = (4, 8, 10)
VREF = 1.0

#: Mismatch large enough that a formula relying on exact binary weights would
#: be caught, small enough that the array still converts.
MISMATCH_SIGMA = 0.02
SEED = 20260926
DRAWS = 200

#: A top-plate parasitic sized as a fraction of the array. Deliberately large:
#: the claim under test is that it moves no threshold at all, so a large one
#: makes a violation obvious rather than lost in rounding.
PARASITIC_FRACTION = 0.3


@pytest.fixture(params=RESOLUTIONS)
def units(request):
    return ideal_units(request.param)


def trial_words(trace, n_bits):
    """The word driven on the bottom plates at each trial, MSB first."""
    settled, words = 0, []
    for i, decision in enumerate(trace):
        trial = settled | (1 << (n_bits - 1 - i))
        words.append(trial)
        if decision:
            settled = trial
    return words


def mismatched(n_bits, rng):
    return ideal_units(n_bits) * (1 + rng.normal(0.0, MISMATCH_SIGMA, 2**n_bits))


def test_the_default_reference_is_the_design_common_mode(units):
    code = 2 ** (n_bits_of(units) - 1)
    assert top_plate_voltage(0.3, code, units, VREF) == top_plate_voltage(
        0.3, code, units, VREF, vcm=VCM_FRACTION * VREF
    )


def test_the_top_plate_reads_vcm_minus_the_remaining_error(units):
    """V_top - Vcm = -(Vin - V_DAC): the guess's error, inverted."""
    rng = np.random.default_rng(SEED)
    weights, total = branch_weights(units), units.sum()
    for _ in range(DRAWS):
        vin = rng.uniform(0.0, VREF)
        code = int(rng.integers(0, 2 ** n_bits_of(units)))
        vcm = VCM_FRACTION * VREF
        v_top = top_plate_voltage(vin, code, units, VREF, vcm=vcm)
        assert v_top - vcm == pytest.approx(-(vin - dac_voltage(code, weights, total, VREF)))


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_every_decision_can_be_read_off_the_top_plate(n_bits):
    """Below Vcm means the guess is still low: keep the bit. Checked on
    mismatched arrays, so it is the real branch weights being read, not an
    idealised binary ladder."""
    rng = np.random.default_rng(SEED + n_bits)
    for _ in range(DRAWS):
        units = mismatched(n_bits, rng)
        vin = rng.uniform(0.0, VREF)
        _, trace = sar_convert(vin, units, VREF)
        vcm = VCM_FRACTION * VREF
        read = [
            int(top_plate_voltage(vin, word, units, VREF, vcm=vcm) <= vcm)
            for word in trial_words(trace, n_bits)
        ]
        assert read == trace


def test_vcm_moves_the_voltage_and_never_a_decision(units):
    """The reference cancels out of the comparison, so any constant works
    arithmetically; it is chosen for where it puts the node, not for what it
    decides."""
    rng = np.random.default_rng(SEED)
    for _ in range(DRAWS):
        vin = rng.uniform(0.0, VREF)
        code = int(rng.integers(0, 2 ** n_bits_of(units)))
        at_ground = top_plate_voltage(vin, code, units, VREF, vcm=0.0)
        at_vcm = top_plate_voltage(vin, code, units, VREF, vcm=VCM_FRACTION * VREF)
        assert at_vcm - at_ground == pytest.approx(VCM_FRACTION * VREF)
        assert (at_ground <= 0.0) == (at_vcm <= VCM_FRACTION * VREF)


def test_a_top_plate_parasitic_shrinks_the_swing_and_moves_no_threshold(units):
    """A capacitance from the top plate to a fixed potential holds the same
    charge at the decision point as at sampling -- both at Vcm -- so it drops
    out of the threshold. What it does is divide the swing the comparator
    sees, which scales the comparator's own offset and noise up by the same
    factor when referred back to the input."""
    rng = np.random.default_rng(SEED)
    total = units.sum()
    c_par = PARASITIC_FRACTION * total
    vcm = VCM_FRACTION * VREF
    for _ in range(DRAWS):
        vin = rng.uniform(0.0, VREF)
        code = int(rng.integers(0, 2 ** n_bits_of(units)))
        clean = top_plate_voltage(vin, code, units, VREF, vcm=vcm) - vcm
        loaded = top_plate_voltage(vin, code, units, VREF, vcm=vcm, c_par=c_par) - vcm
        assert loaded == pytest.approx(clean * total / (total + c_par))
        assert (loaded <= 0.0) == (clean <= 0.0)


def test_referenced_to_vcm_the_first_trial_stays_inside_the_rails(units):
    """The widest swing of a conversion is its first trial. Centred on Vcm it
    spans the reference and no further, so no switch junction on the node is
    forward-biased."""
    msb = 2 ** (n_bits_of(units) - 1)
    for vin in np.linspace(0.0, VREF, 101):
        v_top = top_plate_voltage(vin, msb, units, VREF)
        assert -1e-12 <= v_top <= VREF + 1e-12


def test_referenced_to_ground_the_first_trial_goes_below_it(units):
    """The alternative the design rejects: half the swing lands below ground,
    down to minus half the reference at full-scale input."""
    msb = 2 ** (n_bits_of(units) - 1)
    lowest = min(top_plate_voltage(v, msb, units, VREF, vcm=0.0) for v in (0.0, VREF))
    assert lowest == pytest.approx(-VREF / 2)
