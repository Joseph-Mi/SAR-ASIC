"""Stream a MiM array with a common upper plate and recover its placement.

Contract: electrical units share the upper net; edge and filler dummies stay
isolated. Reference properties carry slot identity, not extracted connectivity.
"""

from __future__ import annotations

import argparse
import math
import pathlib

import sky130
from array_place import Placement, Unit, placement

TOP = "sar_array"
DUMMY = "dummy"
BRANCH_PREFIX = "branch_"
SLOT_PROPERTY = 1
UPPER_NET_LABEL = "TOP_PLATE"
GDS_UNIT = 1e-6
GDS_PRECISION = 1e-9
OUT = pathlib.Path("build/layout/sar_array.gds")


def upper_pad_side() -> float:
    """A square landing pad satisfying minimum upper-metal area on the grid."""
    return math.ceil(math.sqrt(sky130.METAL4_MIN_AREA) / sky130.LAYOUT_GRID) * sky130.LAYOUT_GRID


def _route_upper(top, drawn: Placement) -> None:
    """Join electrical rows with a spine in the gap beside the dummy column."""
    import gdspy

    rows = {}
    for unit in drawn.units:
        if unit.slot is not None:
            rows.setdefault(unit.row, []).append(unit)
    half = upper_pad_side() / 2
    centre = drawn.side / 2
    first_x = min(u.x for units in rows.values() for u in units)
    spine_x = first_x + centre - sky130.mim_pitch(drawn.side) / 2
    row_ys = []
    for units in rows.values():
        y = units[0].y + centre
        row_ys.append(y)
        right = max(u.x for u in units) + centre
        top.add(
            gdspy.Rectangle(
                (spine_x - half, y - half),
                (right + half, y + half),
                layer=sky130.MIM_GDS_UPPER[0],
                datatype=sky130.MIM_GDS_UPPER[1],
            )
        )
    top.add(
        gdspy.Rectangle(
            (spine_x - half, min(row_ys) - half),
            (spine_x + half, max(row_ys) + half),
            layer=sky130.MIM_GDS_UPPER[0],
            datatype=sky130.MIM_GDS_UPPER[1],
        )
    )
    top.add(
        gdspy.Label(
            UPPER_NET_LABEL,
            (spine_x, min(row_ys)),
            layer=sky130.MIM_GDS_UPPER_LABEL[0],
            texttype=sky130.MIM_GDS_UPPER_LABEL[1],
        )
    )


def write_gds(drawn: Placement, path: pathlib.Path) -> None:
    """Write a contacted upper plate above each isolated shielding bottom plate."""
    import gdspy

    library = gdspy.GdsLibrary(unit=GDS_UNIT, precision=GDS_PRECISION)
    top = gdspy.Cell(TOP, exclude_from_current=True)
    library.add(top)
    for branch in [None, *range(drawn.n_bits + 1)]:
        name = DUMMY if branch is None else f"{BRANCH_PREFIX}{branch}"
        cell = gdspy.Cell(name, exclude_from_current=True)
        library.add(cell)
        enclosure = sky130.MIM_PLATE_ENCLOSURE
        cell.add(
            gdspy.Rectangle(
                (0, 0),
                (drawn.side, drawn.side),
                layer=sky130.MIM_GDS_PLATE[0],
                datatype=sky130.MIM_GDS_PLATE[1],
            )
        )
        cell.add(
            gdspy.Rectangle(
                (-enclosure, -enclosure),
                (drawn.side + enclosure, drawn.side + enclosure),
                layer=sky130.MIM_GDS_BOTTOM[0],
                datatype=sky130.MIM_GDS_BOTTOM[1],
            )
        )
        centre = drawn.side / 2
        pad_side = upper_pad_side()
        for spec, half in (
            (sky130.MIM_GDS_CONTACT, sky130.MIM_CONTACT_SIDE / 2),
            (sky130.MIM_GDS_UPPER, pad_side / 2),
        ):
            cell.add(
                gdspy.Rectangle(
                    (centre - half, centre - half),
                    (centre + half, centre + half),
                    layer=spec[0],
                    datatype=spec[1],
                )
            )
    for unit in drawn.units:
        name = DUMMY if unit.branch is None else f"{BRANCH_PREFIX}{unit.branch}"
        ref = gdspy.CellReference(library.cells[name], origin=(unit.x, unit.y))
        if unit.slot is not None:
            ref.properties[SLOT_PROPERTY] = str(unit.slot)
        top.add(ref)
    _route_upper(top, drawn)
    path.parent.mkdir(parents=True, exist_ok=True)
    library.write_gds(str(path))


def read_units(path: pathlib.Path) -> tuple[Unit, ...]:
    """Recover row-major coordinates and branch ownership without a sidecar."""
    import gdspy

    library = gdspy.GdsLibrary(infile=str(path))
    top = library.cells[TOP]
    plates = []
    for ref in top.references:
        polygons = ref.get_polygons(by_spec=True).get(sky130.MIM_GDS_PLATE, [])
        if len(polygons) != 1:
            raise ValueError("each reference must contain exactly one capacitor plate")
        lower = polygons[0].min(axis=0)
        plates.append((ref, float(lower[0]), float(lower[1])))
    xs = sorted({x for _, x, _ in plates})
    ys = sorted({y for _, _, y in plates})
    units = []
    for ref, x, y in plates:
        name = ref.ref_cell.name
        slot = ref.properties.get(SLOT_PROPERTY)
        branch = None if name == DUMMY else int(name.removeprefix(BRANCH_PREFIX))
        if (slot is None) != (branch is None):
            raise ValueError("a reference's slot and branch disagree")
        units.append(
            Unit(
                x,
                y,
                xs.index(x),
                ys.index(y),
                None if slot is None else int(slot),
                branch,
            )
        )
    return tuple(units)


def main() -> None:
    """Generate the declared array and print the extent that DRC will inspect."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=pathlib.Path, default=OUT)
    args = parser.parse_args()
    drawn = placement()
    write_gds(drawn, args.out)
    print(
        f"{args.out}: {drawn.columns} columns x {drawn.rows} rows; "
        f"{sum(u.slot is not None for u in drawn.units)} electrical units"
    )


if __name__ == "__main__":
    main()
