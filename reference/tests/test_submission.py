"""The file the shuttle reads, enforced against the design it describes.

A committed artifact that nothing checks agrees with the declarations on the
day it was generated and never again. The one claim that makes every other
claim here worth making is the first test: that the file on disk is what the
pin map and the vendored template generate today.

`analog_pins` gets its own tests. It is the field that decides how many pins
are bonded, there is no way to observe it being wrong from inside this
repository, and the symptom on silicon is a reference that is not connected.

What these assert on is the generator's own data rather than the file parsed
back, because parsing YAML needs a library and the digital half of CI builds
its own toolchain without one. The round trip is checked separately, wherever
a library is to be had, which is what stops the data and the rendering from
drifting apart.
"""

from __future__ import annotations

import pathlib

import pytest

import submission
import template
from pins import ANALOG_WIDTH, GROUP_WIDTH, analog_pins, assignments

REPO = pathlib.Path(__file__).resolve().parents[2]

#: Sections of the pinout, and how many pins the platform lists in each.
SECTION_WIDTH = {"ui": GROUP_WIDTH, "uo": GROUP_WIDTH, "uio": GROUP_WIDTH, "ua": ANALOG_WIDTH}

#: How each section of the pinout is named against the group the map declares.
#: The platform's own spelling is shorter than the port's: `ui`, not `ui_in`.
SECTIONS = {"ui_in": "ui", "uo_out": "uo", "uio": "uio", "ua": "ua"}


@pytest.fixture(scope="module")
def fields() -> dict:
    return submission.project_fields()


@pytest.fixture(scope="module")
def listed() -> dict:
    return submission.pinout()


def test_the_committed_file_is_what_the_declarations_generate():
    """The test that makes the rest of this file worth reading."""
    path = REPO / submission.RENDERING
    assert path.exists(), f"never generated: run `{submission.REGENERATE}`"
    assert path.read_text(encoding=submission.ENCODING) == submission.as_yaml(), (
        f"{submission.RENDERING} is stale: run `{submission.REGENERATE}`"
    )


def test_the_rendering_is_yaml_that_says_what_the_generator_says():
    """The round trip, where there is a library to do it with: the rendering
    and the data behind it are written separately, so this is what holds them
    together. Skipped rather than reimplemented where PyYAML is absent -- a
    hand-rolled parser would be a second thing to get wrong."""
    yaml = pytest.importorskip("yaml", reason="PyYAML is not installed")
    parsed = yaml.safe_load(submission.as_yaml())
    assert set(parsed) == {"project", "pinout", "yaml_version"}
    assert parsed["project"] == submission.project_fields()
    assert parsed["pinout"] == submission.pinout()
    assert parsed["yaml_version"] == submission.YAML_VERSION


def test_it_claims_exactly_the_analog_pins_the_map_uses(fields):
    """Fewer and the reference is not bonded; more and a pin is paid for and
    carries nothing."""
    assert fields["analog_pins"] == len(analog_pins())


def test_the_claim_covers_every_analog_pin_the_pinout_names(fields, listed):
    """The count and the pinout come from the same map, so they cannot
    disagree -- and this says so, because the platform reads the count while a
    human reads the pinout."""
    named = [i for i in range(ANALOG_WIDTH) if listed[f"ua[{i}]"]]
    assert named == list(range(fields["analog_pins"]))


def test_the_tiles_are_the_ones_the_vendored_template_draws(fields):
    """The floorplan budget was divided out of that file; a submission asking
    for a different size asks for a different die."""
    assert fields["tiles"] == template.tiles()


def test_the_top_module_is_the_name_the_contract_declares(fields):
    """The same string has to appear in the YAML, the Verilog, and the GDS and
    LEF file names. `test_tile` holds the Verilog against this declaration;
    this holds the file the shuttle reads against it."""
    assert fields["top_module"] == submission.TOP_MODULE


def test_every_section_lists_the_pins_the_platform_gives(listed):
    for section, width in sorted(SECTION_WIDTH.items()):
        keys = [k for k in listed if k.startswith(f"{section}[")]
        assert len(keys) == width, f"{section}: {len(keys)} listed, the platform gives {width}"


def test_every_pin_the_design_uses_is_named_and_every_spare_one_is_blank(listed):
    """An empty description on a pin that carries something is a datasheet that
    omits it; a description on a spare pin is one that invents it."""
    used = {(SECTIONS[group], bit) for (group, bit), _ in assignments().items()}
    for section, width in sorted(SECTION_WIDTH.items()):
        for bit in range(width):
            named = bool(listed[f"{section}[{bit}]"])
            assert named == ((section, bit) in used), f"{section}[{bit}] is named: {named}"


def test_the_result_is_named_end_to_end(listed):
    """Those pins are what a user reads a number off, so the datasheet has to
    say which end is which -- the map puts the top bits on the dedicated
    outputs for exactly that reason."""
    named = " ".join(listed.values())
    assert "(MSB)" in named and "(LSB)" in named


def test_the_second_analog_supply_is_not_asked_for(fields):
    """Asking for it means a different template and a different die, and every
    device in this design is a 1.8 V core device."""
    assert fields["uses_vapwr"] is False


def test_nothing_in_it_is_empty_that_the_platform_prints(fields):
    for name in ("title", "author", "description", "language", "top_module"):
        assert fields[name], name
