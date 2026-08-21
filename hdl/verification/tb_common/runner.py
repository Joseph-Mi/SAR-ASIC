"""Thin wrapper over cocotb's Python runner. Verilator only.

We use the runner (not cocotb Makefiles) so the suite runs under plain pytest
and needs no `make`. Every testbench file holds both its `@cocotb.test()`
coroutines and a `def test_*()` pytest entry point that calls `run()` below.
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path

from cocotb_tools.runner import VerilatorControlFile, get_runner

SIM = "verilator"

REPO_ROOT = Path(__file__).resolve().parents[3]
RTL_DIR = REPO_ROOT / "hdl" / "rtl"
BUILD_DIR = REPO_ROOT / "build" / "sim"

#: Waveforms cost runtime; off by default, on with `WAVES=1`.
DEFAULT_WAVES = os.getenv("WAVES", "0") not in ("0", "", "false", "False")

#: Applies to every build; matches the timescale `make lint-rtl` uses.
TIMESCALE = ("1ns", "1ps")

#: Verilator is strict about unused/undriven signals. Keep it that way, but let
#: waivers live in one reviewable file instead of inline pragmas.
WAIVERS = REPO_ROOT / "hdl" / "lint" / "waivers.vlt"


def rtl(*names: str) -> list[Path]:
    """`rtl("sar_fsm", "sar_dac_ctrl")` -> the matching paths in hdl/rtl/.

    Searches recursively so submodules may live in hdl/rtl/<block>/. RTL is
    Verilog-2005, so only .v is considered.
    """
    out: list[Path] = []
    for name in names:
        stem = name[:-2] if name.endswith(".v") else name
        matches = sorted(RTL_DIR.rglob(f"{stem}.v"))
        if not matches:
            raise FileNotFoundError(f"no {stem}.v under {RTL_DIR}")
        if len(matches) > 1:
            raise ValueError(f"{stem}.v is ambiguous: {matches}")
        out.append(matches[0])
    return out


def run(
    top: str,
    *,
    sources: list[Path] | None = None,
    test_module: str | None = None,
    test_dir: Path | None = None,
    testcase: str | list[str] | None = None,
    parameters: dict[str, object] | None = None,
    includes: list[Path] | None = None,
    defines: dict[str, object] | None = None,
    build_args: list[str] | None = None,
    test_args: list[str] | None = None,
    plusargs: list[str] | None = None,
    waves: bool | None = None,
    seed: int | None = None,
) -> None:
    """Build `top` with Verilator and run the cocotb tests in the calling module.

    Defaults are conventions, not magic: `sources` defaults to `hdl/rtl/<top>.v`
    and `test_module`/`test_dir` default to the file that called this.
    """
    caller_path = Path(inspect.stack()[1].filename).resolve()

    waves = DEFAULT_WAVES if waves is None else waves
    sources = sources if sources is not None else rtl(top)
    test_module = test_module or caller_path.stem
    test_dir = test_dir or caller_path.parent

    build_dir = BUILD_DIR / top
    build_dir.mkdir(parents=True, exist_ok=True)

    build_sources: list[object] = [str(p) for p in sources]
    if WAIVERS.is_file():
        build_sources.append(VerilatorControlFile(WAIVERS))

    runner = get_runner(SIM)
    runner.build(
        sources=build_sources,
        hdl_toplevel=top,
        includes=[str(p) for p in (includes or [])],
        defines=defines or {},
        parameters=parameters or {},
        build_dir=str(build_dir),
        build_args=["-Wall", *(build_args or [])],
        timescale=TIMESCALE,
        waves=waves,
        always=True,
    )

    runner.test(
        hdl_toplevel=top,
        test_module=test_module,
        test_dir=str(test_dir),
        testcase=testcase,
        build_dir=str(build_dir),
        test_args=list(test_args or []),
        plusargs=list(plusargs or []),
        results_xml=str(build_dir / "results.xml"),
        timescale=TIMESCALE,
        seed=seed,
        waves=waves,
    )
