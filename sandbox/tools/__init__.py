"""Shared helpers for the sandbox experiments.

Nothing outside `sandbox/` imports this. What lives here carries no circuit in
it, so each experiment holds only its own stimulus and its own measurements.
Running a deck is not here: the design's own simulations need it too, and
design code may not import from the sandbox, so it lives with them.
"""

from tools import netlist, sky130

__all__ = ["netlist", "sky130"]
