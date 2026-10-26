"""What a verification run spent its time on, as markdown.

Reads the reports the verify targets write and prints a table per level and the
tests that cost the most. Run with no arguments it reads every report it finds.

Contract: a run this long is read by someone who was not watching it, so this
prints what a log cannot -- a per-test duration -- and prints nothing at all
when there is no report, rather than failing a job whose tests have already
spoken.
"""

from __future__ import annotations

import pathlib
import sys
import xml.etree.ElementTree as ET

#: Where the verify targets leave their reports.
REPORTS = pathlib.Path("build/verify")

#: How many of the slowest tests to name. Enough to see which handful of tests
#: a level is, and short enough to read beside the table.
SLOWEST = 15

#: Columns that only earn their place when they are not zero.
OUTCOMES = ("failures", "errors", "skipped")


def levels(paths: list[pathlib.Path]) -> list[tuple[str, dict[str, int], float]]:
    """Each report's level name, its outcome counts and its duration."""
    found = []
    for path in paths:
        suite = ET.parse(path).getroot().find("testsuite")
        if suite is None:
            continue
        counts = {name: int(suite.get(name, 0)) for name in ("tests", *OUTCOMES)}
        found.append((path.stem, counts, float(suite.get("time", 0.0))))
    return sorted(found, key=lambda level: -level[2])


def tests(paths: list[pathlib.Path]) -> list[tuple[float, str, str]]:
    """Every test's duration, slowest first, with the level it ran in."""
    found = [
        (float(case.get("time", 0.0)), case.get("classname", "").split(".")[-1], case.get("name"))
        for path in paths
        for case in ET.parse(path).iter("testcase")
    ]
    return sorted(found, reverse=True)


def clock(seconds: float) -> str:
    return f"{int(seconds) // 60}m {int(seconds) % 60:02d}s"


def markdown(paths: list[pathlib.Path]) -> str:
    out = ["| level | tests | time |", "|---|---:|---:|"]
    for name, counts, seconds in levels(paths):
        state = ", ".join(f"{counts[k]} {k}" for k in OUTCOMES if counts[k])
        out.append(
            f"| {name}{' (' + state + ')' if state else ''} "
            f"| {counts['tests']} | {clock(seconds)} |"
        )
    out += ["", f"<details><summary>The {SLOWEST} slowest tests</summary>", ""]
    out += ["| test | level | time |", "|---|---|---:|"]
    out += [
        f"| `{name}` | {where} | {clock(seconds)} |"
        for seconds, where, name in tests(paths)[:SLOWEST]
    ]
    out += ["", "</details>"]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    paths = [pathlib.Path(a) for a in argv] or sorted(REPORTS.glob("*.xml"))
    paths = [p for p in paths if p.is_file()]
    if not paths:
        return 0
    print(markdown(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
