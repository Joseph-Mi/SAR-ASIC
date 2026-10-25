"""What the shuttle is told about this project, generated from what it is.

Contract: `info.yaml` is the file the platform reads to decide how many tiles
to give the project, how many analog pins to bond, and what to print on the
datasheet. Two of those are facts this repository already declares -- the pin
map says which signal each pin carries and how many analog pins are claimed,
and the vendored template says how many tiles the floorplan was drawn for --
so they are rendered from the declarations rather than typed beside them.

The one that bites is `analog_pins`. The platform connects that many pins and
no more, counting from zero: a design that claims two and wires three has a
third pin that passed every check in this repository and is not bonded to
anything. It is a number in a YAML file standing between the array and the
reference.

What is *not* derived is the prose: a title, a one-line description, and what
each pin is called on the datasheet. Those are written here because there is
nowhere else they could come from, and they are the only hand-written strings
in the file.

Still M9's, and deliberately not invented here: the submission tree itself --
`src/project.v`, `gds/`, `lef/` and `docs/info.md` -- whose file names have to
match `TOP_MODULE`. This module renders the metadata; assembling the tree
around it is a separate job with the layout in it.
"""

from __future__ import annotations

import pathlib

import template
from interface import N_BITS
from pins import (
    ANALOG_WIDTH,
    CODE,
    DONE,
    EDGE_CAPTURE,
    GROUP_WIDTH,
    HOLD,
    SINGLE_SHOT,
    SPI_CS_N,
    SPI_MISO,
    SPI_MOSI,
    SPI_SCK,
    START,
    UA,
    UI_IN,
    UIO,
    UO_OUT,
    VCM,
    VIN,
    VREF,
    analog_pins,
)

REPO = pathlib.Path(__file__).resolve().parent.parent

#: Where the platform looks for it, and the command that writes it.
RENDERING = "info.yaml"
REGENERATE = "make info"
ENCODING = "utf-8"

#: The chip's own name. It has to start with the platform's prefix, be unique
#: on the shuttle, and match the module in the RTL and the GDS and LEF handed
#: in beside it -- so it is declared here, with the contract, and the RTL is
#: checked against it rather than the other way round.
TOP_MODULE = "tt_um_josephmi_sar_adc"

TITLE = "Charge-redistribution SAR ADC"
AUTHOR = "Joseph-Mi"
DESCRIPTION = (
    "Successive-approximation ADC: a binary-weighted capacitor array as both "
    "sample-and-hold and DAC, a StrongARM latch comparator, and a Verilog "
    "controller with SPI configuration and six design-for-test modes."
)

#: The platform's own word for a hand-drawn project.
LANGUAGE = "Analog"

#: The clock the board is asked for, hertz -- undecided, and rendered as the
#: platform's own placeholder for a field with no answer yet.
#:
#: What the settling law fixes is how short a conversion *step* may be at the
#: slowest corner. What this field states is the clock the board supplies, and
#: the divider sits between the two: the same die runs at a range of clocks,
#: so this is a board choice rather than a measurement, and nothing on the die
#: waits on it. Writing a number before it is chosen would advertise a rate
#: the part was never held to, so it stays at zero until a rate is decided,
#: and CLAUDE.md's open findings carry it so submission cannot forget it.
CLOCK_HZ = 0

#: The second analog supply, which this design does not use: every device in it
#: is a 1.8 V core device, and asking for the 3.3 V rail would mean a different
#: template and a different die.
USES_VAPWR = False

#: Where the platform looks for the files below, relative to the submission
#: root. It lists them by bare name and resolves them itself, so a path here
#: would not be found.
SOURCE_DIR = "src"

#: The file the platform compiles to black-box the design. One entry, because
#: an analog submission hands over a stub and a layout. The directory does not
#: exist yet -- packaging it is M9's -- and a test holds this list against it
#: as soon as it does, so the listing cannot be the thing that is wrong on the
#: day it is read.
SOURCE_FILES = ("project.v",)

#: What each signal is called on the datasheet. The map decides which pin
#: carries what; this decides only how it reads to someone holding the board.
NAMES = {
    DONE: "DONE (result ready, one cycle)",
    HOLD: "HOLD (freeze result pins)",
    START: "START (begin conversion)",
    SINGLE_SHOT: "SINGLE_SHOT (one conversion per request)",
    EDGE_CAPTURE: "EDGE_CAPTURE (capture on rising HOLD)",
    SPI_CS_N: "SPI CS_N",
    SPI_MOSI: "SPI MOSI",
    SPI_MISO: "SPI MISO",
    SPI_SCK: "SPI SCK",
    VIN: "VIN (analog input)",
    VREF: "VREF (reference)",
    VCM: "VCM (common mode)",
}

#: How the platform's own pinout section spells each group, which is not how
#: the port list does: `ui` for the dedicated inputs, `uo` for the dedicated
#: outputs.
SECTIONS = (("ui", UI_IN), ("uo", UO_OUT), ("uio", UIO), ("ua", UA))


def pin_name(signal: str | None) -> str:
    """What the datasheet calls one pin, empty for a pin left unused.

    A result bit is named by arithmetic rather than listed: there is one per
    bit of the resolution, and the two ends are marked because those are the
    pins someone reaches for first.
    """
    if signal is None:
        return ""
    if signal.startswith(CODE):
        index = int(signal[signal.index("[") + 1 : -1])
        edge = {N_BITS - 1: " (MSB)", 0: " (LSB)"}.get(index, "")
        return f"CODE[{index}]{edge}"
    return NAMES[signal]


def _quoted(value: str) -> str:
    return '"' + value.replace('"', '\\"') + '"'


#: The version of the schema the platform reads this file against.
YAML_VERSION = 6


def project_fields() -> dict[str, object]:
    """The `project` mapping, as values rather than as text.

    Separate from the rendering so that what the file claims can be asserted
    without parsing it back: a test that reads YAML needs a YAML library, and
    the digital half of CI builds its own toolchain and has none. The round
    trip is still checked where a library exists, which is what keeps these
    two from drifting.
    """
    return {
        "title": TITLE,
        "author": AUTHOR,
        "discord": "",
        "description": DESCRIPTION,
        "language": LANGUAGE,
        "clock_hz": CLOCK_HZ,
        "tiles": template.tiles(),
        "analog_pins": len(analog_pins()),
        "uses_vapwr": USES_VAPWR,
        "top_module": TOP_MODULE,
        "source_files": list(SOURCE_FILES),
    }


def pinout() -> dict[str, str]:
    """Every pin the platform lists, and what the datasheet calls it."""
    found = {}
    for section, group in SECTIONS:
        count = ANALOG_WIDTH if section == "ua" else GROUP_WIDTH
        for index in range(count):
            signal = group[index] if index < len(group) else None
            found[f"{section}[{index}]"] = pin_name(signal)
    return found


def as_yaml() -> str:
    """The file, in the platform's own key order and shape.

    Written out rather than dumped from a mapping: the platform's template is
    a commented document whose comments are instructions to whoever reads the
    file next, and a serialiser would drop them.
    """
    field = project_fields()
    lines = [
        "# Tiny Tapeout project information.",
        f"# Generated from the pin map and the vendored template: {REGENERATE}.",
        "# Do not edit -- a hand edit is a pin assignment that nothing checks.",
        "project:",
        f"  title:        {_quoted(field['title'])}",
        f"  author:       {_quoted(field['author'])}",
        f"  discord:      {_quoted(field['discord'])}",
        f"  description:  {_quoted(field['description'])}",
        f"  language:     {_quoted(field['language'])}",
        f"  clock_hz:     {field['clock_hz']}",
        "",
        "  # Tiles, as the vendored template in layout/ draws them.",
        f"  tiles: {_quoted(field['tiles'])}",
        "",
        "  # Analog pins claimed. The platform bonds this many, counting from",
        "  # ua[0]: a signal on a pin past it is not connected.",
        f"  analog_pins: {field['analog_pins']}",
        f"  uses_vapwr: {str(field['uses_vapwr']).lower()}",
        "",
        f"  top_module:  {_quoted(field['top_module'])}",
        "",
        "  source_files:",
        *[f"    - {_quoted(name)}" for name in field["source_files"]],
        "",
        "# The pinout, for the datasheet. Unused pins are left empty.",
        "pinout:",
    ]
    listed = pinout()
    for section, _ in SECTIONS:
        lines.append("")
        lines += [
            f"  {key}: {_quoted(name)}"
            for key, name in listed.items()
            if key.startswith(f"{section}[")
        ]
    lines += ["", "# Do not change!", f"yaml_version: {YAML_VERSION}", ""]
    return "\n".join(lines)


def rendered() -> dict[str, str]:
    return {RENDERING: as_yaml()}


def main() -> None:
    for path, text in rendered().items():
        (REPO / path).write_text(text, encoding=ENCODING)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
