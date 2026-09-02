"""Running an ngspice deck and reading the numbers back out.

Contract: a deck handed to `run` prints its results through `meas` or `print`,
and the caller owns a writable working directory for the scratch file.

Selecting the model library costs far more than any analysis and is paid per
process, so a sweep belongs in one deck and a Monte Carlo in a loop around
`reset`.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess

#: ngspice opens every result with "name = value" at a line start. The name is
#: captured whole so one measurement is not read as another whose name it ends;
#: the line is not end-anchored because min and max trail their sweep position.
RESULT = re.compile(r"^\s*(\w+)\s*=\s*([-+\d.eE]+)", re.M)

LIBRARY = re.compile(r"^\.lib\s+(\S*sky130\.lib\.spice)\s+\w+\s*$", re.M)


class DeckError(RuntimeError):
    """A deck that produced nothing a caller can use."""


def library(netlist: str) -> str:
    """The model library path a netlist selects, without its corner."""
    found = LIBRARY.search(netlist)
    if not found:
        raise DeckError("netlist selects no sky130 model library")
    return found.group(1)


def subckt(netlist: str, name: str) -> str:
    """One subcircuit definition, whole, including its terminating line."""
    found = re.search(rf"^\.subckt\s+{re.escape(name)}\b.*?^\.ends\s*$", netlist, re.M | re.S)
    if not found:
        raise DeckError(f"netlist defines no subcircuit named {name}")
    return found.group(0)


def run(deck: str, workdir: pathlib.Path) -> dict[str, list[float]]:
    """Simulate one deck, returning every result it printed, in order.

    Results accumulate under their own names, so a loop that measures the same
    quantity each pass returns one list of draws per name.

    ngspice exits zero whether or not a deck produced anything, so an empty
    result is the failure signal. The scratch deck is named for the process
    holding it: two runs sharing one name would simulate each other's circuit.
    """
    scratch = workdir / f"_run{os.getpid()}.spice"
    scratch.write_text(deck)
    try:
        proc = subprocess.run(
            ["ngspice", "-b", scratch.name],
            cwd=workdir,
            capture_output=True,
            text=True,
        )
    finally:
        scratch.unlink(missing_ok=True)

    results: dict[str, list[float]] = {}
    for name, value in RESULT.findall(proc.stdout):
        results.setdefault(name, []).append(float(value))
    if not results:
        raise DeckError(f"deck produced no measurements\n{proc.stdout}\n{proc.stderr}")
    return results
