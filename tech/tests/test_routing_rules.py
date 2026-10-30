"""Lower-metal routing constants held to the running process decks.

Contract: contact geometry uses the strictest enclosure on every side and
translates Magic's effective contact edge back to the drawn via edge.
"""

from __future__ import annotations

import re

import pytest

import sky130

PER_MICRON = 1000.0
needs_pdk = pytest.mark.skipif(not sky130.pdk().is_dir(), reason="no process tree")

RULES = (
    (r"via_not_mt\.width\(([\d.]+),", sky130.VIA1_SIDE),
    (r"via2_not_mt\.width\(([\d.]+),", sky130.VIA2_SIDE),
    (r'"via.5a :[^"\n]*: ([\d.]+)um"', sky130.VIA_LANDING_ENCLOSURE),
    (r"m2\.enclosing\(via_outside_periphery, ([\d.]+), projection", sky130.VIA_LANDING_ENCLOSURE),
    (r"m2\.enclosing\(via2, ([\d.]+), projection", sky130.VIA_LANDING_ENCLOSURE),
    (r"m3\.enclosing\(via2, ([\d.]+),", sky130.VIA2_METAL3_ENCLOSURE),
    (r"non_huge_m1\.space\(([\d.]+),", sky130.METAL1_SPACING),
    (r"non_huge_m2\.space\(([\d.]+),", sky130.METAL2_SPACING),
)


@needs_pdk
@pytest.mark.parametrize("pattern, expected", RULES)
def test_lower_metal_dimensions_match_the_deck(pattern, expected):
    match = re.search(pattern, sky130.drc_klayout().read_text())
    assert match
    assert float(match.group(1)) == pytest.approx(expected)


@needs_pdk
def test_bottom_contact_stays_outside_the_capacitor():
    magic = sky130.drc_magic().read_text()
    clearance = re.search(r"spacing via2 \*mimcap (\d+)", magic)
    enclosure = re.search(r"m2\.enclosing\(via2, ([\d.]+),", sky130.drc_klayout().read_text())
    assert clearance and enclosure
    assert sky130.MIM_VIA2_SPACING == pytest.approx(
        float(clearance.group(1)) / PER_MICRON + float(enclosure.group(1))
    )


@needs_pdk
def test_lower_metal_stream_layers_match_the_process():
    deck = sky130.drc_klayout().read_text()
    for name, spec in (
        ("m1", sky130.METAL1_GDS),
        ("via", sky130.VIA1_GDS),
        ("m2", sky130.METAL2_GDS),
        ("via2", sky130.VIA2_GDS),
    ):
        found = re.search(rf'{name}_wildcard = "(\d+)/(\d+)"', deck)
        assert found and tuple(int(v) for v in found.groups()) == spec
    layer, purpose = sky130.METAL2_LABEL_GDS
    path = sky130.pdk() / "libs.tech/klayout/tech" / f"{sky130.pdk().name}.lyp"
    assert f"<name>met2.label - {layer}/{purpose}</name>" in path.read_text()
