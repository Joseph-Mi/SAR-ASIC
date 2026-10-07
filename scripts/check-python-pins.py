#!/usr/bin/env python3
"""Fail unless the installed Python packages are the versions requirements.txt pins.

requirements.txt is the only place those versions live, so this reads them from
it rather than keeping a copy. A package pinned and missing, or installed at
another version, is named here -- instead of surfacing later as a command not
found in the middle of an unrelated target.
"""

from __future__ import annotations

import importlib.metadata as metadata
import pathlib
import re
import sys

#: A pinned requirement. Only exact pins are checked: a range is not a claim
#: about what is installed, so there is nothing to disagree with.
PIN = re.compile(r"^(?P<name>[A-Za-z0-9._-]+)==(?P<version>[^\s;#]+)")

REQUIREMENTS = pathlib.Path(__file__).resolve().parent.parent / "requirements.txt"


def pins(text: str) -> dict[str, str]:
    """Every exactly pinned package, by name."""
    found = {}
    for line in text.splitlines():
        match = PIN.match(line.strip())
        if match:
            found[match["name"]] = match["version"]
    return found


def main() -> int:
    wanted = pins(REQUIREMENTS.read_text())
    if not wanted:
        print(f"{REQUIREMENTS.name} pins nothing to check", file=sys.stderr)
        return 1

    wrong = []
    for name, version in sorted(wanted.items()):
        try:
            got = metadata.version(name)
        except metadata.PackageNotFoundError:
            wrong.append(f"{name}: want {version}, not installed")
        else:
            if got != version:
                wrong.append(f"{name}: want {version}, got {got}")

    if wrong:
        print("\n".join(wrong), file=sys.stderr)
        print("the container runs these from a layer: make image, then", file=sys.stderr)
        print("remove the old container so make recreates it from the new one", file=sys.stderr)
        return 1

    print(f"python packages match requirements.txt ({len(wanted)} pins)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
