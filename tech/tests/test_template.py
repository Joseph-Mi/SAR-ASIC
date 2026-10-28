"""The tile template, read rather than transcribed.

Two jobs. The first is the reader itself: a regex that stops matching partway
through a file returns a short answer and no error, which is the failure mode
a parser like this has, so what it read is checked against the file's own
counts. The second is the floorplan budget, whose numbers were derived by hand
from this file and are the kind that stay right until the template moves.
"""

from __future__ import annotations

import pathlib
import re

import pytest

import template
from tinytapeout import GROUND, SUPPLY, SUPPLY_ANALOG

REPO = next(p for p in pathlib.Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
FLOORPLAN = REPO / "docs" / "floorplan.md"

#: The die as the floorplan document states it, in micrometres: two numbers
#: written as a product. The document explains them at length; this finds the
#: pair to compare.
DOCUMENTED = re.compile(r"\*\*(\d+\.\d+) x (\d+\.\d+) um\*\*")

#: The split as that document states it: the digital half's height, which is
#: the one number in the budget that is a decision rather than a reading.
SPLIT = re.compile(r"^    digital\s+\d+\.\d+ x (\d+(?:\.\d+)?)\s", re.M)

#: Edges a pin may sit on, as a fraction of the die's height: the template
#: puts every pin on the top or the bottom, which is what decides that the
#: digital half goes at the top and the analog half at the bottom.
EDGE = 0.05


def test_the_template_is_vendored_where_the_reader_looks_for_it():
    """It is committed so that a shuttle-side change shows up as a diff rather
    than as a surprise at submission; `layout/PROVENANCE` says where from."""
    assert template.PATH.exists(), f"{template.PATH} is missing"


def test_the_pins_read_are_the_pins_the_file_says_it_holds():
    """The reader's own guard, asserted rather than trusted: this is the test
    that fails if the DEF's syntax ever drifts from what the pattern expects."""
    assert template.pins()
    assert len(template.pins()) == len({p.declaration for p in template.pins()})


def test_every_pin_is_on_one_of_the_two_edges():
    """Each half's pins are on its own edge, which is the whole reason the
    floorplan puts the digital half at the top and the analog at the bottom."""
    _, height = template.die_area()
    for pin in template.pins():
        near = min(pin.y, height - pin.y)
        assert near <= EDGE * height, f"{pin.declaration} sits {pin.y:g} um up a {height:g} um die"


def test_the_analog_pins_are_on_the_opposite_edge_to_the_digital_ones():
    """If they shared an edge the split would be a free choice; they do not."""
    _, height = template.die_area()
    analog = [p.y for p in template.pins() if p.name == template.analog_group().name]
    digital = [p.y for p in template.pins() if p.name != template.analog_group().name]
    assert max(analog) < height / 2 < min(digital)


def test_the_analog_pins_are_evenly_spaced():
    """A pitch is only a pitch if every gap is the same one."""
    assert template.analog_pitch() > 0


def test_the_floorplan_document_states_the_die_the_template_draws():
    """The budget's numbers were derived from this file by hand. A template
    that moves has to move them, and this is what says so."""
    found = DOCUMENTED.search(FLOORPLAN.read_text())
    assert found, f"{FLOORPLAN.name} states no die size to check"
    stated = tuple(float(v) for v in found.groups())
    assert stated == template.die_area(), f"the document says {stated}"


def test_the_floorplan_document_states_the_split_that_is_declared():
    """For the same reason as the die above, and it is the weaker of the two
    directions: the die moves only when the template is revendored, while the
    split is ours to change, and a document left behind by that is a budget
    argued from a number nothing uses."""
    found = SPLIT.search(FLOORPLAN.read_text())
    assert found, f"{FLOORPLAN.name} states no split to check"
    assert float(found.group(1)) == pytest.approx(template.DIGITAL_HEIGHT)


def test_the_split_leaves_a_strip_of_the_die():
    """And leaves it the full width, the two halves being stacked."""
    width, height = template.analog_strip()
    assert (width, height) == (
        template.die_area()[0],
        template.die_area()[1] - template.DIGITAL_HEIGHT,
    )


@pytest.mark.parametrize("height", [0.0, -1.0, 1e6])
def test_a_split_that_does_not_divide_the_die_is_refused(height, monkeypatch):
    """A strip of no height or of negative height is a budget that would pass
    every check below it while describing nothing."""
    monkeypatch.setattr(template, "DIGITAL_HEIGHT", height)
    with pytest.raises(ValueError):
        template.analog_strip()


def test_the_template_carries_no_supply_among_its_pins():
    """The supplies are special nets in the layout and ports in the platform's
    Verilog, which is why the port list is checked against both files and not
    against this one alone."""
    names = {p.name for p in template.pins()}
    assert not names & {GROUND, SUPPLY, SUPPLY_ANALOG}


@pytest.mark.parametrize("call", [template.die_area, template.pins, template.groups])
def test_a_missing_template_is_refused_rather_than_read_as_empty(call, monkeypatch):
    """A reader that answers from a file that is not there answers zero pins
    on a die of no size, and every test above would pass."""
    monkeypatch.setattr(template, "PATH", template.PATH.with_name("absent.def"))
    with pytest.raises(FileNotFoundError):
        call()
