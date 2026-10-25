"""The file the shuttle reads, enforced against the design it describes.

A committed artifact that nothing checks agrees with the declarations on the
day it was generated and never again. The one claim that makes every other
claim here worth making is the first test: that the file on disk is what the
pin map and the vendored template generate today.

`analog_pins` gets its own tests. It is the field that decides how many pins
are bonded, there is no way to observe it being wrong from inside this
repository, and the symptom on silicon is a reference that is not connected.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

import submission
import template
from pins import ANALOG_WIDTH, GROUP_WIDTH, analog_pins, assignments

REPO = pathlib.Path(__file__).resolve().parents[2]

#: Sections of the pinout, and how many pins the platform lists in each.
SECTION_WIDTH = {"ui": GROUP_WIDTH, "uo": GROUP_WIDTH, "uio": GROUP_WIDTH, "ua": ANALOG_WIDTH}


@pytest.fixture(scope="module")
def generated() -> str:
    return submission.as_yaml()


@pytest.fixture(scope="module")
def parsed(generated) -> dict:
    return yaml.safe_load(generated)


def test_the_committed_file_is_what_the_declarations_generate(generated):
    """The test that makes the rest of this file meaningful."""
    path = REPO / submission.RENDERING
    assert path.exists(), f"never generated: run `{submission.REGENERATE}`"
    assert path.read_text(encoding=submission.ENCODING) == generated, (
        f"{submission.RENDERING} is stale: run `{submission.REGENERATE}`"
    )


def test_it_is_yaml_the_platform_can_read(parsed):
    assert set(parsed) == {"project", "pinout", "yaml_version"}


def test_it_claims_exactly_the_analog_pins_the_map_uses(parsed):
    """Fewer and the reference is not bonded; more and a pin is paid for and
    carries nothing."""
    assert parsed["project"]["analog_pins"] == len(analog_pins())


def test_the_claim_covers_every_analog_pin_the_pinout_names(parsed):
    """The count and the pinout are rendered from the same map, so they cannot
    disagree -- and this is what says so, because the platform reads the count
    and a human reads the pinout."""
    named = [i for i in range(ANALOG_WIDTH) if parsed["pinout"][f"ua[{i}]"]]
    assert named == list(range(parsed["project"]["analog_pins"]))


def test_the_tiles_are_the_ones_the_vendored_template_draws(parsed):
    """The floorplan budget was divided out of that file; a submission that
    asks for a different size asks for a different die."""
    assert parsed["project"]["tiles"] == template.tiles()


def test_the_top_module_is_the_name_the_contract_declares(parsed):
    """The same string has to appear in the YAML, the Verilog, and the GDS and
    LEF file names. `test_tile` holds the Verilog against this declaration;
    this holds the YAML against it."""
    assert parsed["project"]["top_module"] == submission.TOP_MODULE


def test_every_section_lists_the_pins_the_platform_gives(parsed):
    for section, width in sorted(SECTION_WIDTH.items()):
        keys = [k for k in parsed["pinout"] if k.startswith(f"{section}[")]
        assert len(keys) == width, f"{section}: {len(keys)} pins listed, the platform gives {width}"


def test_every_pin_the_design_uses_is_named_and_every_spare_one_is_blank(parsed):
    """An empty description on a pin that carries something is a datasheet
    that omits it; a description on a spare pin is one that invents it."""
    sections = {"ui_in": "ui", "uo_out": "uo", "uio": "uio", "ua": "ua"}
    used = {(sections[group], bit) for (group, bit), _ in assignments().items()}
    for section, width in sorted(SECTION_WIDTH.items()):
        for bit in range(width):
            named = bool(parsed["pinout"][f"{section}[{bit}]"])
            assert named == ((section, bit) in used), f"{section}[{bit}] is named: {named}"


def test_the_result_is_named_end_to_end(parsed):
    """Those pins are what a user reads a number off, so the datasheet has to
    say which end is which -- the map puts the top bits on the dedicated
    outputs for exactly that reason."""
    named = " ".join(str(v) for v in parsed["pinout"].values())
    assert "(MSB)" in named and "(LSB)" in named


def test_the_second_analog_supply_is_not_asked_for(parsed):
    """Asking for it means a different template and a different die, and every
    device in this design is a 1.8 V core device."""
    assert parsed["project"]["uses_vapwr"] is False


def test_nothing_in_it_is_empty_that_the_platform_prints(parsed):
    for field in ("title", "author", "description", "language", "top_module"):
        assert parsed["project"][field], field
