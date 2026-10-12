"""The process facts, held to their own contract.

What the PDK says is checked against the PDK, by the tests that can run a
simulator. These check the other half: that the expressions built on those
numbers behave, and that a geometry they cannot draw is refused rather than
extrapolated into. They need no tools, so they run everywhere -- which matters
because a silently wrong unit capacitance moves every absolute figure the
project quotes.
"""

from __future__ import annotations

import numpy as np
import pytest

import sky130

#: A drawn square well above the minimum, micrometres, and a rectangle of the
#: same drawn area: the plate bias acts on both dimensions, so the two do not
#: come out equal.
SIDE = 10.0
LONG, SHORT = 25.0, 4.0

#: Reverse biases spanning a supply, volts.
BIASES = (0.0, 0.45, 0.9, 1.8)

#: A width and length a device is asked for, micrometres.
WIDTH, LENGTH = 2.0, 0.15


def test_a_bigger_plate_holds_more():
    for corner in sky130.CAP_CORNERS:
        assert sky130.mim_capacitance(2 * SIDE, 2 * SIDE, corner) > (
            sky130.mim_capacitance(SIDE, SIDE, corner)
        )


def test_the_bias_makes_a_square_worth_more_than_a_strip_of_equal_area():
    """The reason a unit is square. The plate runs past every drawn edge, so a
    long thin shape gains more edge than a square of the same drawn area --
    and a unit that differs from its neighbours in shape differs in value."""
    assert LONG * SHORT == pytest.approx(SIDE * SIDE)
    assert sky130.mim_capacitance(LONG, SHORT) > sky130.mim_capacitance(SIDE, SIDE)


def test_the_corners_order_the_way_their_parameters_do():
    low, typical, high = (sky130.mim_unit(c) for c in sky130.CAP_CORNERS)
    assert low < typical < high


def test_a_diffusion_sheds_capacitance_as_it_is_pushed_away_from_its_body():
    for width in (1.0, WIDTH):
        seen = [sky130.diffusion_capacitance(width, b) for b in BIASES]
        assert seen == sorted(seen, reverse=True)
        assert seen[0] == pytest.approx(sky130.DIFFUSION_ZERO_BIAS * width)


def test_a_diffusion_scales_with_the_width_it_is_drawn_at():
    assert sky130.diffusion_capacitance(2 * WIDTH) == pytest.approx(
        2 * sky130.diffusion_capacitance(WIDTH)
    )


def test_a_diffusion_takes_a_curve_of_biases_as_readily_as_one():
    """So a figure of the law and a single number come from one expression."""
    curve = sky130.diffusion_capacitance(WIDTH, np.array(BIASES))
    assert curve.shape == (len(BIASES),)
    assert curve[0] == pytest.approx(sky130.diffusion_capacitance(WIDTH, BIASES[0]))


def test_a_devices_junction_geometry_follows_from_its_width():
    """The wrapper draws its mismatch against the geometry it is called with,
    so the areas and perimeters belong on the call rather than at a default."""
    one = sky130.mosfet(WIDTH, LENGTH)
    wider = sky130.mosfet(2 * WIDTH, LENGTH)
    assert one["W"] == WIDTH and one["L"] == LENGTH
    assert wider["ad"] > one["ad"]
    assert wider["pd"] > one["pd"]
    assert wider["nrd"] < one["nrd"]


@pytest.mark.parametrize(
    "call",
    [
        lambda: sky130.mim_capacitance(SIDE, SIDE, "tt"),
        lambda: sky130.mim_capacitance(-sky130.CAP_MIM_BIAS["typical"], SIDE),
        lambda: sky130.mim_capacitance(SIDE, -sky130.CAP_MIM_BIAS["typical"]),
        lambda: sky130.diffusion_capacitance(0.0),
        lambda: sky130.diffusion_capacitance(-WIDTH),
        lambda: sky130.diffusion_capacitance(WIDTH, -0.1),
    ],
)
def test_a_geometry_the_process_cannot_draw_is_refused(call):
    """Refused rather than extrapolated. A plate the bias has eaten and a
    forward-biased diffusion are both regimes the expressions do not describe,
    and a number returned there would look like every other number."""
    with pytest.raises(ValueError):
        call()
