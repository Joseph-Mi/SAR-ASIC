"""What the result pins show, conversion by conversion.

The converter produces a code whenever it finishes; the pins do not have to
follow every one. This says which results reach the pins and when the flag that
marks a change goes up, so a reader that waits for the flag always finds pins
that just changed -- whichever mode the part is in.

Contract: `pin` is called with the hold pin's level once per cycle it could
have changed, and `finished` once per conversion that ended, in the order the
two happen. The pin's level is the synchronised one: a level the clock has
already captured, not the asynchronous wire.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The pin freezes the result while it is high; the converter keeps running.
LEVEL_HOLD = "level_hold"

#: The pin's rising edge asks for one result. Until one is asked for, the pins
#: hold what they have.
EDGE_CAPTURE = "edge_capture"

MODES = (LEVEL_HOLD, EDGE_CAPTURE)

#: What the pins read before any conversion has reached them.
INITIAL_CODE = 0

#: The pin's level before anything has sampled it. High, so a pin already high
#: when the part comes out of reset is not read as an edge: there was no edge,
#: and a request nobody made captures a result nobody asked for.
INITIAL_LEVEL = True


@dataclass
class Readout:
    """The holding register behind the result pins, and its flag."""

    mode: str = LEVEL_HOLD
    code: int = INITIAL_CODE
    done: bool = False
    #: A capture asked for and not yet served. A request has to outlive the
    #: edge that made it: the edge almost never lands on the cycle a
    #: conversion ends, and a request dropped between the two is a press that
    #: did nothing.
    pending: bool = False
    _level: bool = INITIAL_LEVEL

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"{self.mode} is not one of {MODES}")

    def pin(self, level: bool) -> None:
        """The hold pin, as the clock sees it."""
        if self.mode == EDGE_CAPTURE and level and not self._level:
            self.pending = True
        self._level = bool(level)

    @property
    def updating(self) -> bool:
        """Whether a conversion ending now would reach the pins."""
        return self.pending if self.mode == EDGE_CAPTURE else not self._level

    def finished(self, code: int) -> None:
        """A conversion ended with `code`."""
        self.done = self.updating
        if self.done:
            self.code = code
            self.pending = False

    def idle(self) -> None:
        """A cycle in which no conversion ended."""
        self.done = False
