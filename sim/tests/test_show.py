"""The drawing runs: a small closed loop produces its figure and its raw file,
and the codes it reports are the model's."""

from __future__ import annotations

import shutil

import pytest

import cosim
import show
from sar import ideal_units, sar_convert

pytestmark = pytest.mark.skipif(
    shutil.which("ngspice") is None or not cosim.available(),
    reason="needs ngspice, verilator and the element glue ngspice installs",
)

#: A resolution small enough to draw in seconds.
SMALL = 4

#: One input off every threshold at that resolution.
VIN = 0.3


def test_the_loop_is_drawn_and_its_waveforms_kept(tmp_path, capsys):
    figure, raw = show.show([VIN], SMALL, designed=False, out=tmp_path / "loop.png")
    assert figure.stat().st_size and raw.stat().st_size
    want = sar_convert(VIN, ideal_units(SMALL), 1.0)[0]
    assert f"-> code {want} " in capsys.readouterr().out
