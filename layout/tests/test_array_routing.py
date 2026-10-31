"""Upper-plate connectivity recovered from streamed metal geometry.

Contract: the charge-summing node reaches every electrical unit and no
perimeter or filler dummy; a label alone is not evidence of a connection.
"""

from __future__ import annotations

import numpy as np
import pytest

import sky130
from array_check import LayoutError
from array_check import upper_slots as connected_slots
from array_gds import TOP, write_gds
from array_place import placement
from interface import N_BITS

RESOLUTIONS = (1, 4, N_BITS)


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
        if (p.layers[0], p.datatypes[0]) == sky130.MIM_GDS_UPPER
        and np.ptp(p.polygons[0], axis=0)[0] > np.ptp(p.polygons[0], axis=0)[1]
    ]
    assert rows
    top.polygons.remove(rows[-1])
    library.write_gds(str(path))
    reread = gdspy.GdsLibrary(infile=str(path))
    with pytest.raises(LayoutError, match="upper metal"):
        connected_slots(reread)


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
    with pytest.raises(LayoutError, match="dummy"):
        connected_slots(gdspy.GdsLibrary(infile=str(path)))
