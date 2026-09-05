"""Running an ngspice deck and reading the numbers back out.

Contract: a deck handed to `run` prints its results through `meas` or `print`,
and the caller owns a writable working directory for the scratch file.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess

#: Names are captured whole so one result is not read as another whose name it
#: ends; not end-anchored because min and max trail their sweep position.
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


def ports(subckt: str) -> list[str]:
    """The terminal names of a subcircuit, in the order it declares them.

    An extracted subcircuit rarely lists its terminals in the order the
    schematic did. Wiring one up by position silently miswires it, so callers
    map by name and take the order from here.
    """
    return re.match(r"^\.subckt\s+\S+\s+(.*)$", subckt, re.M).group(1).split()


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
