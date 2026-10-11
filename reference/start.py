"""What asks for a conversion, and when the search is allowed to hear it.

The part runs in one of two modes, chosen by a pin so it can be moved between
them with a jumper and no firmware: convert continuously, or convert once each
time it is asked.

Contract: `asking` says whether the search is being asked to begin on the cycle
it is called in, and `cycle` is the clock edge that ends that cycle -- the pin's
level during it, whether the search was idle, and whether the search took a step
on it. The levels are the synchronised ones: levels the clock has already
captured, not the asynchronous wires.

Continuous mode reads no pin at all. The platform leaves an unconnected input
low, so a part with nothing wired to it is in this mode with its request pin
low, and that has to be a part that converts: anything else reads as a dead chip
on a bench. Giving the pin a second meaning here -- run while high -- is what
would make the default a part that sits still.

A request has to outlive the wait to be heard. The search hears one only on a
step of the conversion clock, and at the slowest rate that clock can be asked
for those are two hundred and fifty six cycles apart, so a request that lived
only as long as the edge that made it would be missed on all but one of them. It
has to outlive a conversion in flight too, for the same reason a capture
request does: an ask arriving mid-conversion is an ask, not a mistake.

A press and the request being served can land on the same cycle. The press wins
-- a request already being served is one conversion, and dropping the new one
loses a press that was really made.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Convert back to back for as long as the part is powered.
CONTINUOUS = "continuous"

#: Convert once per rising edge of the request pin.
SINGLE_SHOT = "single_shot"

MODES = (CONTINUOUS, SINGLE_SHOT)

#: The request pin's level before anything has sampled it. High, so a pin
#: already high when the part comes out of reset is not read as an edge: there
#: was no edge, and a conversion nobody asked for is not what single-shot
#: means.
INITIAL_LEVEL = True


@dataclass
class Start:
    """The request behind a conversion."""

    #: Read from a pin every cycle, so it may move at any time. Moving it does
    #: not disturb a conversion already running: nothing here can stop one.
    mode: str = CONTINUOUS

    #: A conversion asked for and not yet begun.
    pending: bool = False

    _level: bool = INITIAL_LEVEL

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"{self.mode} is not one of {MODES}")

    def asking(self, ready: bool) -> bool:
        """Whether the search is being asked to begin, this cycle."""
        if not ready:
            return False
        return True if self.mode == CONTINUOUS else self.pending

    def cycle(self, level: bool, ready: bool, stepping: bool) -> None:
        """The clock edge ending a cycle the pin was at `level` for."""
        if self.mode not in MODES:
            raise ValueError(f"{self.mode} is not one of {MODES}")
        asked = self.mode == SINGLE_SHOT and bool(level) and not self._level
        if stepping and self.asking(ready):
            self.pending = False
        if asked:
            self.pending = True
        self._level = bool(level)
