"""Upper-plate connectivity recovered from streamed metal geometry.

Contract: the charge-summing node reaches every electrical unit and no
perimeter or filler dummy; a label alone is not evidence of a connection.
"""

from __future__ import annotations

import numpy as np
import pytest

import sky130
from array_gds import SLOT_PROPERTY, TOP, UPPER_NET_LABEL, write_gds
from array_place import placement
from interface import N_BITS

RESOLUTIONS = (1, 4, N_BITS)


def connected_slots(library):
    """Find the labelled island by unioning actual upper-metal polygons."""
    import gdspy

    top = library.cells[TOP]
    labels = [label for label in top.labels if label.text == UPPER_NET_LABEL]
    assert len(labels) == 1
    polygons = top.get_polygons(by_spec=True)[sky130.MIM_GDS_UPPER]
    merged = gdspy.boolean(polygons, None, "or", max_points=0)
    islands = [p for p in merged.polygons if gdspy.inside([labels[0].position], [p])[0]]
    assert len(islands) == 1
    slots = set()
    for ref in top.references:
        contacts = ref.get_polygons(by_spec=True)[sky130.MIM_GDS_CONTACT]
        (contact,) = contacts
        centre = contact.mean(axis=0)
        if gdspy.inside([centre], islands)[0]:
            slot = ref.properties.get(SLOT_PROPERTY)
            assert slot is not None, "the charge-summing net reaches an edge or filler dummy"
            slots.add(int(slot))
    return slots


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_common_upper_plate_reaches_exactly_the_electrical_units(tmp_path, n_bits):
    gdspy = pytest.importorskip("gdspy")
    path = tmp_path / "sar_array.gds"
    write_gds(placement(n_bits), path)
    library = gdspy.GdsLibrary(infile=str(path))
    assert connected_slots(library) == set(range(2**n_bits))


def test_missing_row_connection_is_detected(tmp_path):
    gdspy = pytest.importorskip("gdspy")
    drawn = placement()
    path = tmp_path / "sar_array.gds"
    write_gds(drawn, path)
    library = gdspy.GdsLibrary(infile=str(path))
    top = library.cells[TOP]
    rows = [
        p
        for p in top.polygons
        if np.ptp(p.polygons[0], axis=0)[0] > np.ptp(p.polygons[0], axis=0)[1]
    ]
    assert rows
    top.polygons.remove(rows[-1])
    library.write_gds(str(path))
    reread = gdspy.GdsLibrary(infile=str(path))
    assert connected_slots(reread) != set(range(2**N_BITS))


def test_a_short_to_a_dummy_is_detected(tmp_path):
    gdspy = pytest.importorskip("gdspy")
    drawn = placement()
    path = tmp_path / "sar_array.gds"
    write_gds(drawn, path)
    library = gdspy.GdsLibrary(infile=str(path))
    top = library.cells[TOP]
    active = next(u for u in drawn.units if u.slot is not None)
    dummy = next(u for u in drawn.units if u.row == active.row and u.slot is None)
    lower = (dummy.x + drawn.side / 2, active.y + drawn.side / 2)
    upper = (active.x + drawn.side / 2, active.y + drawn.side / 2)
    top.add(
        gdspy.FlexPath(
            [lower, upper],
            sky130.MIM_CONTACT_SIDE,
            layer=sky130.MIM_GDS_UPPER[0],
            datatype=sky130.MIM_GDS_UPPER[1],
        )
    )
    library.write_gds(str(path))
    with pytest.raises(AssertionError, match="dummy"):
        connected_slots(gdspy.GdsLibrary(infile=str(path)))
