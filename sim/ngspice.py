"""Running an ngspice deck and reading the numbers back out.

Contract: a deck handed to `run` prints its results through `meas` or `print`,
and the caller owns a writable working directory for the scratch file.
"""

from __future__ import annotations

import logging
import os
import pathlib
import re
import subprocess
import threading
import time

#: Names are captured whole so one result is not read as another whose name it
#: ends; not end-anchored because min and max trail their sweep position.
RESULT = re.compile(r"^\s*(\w+)\s*=\s*([-+\d.eE]+)", re.M)

#: Conversions per simulation. Each conversion is fine alone and in batches of
#: tens; a single run of thousands of switch edges over tens of microseconds
#: eventually wedges the solver's timestep control ("timestep too small") on
#: some edge that is harmless in a shorter run.
BATCH = 32

LIBRARY = re.compile(r"^\.lib\s+(\S*sky130\.lib\.spice)\s+\w+\s*$", re.M)

#: Solver relative tolerance. The default, a part in a thousand, is looser
#: than anything this design asks a simulator: a node left floating has to
#: conserve its charge far more tightly than the answer it is compared
#: against, and a decision taken near a point where the circuit is balanced
#: resolves at whatever asymmetry the solver carries. A decade tighter covers
#: both at no cost in run time. Tighter again stalls on hard edges without
#: buying anything a test can see.
RELTOL = 1e-4

#: One record either side of every simulation, so that a suite whose tests are
#: minutes of silence each says which circuit it is inside. A deck that wedges
#: the solver never returns, and the record of it starting is the only thing
#: that tells that apart from a deck still working.
log = logging.getLogger(__name__)

#: Seconds one deck may run before it is called a stall rather than a
#: simulation. A wedged timestep does not finish at all, so this only has to
#: sit above the longest deck any test asks for -- a batch of conversions
#: through transistor switches at the slowest corner -- and below the patience
#: of whatever is waiting on the suite.
TIMEOUT = 1200.0

#: Raising the bound for an exploratory deck, without editing it.
TIMEOUT_ENV = "SAR_NGSPICE_TIMEOUT"


class DeckError(RuntimeError):
    """A deck that produced nothing a caller can use."""


def title(deck: str) -> str:
    """A deck's own first line, which ngspice reads as its title.

    What the heartbeat names a simulation by. Every deck this repository
    generates opens with one.
    """
    return deck.partition("\n")[0].lstrip("*").strip()


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


def results(stdout: str) -> dict[str, list[float]]:
    """Every `name = value` a run printed, in order, grouped by name.

    Results accumulate under their own names, so a loop that measures the same
    quantity each pass returns one list of draws per name.
    """
    found: dict[str, list[float]] = {}
    for name, value in RESULT.findall(stdout):
        found.setdefault(name, []).append(float(value))
    return found


def run(deck: str, workdir: pathlib.Path) -> dict[str, list[float]]:
    """Simulate one deck, returning every result it printed.

    ngspice exits zero whether or not a deck produced anything, so an empty
    result is the failure signal. The scratch deck is named for the caller
    holding it -- the process and the thread within it, because a pool of
    threads shares one process id and two of them sharing one deck name would
    simulate each other's circuit.
    """
    scratch = workdir / f"_run{os.getpid()}_{threading.get_ident()}.spice"
    scratch.write_text(deck)
    limit = float(os.environ.get(TIMEOUT_ENV, TIMEOUT))
    log.info("start: %s (%d lines)", title(deck), deck.count("\n"))
    started = time.monotonic()
    try:
        proc = subprocess.run(
            ["ngspice", "-b", scratch.name],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=limit,
        )
    except subprocess.TimeoutExpired as expired:
        # The deck is left where it was written: a stall is reproducible only
        # from the exact text that caused it, and this is the one failure mode
        # whose cause is the input rather than the answer.
        raise DeckError(
            f"{title(deck)}: no answer in {limit:g} s, which is a stalled solver "
            f"rather than a slow one; the deck is at {scratch}"
        ) from expired
    else:
        scratch.unlink(missing_ok=True)

    found = results(proc.stdout)
    log.info(
        "done: %s in %.1f s, %d measurements",
        title(deck),
        time.monotonic() - started,
        len(found),
    )
    if not found:
        raise DeckError(f"deck produced no measurements\n{proc.stdout}\n{proc.stderr}")
    return found
