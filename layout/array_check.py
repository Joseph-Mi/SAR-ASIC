"""Read-only geometry and connectivity validation of a supplied array layout.

Contract: the input is the artifact under test; validation never regenerates
it. Electrical slot metadata and branch cells must survive geometry edits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import shutil
import subprocess
import sys
import tempfile

import sky130
import template
from array_bottom import branch_label
from array_gds import GDS_PRECISION, GDS_UNIT, SLOT_PROPERTY, TOP, UPPER_NET_LABEL, read_units
from array_place import DUMMY_RING
from interface import N_BITS
from mismatch import interleaved
from sar import branch_slices

COORDINATE_TOLERANCE = GDS_PRECISION / GDS_UNIT
DRC_ROOT = pathlib.Path("build/layout/checks")


class LayoutError(ValueError):
    """The supplied artifact violates an array requirement."""


def extract(path):
    """Extract a flat conductor graph without treating a capacitor as a short."""
    import klayout.db as db

    layout = db.Layout()
    layout.read(str(path))
    top = layout.cell(TOP)
    if top is None:
        raise LayoutError(f"missing top cell {TOP}")
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
        if net is None:
            raise LayoutError(f"no conductor at {name} ({x}, {y})")
        return net.cluster_id

    return extractor, probe


def upper_slots(library) -> set[int]:
    """Recover the labelled upper island from polygons rather than labels alone."""
    import gdspy

    top = library.cells[TOP]
    labels = [
        label
        for label in top.labels
        if label.text == UPPER_NET_LABEL
        and (label.layer, label.texttype) == sky130.MIM_GDS_UPPER_LABEL
    ]
    if len(labels) != 1:
        raise LayoutError("the upper net must have exactly one metal4 label")
    polygons = top.get_polygons(by_spec=True).get(sky130.MIM_GDS_UPPER, [])
    merged = gdspy.boolean(polygons, None, "or", max_points=0)
    if merged is None:
        raise LayoutError("missing upper metal")
    islands = [p for p in merged.polygons if gdspy.inside([labels[0].position], [p])[0]]
    if len(islands) != 1:
        raise LayoutError("the upper label is not on a unique metal island")
    slots = set()
    dummy_count = 0
    for ref in top.references:
        contacts = ref.get_polygons(by_spec=True).get(sky130.MIM_GDS_CONTACT, [])
        if len(contacts) != 1:
            raise LayoutError("each unit must retain its upper contact")
        plates = ref.get_polygons(by_spec=True).get(sky130.MIM_GDS_PLATE, [])
        if len(plates) != 1 or not all(gdspy.inside(contacts[0], plates)):
            raise LayoutError("an upper contact is outside its capacitor plate")
        centre = contacts[0].mean(axis=0)
        slot = ref.properties.get(SLOT_PROPERTY)
        dummy_count += slot is None
        if gdspy.inside([centre], islands)[0]:
            if slot is None:
                raise LayoutError("the upper net reaches an edge or filler dummy")
            slots.add(int(slot))
    if len(merged.polygons) != dummy_count + 1:
        raise LayoutError("unexpected isolated upper metal or connected dummy pads")
    return slots


def _check_geometry(library, units, n_bits):
    import gdspy

    count = 2**n_bits
    electrical = [u for u in units if u.slot is not None]
    if len(electrical) != count or {u.slot for u in electrical} != set(range(count)):
        raise LayoutError("electrical slots must occur exactly once at the required resolution")
    actual = [0] * count
    for physical, unit in enumerate(sorted(electrical, key=lambda u: (u.y, u.x))):
        actual[unit.slot] = physical
    if actual != interleaved(n_bits).tolist():
        raise LayoutError("physical ordering disagrees with the golden interleaving")
    owners = {count - 1: n_bits}
    for branch, slots in enumerate(branch_slices(n_bits)):
        owners.update(dict.fromkeys(range(slots.start, slots.stop), branch))
    if any(u.branch != owners[u.slot] for u in electrical):
        raise LayoutError("unit ownership disagrees with the golden branches")
    sites = {(u.column, u.row) for u in units}
    columns, rows = max(u.column for u in units) + 1, max(u.row for u in units) + 1
    if len(sites) != len(units) or len(sites) != columns * rows:
        raise LayoutError("the rectangular unit field has a missing or overlapping site")
    for unit in units:
        perimeter = (
            unit.column < DUMMY_RING
            or unit.column >= columns - DUMMY_RING
            or unit.row < DUMMY_RING
            or unit.row >= rows - DUMMY_RING
        )
        if perimeter and unit.slot is not None:
            raise LayoutError("an electrical unit occupies the dummy perimeter")
    side = sky130.mim_side()
    for ref in library.cells[TOP].references:
        (plate,) = ref.get_polygons(by_spec=True)[sky130.MIM_GDS_PLATE]
        extents = plate.max(axis=0) - plate.min(axis=0)
        if any(
            not math.isclose(float(v), side, rel_tol=0, abs_tol=COORDINATE_TOLERANCE)
            for v in extents
        ):
            raise LayoutError("a unit plate changed from the specified dimensions")
        if not math.isclose(
            gdspy.Polygon(plate).area(), side**2, rel_tol=0, abs_tol=side * COORDINATE_TOLERANCE
        ):
            raise LayoutError("a unit plate is not the specified rectangle")
    lower, upper = library.cells[TOP].get_bounding_box()
    width, height = template.analog_strip()
    if min(lower) < 0 or upper[0] > width or upper[1] > height:
        raise LayoutError("the supplied layout extends outside the analog strip")


def check_layout(path: pathlib.Path, n_bits: int = N_BITS) -> dict:
    """Check this saved file without constructing a replacement placement."""
    path = pathlib.Path(path)
    before = path.read_bytes()

    import gdspy

    if not isinstance(n_bits, int) or n_bits < 1:
        raise LayoutError("required resolution must be a positive integer")
    try:
        library = gdspy.GdsLibrary(infile=str(path))
        if TOP not in library.cells:
            raise LayoutError(f"missing top cell {TOP}")
        units = read_units(path)
        _check_geometry(library, units, n_bits)
        if upper_slots(library) != set(range(2**n_bits)):
            raise LayoutError("the upper net does not reach every electrical slot")
        extractor, probe = extract(path)
        labels = library.cells[TOP].labels
        nets = {}
        for branch in range(n_bits + 1):
            name = branch_label(branch, n_bits)
            matches = [
                label
                for label in labels
                if label.text == name and (label.layer, label.texttype) == sky130.METAL2_LABEL_GDS
            ]
            if len(matches) != 1:
                raise LayoutError(f"bottom terminal {name} must have exactly one metal2 label")
            nets[branch] = probe("m2", *matches[0].position)
        if len(set(nets.values())) != n_bits + 1:
            raise LayoutError("bottom branch outputs are shorted")
        members = {branch: set() for branch in nets}
        all_unit_nets = set()
        for unit in units:
            net = probe("m3", unit.x + sky130.mim_side() / 2, unit.y + sky130.mim_side() / 2)
            all_unit_nets.add(net)
            for branch, wanted in nets.items():
                if net == wanted:
                    if unit.slot is None:
                        raise LayoutError("a bottom branch reaches an edge or filler dummy")
                    members[branch].add(unit.slot)
        for branch, slots in enumerate(branch_slices(n_bits)):
            if members[branch] != set(range(slots.start, slots.stop)):
                raise LayoutError(
                    f"{branch_label(branch, n_bits)} has missing or wrong unit connections"
                )
        if members[n_bits] != {2**n_bits - 1}:
            raise LayoutError("bd must reach only the terminating electrical unit")
        dummy_count = sum(u.slot is None for u in units)
        if len(all_unit_nets) != n_bits + 1 + dummy_count:
            raise LayoutError("dummy bottom terminals must remain isolated")
        circuit = extractor.netlist().circuit_by_name(TOP)
        if circuit is None or {net.cluster_id for net in circuit.each_net()} != all_unit_nets:
            raise LayoutError("unexpected orphan conductor in the lower metal stack")
    except LayoutError:
        raise
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise LayoutError(str(error)) from error
    if path.read_bytes() != before:
        raise LayoutError("input changed during validation; validate a stable saved file")
    return {
        "input": str(path.resolve()),
        "sha256": hashlib.sha256(before).hexdigest(),
        "resolution": n_bits,
        "electrical_units": 2**n_bits,
        "dummy_units": sum(u.slot is None for u in units),
        "bottom_units": {branch_label(k, n_bits): len(v) for k, v in members.items()},
        "scope": "array geometry and conductor connectivity",
        "device_lvs": False,
        "parasitics": False,
        "drc": "not run",
    }


def main(argv: list[str] | None = None) -> int:
    """Validate the requested artifact and optionally DRC a private snapshot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=pathlib.Path)
    parser.add_argument("--report", type=pathlib.Path)
    parser.add_argument("--n-bits", type=int, default=N_BITS)
    parser.add_argument("--drc", action="store_true")
    parser.add_argument("--drc-root", type=pathlib.Path, default=DRC_ROOT)
    args = parser.parse_args(argv)
    try:
        if args.report and (
            args.report.resolve() == args.input.resolve()
            or (args.report.exists() and args.input.exists() and args.report.samefile(args.input))
        ):
            raise LayoutError("report must not overwrite the input layout")
        report = check_layout(args.input, args.n_bits)
        if args.drc:
            args.drc_root.mkdir(parents=True, exist_ok=True)
            run_dir = pathlib.Path(tempfile.mkdtemp(prefix="drc-", dir=args.drc_root)).resolve()
            snapshot = run_dir / f"{TOP}.gds"
            shutil.copyfile(args.input, snapshot)
            if hashlib.sha256(snapshot.read_bytes()).hexdigest() != report["sha256"]:
                raise LayoutError("input changed before the DRC snapshot was created")
            result = subprocess.run(
                ["sak-drc.sh", "-b", "-w", str(run_dir), str(snapshot)], check=False
            )
            if result.returncode:
                raise LayoutError(f"DRC failed; reports are in {run_dir}")
            report["drc_directory"] = str(run_dir)
            report["drc"] = "Magic and KLayout clean"
        if hashlib.sha256(args.input.read_bytes()).hexdigest() != report["sha256"]:
            raise LayoutError("input changed during validation")
        content = json.dumps(report, indent=2) + "\n"
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(content)
        print(content, end="")
        return 0
    except (ValueError, OSError, ImportError, RuntimeError) as error:
        print(f"layout validation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
