"""Bottom-plate ownership checked by extracting the streamed metal stack.

Contract: each labelled branch reaches exactly its golden-model slots through
metal and vias, without borrowing connectivity from instance names.
"""

from __future__ import annotations

import pytest

import sky130
from array_bottom import branch_label
from array_gds import TOP, write_gds
from array_place import placement
from interface import N_BITS
from sar import branch_slices

RESOLUTIONS = (1, 4, N_BITS)


def extract(path):
    """Extract a flat conductor graph without treating a capacitor as a short."""
    import klayout.db as db

    layout = db.Layout()
    layout.read(str(path))
    top = layout.cell(TOP)
    extractor = db.LayoutToNetlist(TOP, layout.dbu)
    layers = {}
    for name, spec in (
        ("m1", sky130.METAL1_GDS),
        ("v1", sky130.VIA1_GDS),
        ("m2", sky130.METAL2_GDS),
        ("v2", sky130.VIA2_GDS),
        ("m3", sky130.MIM_GDS_BOTTOM),
    ):
        region = db.Region(top.begin_shapes_rec(layout.layer(*spec)))
        extractor.register(region, name)
        extractor.connect(region)
        layers[name] = region
    for left, right in (("m1", "v1"), ("v1", "m2"), ("m2", "v2"), ("v2", "m3")):
        extractor.connect(layers[left], layers[right])
    extractor.extract_netlist()

    def probe(name, x, y):
        point = db.Point(round(x / layout.dbu), round(y / layout.dbu))
        net = extractor.probe_net(layers[name], point)
        assert net is not None, f"no conductor at {name} ({x}, {y})"
        return net.cluster_id

    return extractor, probe


@pytest.mark.parametrize("n_bits", RESOLUTIONS)
def test_extracted_branches_match_the_golden_unit_sets(tmp_path, n_bits):
    gdspy = pytest.importorskip("gdspy")
    pytest.importorskip("klayout.db")
    drawn = placement(n_bits)
    path = tmp_path / "sar_array.gds"
    write_gds(drawn, path)
    library = gdspy.GdsLibrary(infile=str(path))
    extractor, probe = extract(path)
    labels = {label.text: label for label in library.cells[TOP].labels}
    nets = {}
    for branch in range(n_bits + 1):
        label = labels[branch_label(branch, n_bits)]
        nets[branch] = probe("m2", *label.position)
    assert len(set(nets.values())) == n_bits + 1, "bottom branches are shorted"
    members = {branch: set() for branch in nets}
    for unit in drawn.units:
        net = probe("m3", unit.x + drawn.side / 2, unit.y + drawn.side / 2)
        for branch, wanted in nets.items():
            if net == wanted:
                assert unit.slot is not None, "a bottom branch reaches a perimeter dummy"
                members[branch].add(unit.slot)
    for branch, slots in enumerate(branch_slices(n_bits)):
        assert members[branch] == set(range(slots.start, slots.stop))
    assert members[n_bits] == {2**n_bits - 1}
    assert extractor.netlist() is not None


def test_a_removed_bottom_via_is_detected(tmp_path):
    gdspy = pytest.importorskip("gdspy")
    pytest.importorskip("klayout.db")
    drawn = placement()
    path = tmp_path / "sar_array.gds"
    write_gds(drawn, path)
    library = gdspy.GdsLibrary(infile=str(path))
    cell = library.cells["branch_0"]
    cell.polygons = [p for p in cell.polygons if (p.layers[0], p.datatypes[0]) != sky130.VIA2_GDS]
    library.write_gds(str(path))
    extractor, probe = extract(path)
    label = next(
        label for label in library.cells[TOP].labels if label.text == branch_label(0, N_BITS)
    )
    unit = next(u for u in drawn.units if u.slot == 0)
    assert probe("m3", unit.x + drawn.side / 2, unit.y + drawn.side / 2) != probe(
        "m2", *label.position
    )
    assert extractor.netlist() is not None


def test_a_short_between_bottom_branches_is_detected(tmp_path):
    gdspy = pytest.importorskip("gdspy")
    pytest.importorskip("klayout.db")
    drawn = placement()
    path = tmp_path / "sar_array.gds"
    write_gds(drawn, path)
    library = gdspy.GdsLibrary(infile=str(path))
    top = library.cells[TOP]
    labels = {label.text: label for label in top.labels}
    first, second = (labels[branch_label(branch, N_BITS)].position for branch in range(2))
    top.add(
        gdspy.FlexPath(
            [first, (first[0], second[1]), second],
            sky130.VIA2_SIDE,
            layer=sky130.METAL2_GDS[0],
            datatype=sky130.METAL2_GDS[1],
        )
    )
    library.write_gds(str(path))
    extractor, probe = extract(path)
    assert probe("m2", *first) == probe("m2", *second)
    assert extractor.netlist() is not None


def test_the_routed_gds_stays_inside_the_analog_strip(tmp_path):
    gdspy = pytest.importorskip("gdspy")
    import template

    path = tmp_path / "sar_array.gds"
    write_gds(placement(), path)
    library = gdspy.GdsLibrary(infile=str(path))
    lower, upper = library.cells[TOP].get_bounding_box()
    width, height = template.analog_strip()
    assert lower[0] >= 0 and lower[1] >= 0
    assert upper[0] <= width and upper[1] <= height
