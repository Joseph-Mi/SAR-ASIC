#!/usr/bin/env python
"""Lint every module in hdl/rtl/ with Verilator.

Each file is linted standalone as its own top, so a module that is never
instantiated still gets checked. Waivers live in hdl/lint/waivers.vlt.

Usage:  python scripts/lint_rtl.py [path ...]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RTL_DIR = REPO_ROOT / "hdl" / "rtl"
WAIVERS = REPO_ROOT / "hdl" / "lint" / "waivers.vlt"


def main(argv: list[str]) -> int:
    targets = [Path(a).resolve() for a in argv[1:]] or sorted(RTL_DIR.rglob("*.v"))
    if not targets:
        print(f"no .v files under {RTL_DIR} -- nothing to lint")
        return 0

    include_dirs = sorted({p.parent for p in RTL_DIR.rglob("*.v")})
    failures = []

    for src in targets:
        cmd = [
            "verilator", "--lint-only", "-Wall",
            "--timescale", "1ns/1ps",
            "--top-module", src.stem,
            *[f"-I{d}" for d in include_dirs],
            str(WAIVERS),
            str(src),
        ]
        print(f"lint {src.relative_to(REPO_ROOT)}")
        if subprocess.run(cmd, cwd=REPO_ROOT).returncode != 0:
            failures.append(src)

    if failures:
        print(f"\n{len(failures)} file(s) failed lint:")
        for f in failures:
            print(f"  {f.relative_to(REPO_ROOT)}")
        return 1

    print(f"\nclean: {len(targets)} file(s)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except FileNotFoundError:
        sys.exit("verilator not found on PATH -- see README.md")
