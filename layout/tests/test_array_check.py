"""Saved-layout validation checked against edits to the actual input artifact.

Contract: validation never regenerates or modifies its input, including when
an edited artifact fails the electrical or geometric contract.
"""

from __future__ import annotations

import hashlib
import json
import os
from types import SimpleNamespace

import pytest

import sky130
from array_check import LayoutError, check_layout, main
from array_gds import SLOT_PROPERTY, TOP, write_gds
from array_place import placement
from interface import N_BITS

SMALL_BITS = 4


@pytest.fixture
def saved(tmp_path):
    pytest.importorskip("gdspy")
    pytest.importorskip("klayout.db")
    path = tmp_path / "saved edits.gds"
    write_gds(placement(SMALL_BITS), path)
    return path


def test_saved_layout_is_checked_without_regenerating_or_writing(saved, monkeypatch):
    import array_gds

    before = saved.read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError("validation must not generate layout")

    monkeypatch.setattr(array_gds, "write_gds", forbidden)
    report = check_layout(saved, SMALL_BITS)
    assert saved.read_bytes() == before
    assert report["sha256"] == hashlib.sha256(before).hexdigest()
    assert report["electrical_units"] == 2**SMALL_BITS
    assert report["bottom_units"] == {f"b{k}": 2**k for k in range(SMALL_BITS)} | {"bd": 1}
    assert report["device_lvs"] is False
    assert report["parasitics"] is False
    assert report["drc"] == "not run"


@pytest.mark.parametrize("edit", ["via", "label", "slot", "size", "orphan"])
def test_edits_to_the_saved_artifact_are_detected_and_preserved(saved, edit):
    import gdspy

    library = gdspy.GdsLibrary(infile=str(saved))
    cell = library.cells["branch_0"]
    if edit == "via":
        cell.polygons = [
            p for p in cell.polygons if (p.layers[0], p.datatypes[0]) != sky130.VIA2_GDS
        ]
    elif edit == "label":
        library.cells[TOP].labels = [
            label for label in library.cells[TOP].labels if label.text != "b0"
        ]
    elif edit == "slot":
        library.cells[TOP].references[0].properties[SLOT_PROPERTY] = "0"
    elif edit == "size":
        for polygon in cell.polygons:
            if (polygon.layers[0], polygon.datatypes[0]) == sky130.MIM_GDS_PLATE:
                polygon.scale(0.5)
    else:
        library.cells[TOP].add(
            gdspy.Rectangle(
                (0, 0), (1, 1), layer=sky130.METAL1_GDS[0], datatype=sky130.METAL1_GDS[1]
            )
        )
    library.write_gds(str(saved))
    edited = saved.read_bytes()
    with pytest.raises(LayoutError):
        check_layout(saved, SMALL_BITS)
    assert saved.read_bytes() == edited


def test_moving_an_output_label_along_its_net_is_allowed(saved):
    import gdspy

    library = gdspy.GdsLibrary(infile=str(saved))
    label = next(label for label in library.cells[TOP].labels if label.text == "b0")
    label.position[1] += sky130.LAYOUT_GRID
    library.write_gds(str(saved))
    assert check_layout(saved, SMALL_BITS)["bottom_units"]["b0"] == 1


def test_input_resolution_is_a_requirement_not_inferred_from_missing_units(saved):
    with pytest.raises(LayoutError):
        check_layout(saved, N_BITS)


def test_missing_input_is_not_synthesized(tmp_path):
    path = tmp_path / "missing.gds"
    with pytest.raises(FileNotFoundError):
        check_layout(path)
    assert not path.exists()


def test_cli_writes_a_report_for_the_saved_file(saved, tmp_path):
    report = tmp_path / "report.json"
    before = saved.read_bytes()
    assert main([str(saved), "--n-bits", str(SMALL_BITS), "--report", str(report)]) == 0
    assert json.loads(report.read_text())["sha256"] == hashlib.sha256(before).hexdigest()
    assert saved.read_bytes() == before


@pytest.mark.parametrize("alias", ["same", "hardlink", "symlink"])
def test_report_cannot_overwrite_the_input_through_an_alias(saved, tmp_path, alias):
    report = saved if alias == "same" else tmp_path / "alias.json"
    if alias == "hardlink":
        os.link(saved, report)
    elif alias == "symlink":
        report.symlink_to(saved)
    before = saved.read_bytes()
    assert main([str(saved), "--n-bits", str(SMALL_BITS), "--report", str(report)]) == 1
    assert saved.read_bytes() == before


def test_drc_receives_a_private_snapshot_with_the_real_top_name(saved, tmp_path, monkeypatch):
    import array_check

    before = saved.read_bytes()
    calls = []

    def run(command, **kwargs):
        snapshot = type(saved)(command[-1])
        assert snapshot.resolve() != saved.resolve()
        assert snapshot.name == f"{TOP}.gds"
        assert snapshot.read_bytes() == before
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(array_check.subprocess, "run", run)
    report = tmp_path / "report.json"
    assert (
        main(
            [
                str(saved),
                "--n-bits",
                str(SMALL_BITS),
                "--drc",
                "--drc-root",
                str(tmp_path / "checks"),
                "--report",
                str(report),
            ]
        )
        == 0
    )
    assert len(calls) == 1
    assert json.loads(report.read_text())["drc"] == "Magic and KLayout clean"
    assert saved.read_bytes() == before


def test_a_drc_failure_is_a_validation_failure(saved, tmp_path, monkeypatch):
    import array_check

    before = saved.read_bytes()
    monkeypatch.setattr(
        array_check.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1)
    )
    assert (
        main(
            [
                str(saved),
                "--n-bits",
                str(SMALL_BITS),
                "--drc",
                "--drc-root",
                str(tmp_path / "checks"),
            ]
        )
        == 1
    )
    assert saved.read_bytes() == before
