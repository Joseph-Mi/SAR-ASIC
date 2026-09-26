"""Shared helpers for the sandbox experiments.

Nothing outside `sandbox/` imports this. What lives here carries no circuit in
it, so each experiment holds only its own stimulus and its own measurements.
Running a deck and the PDK's device parameters are not here: the design's
own simulations need them too, and design code may not import from the
sandbox, so they live with them.
"""

from tools import netlist

__all__ = ["netlist"]
