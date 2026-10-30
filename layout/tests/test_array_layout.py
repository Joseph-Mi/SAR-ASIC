"""Placement and stream-out held to the electrical unit ordering.

Contract: expectations come from the permutation, branch ownership and process
geometry, rather than a second placement table.
"""

from __future__ import annotations

import numpy as np
import pytest

import sky130
import template
from array_gds import read_units, write_gds
from array_place import DUMMY_RING, placement
from interface import N_BITS
from mismatch import interleaved
from sar import branch_slices

RESOLUTIONS = (1, 4, N_BITS)
GDS_TOLERANCE = 1e-3


def permutation(units):
    ordered = sorted((u for u in units if u.slot is not None), key=lambda u: (u.y, u.x))
    result = np.empty(len(ordered), dtype=int)
    for physical, unit in enumerate(ordered):
        result[unit.slot] = physical
    return result


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_positions_implement_the_golden_permutation(n_bits):
    drawn = placement(n_bits)
    np.testing.assert_array_equal(permutation(drawn.units), interleaved(n_bits))
    for branch, slots in enumerate(branch_slices(n_bits)):
        assert {u.slot for u in drawn.units if u.branch == branch} == set(
            range(slots.start, slots.stop)
        )
    terminator = [u for u in drawn.units if u.slot == 2**n_bits - 1]
    assert len(terminator) == 1
    assert terminator[0].branch == n_bits


def test_the_ring_and_unused_sites_are_filled_with_dummies():
    drawn = placement()
    sites = {(u.column, u.row): u for u in drawn.units}
    assert len(sites) == drawn.columns * drawn.rows
    for (column, row), unit in sites.items():
        perimeter = (
            column < DUMMY_RING
            or column >= drawn.columns - DUMMY_RING
            or row < DUMMY_RING
            or row >= drawn.rows - DUMMY_RING
        )
        if perimeter:
            assert unit.slot is None
            assert unit.branch is None
    assert sum(u.slot is not None for u in sites.values()) == 2**N_BITS


def test_drawn_geometry_and_keepaway_fit_the_strip():
    drawn = placement()
    width, height = template.analog_strip()
    fit = sky130.mim_fit(2**N_BITS, drawn.side, height, ring=DUMMY_RING, shared=False)
    assert fit is not None
    assert drawn.rows == fit[0]
    assert drawn.columns - 2 * DUMMY_RING == fit[1]
    for unit in drawn.units:
        assert unit.x >= sky130.MIM_METAL_SPACING
        assert unit.y >= sky130.MIM_METAL_SPACING
        assert unit.x + drawn.side + sky130.MIM_METAL_SPACING <= width
        assert unit.y + drawn.side + sky130.MIM_METAL_SPACING <= height
    assert sky130.mim_keep_out(sky130.mim_row(drawn.columns, drawn.side)) == pytest.approx(fit[2])


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_streamed_positions_and_ownership_match_the_golden_model(tmp_path, n_bits):
    pytest.importorskip("gdspy")
    drawn = placement(n_bits)
    path = tmp_path / "sar_array.gds"
    write_gds(drawn, path)
    units = read_units(path)
    np.testing.assert_array_equal(permutation(units), interleaved(n_bits))
    assert sorted((u.slot, u.branch) for u in units if u.slot is not None) == sorted(
        (u.slot, u.branch) for u in drawn.units if u.slot is not None
    )
    assert len(units) == len(drawn.units)


def test_readback_detects_a_swapped_placement(tmp_path):
    gdspy = pytest.importorskip("gdspy")
    path = tmp_path / "sar_array.gds"
    write_gds(placement(), path)
    library = gdspy.GdsLibrary(infile=str(path))
    refs = [r for r in library.cells["sar_array"].references if r.ref_cell.name != "dummy"]
    refs[0].origin, refs[1].origin = refs[1].origin, refs[0].origin
    library.write_gds(str(path))
    assert not np.array_equal(permutation(read_units(path)), interleaved(N_BITS))


@pytest.mark.parametrize("kwargs", [{"n_bits": 0}, {"height": 1.0}, {"width": 1.0}])
def test_an_unplaceable_array_is_refused(kwargs):
    with pytest.raises(ValueError):
        placement(**kwargs)


def test_streamed_capacitors_have_the_specified_plates_and_contacts(tmp_path):
    gdspy = pytest.importorskip("gdspy")
    path = tmp_path / "sar_array.gds"
    drawn = placement()
    write_gds(drawn, path)
    library = gdspy.GdsLibrary(infile=str(path))
    refs = library.cells["sar_array"].references
    assert len(refs) == len(drawn.units)
    for ref in refs:
        polygons = ref.get_polygons(by_spec=True)
        (plate,) = polygons[sky130.MIM_GDS_PLATE]
        (bottom,) = polygons[sky130.MIM_GDS_BOTTOM]
        (contact,) = polygons[sky130.MIM_GDS_CONTACT]
        (upper,) = polygons[sky130.MIM_GDS_UPPER]
        np.testing.assert_allclose(
            plate.max(axis=0) - plate.min(axis=0), drawn.side, atol=GDS_TOLERANCE, rtol=0
        )
        np.testing.assert_allclose(
            plate.min(axis=0) - bottom.min(axis=0),
            sky130.MIM_PLATE_ENCLOSURE,
            atol=GDS_TOLERANCE,
            rtol=0,
        )
        np.testing.assert_allclose(
            bottom.max(axis=0) - plate.max(axis=0),
            sky130.MIM_PLATE_ENCLOSURE,
            atol=GDS_TOLERANCE,
            rtol=0,
        )
        assert np.all(contact.min(axis=0) > plate.min(axis=0))
        assert np.all(contact.max(axis=0) < plate.max(axis=0))
        assert np.prod(upper.max(axis=0) - upper.min(axis=0)) >= sky130.METAL4_MIN_AREA
    actual = {(u.column, u.row): u for u in read_units(path)}
    for unit in drawn.units:
        found = actual[(unit.column, unit.row)]
        assert found.x == pytest.approx(unit.x, abs=GDS_TOLERANCE)
        assert found.y == pytest.approx(unit.y, abs=GDS_TOLERANCE)


def test_readback_uses_plate_geometry_rather_than_reference_origins(tmp_path):
    gdspy = pytest.importorskip("gdspy")
    path = tmp_path / "sar_array.gds"
    drawn = placement()
    write_gds(drawn, path)
    library = gdspy.GdsLibrary(infile=str(path))
    branch = library.cells["branch_0"]
    displacement = sky130.mim_pitch(drawn.side)
    for polygon in branch.polygons:
        polygon.translate(displacement, 0)
    library.write_gds(str(path))
    recovered = next(u for u in read_units(path) if u.branch == 0)
    expected = next(u for u in drawn.units if u.branch == 0)
    assert recovered.x == pytest.approx(expected.x + displacement)
