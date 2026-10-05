"""What the TinyTapeout platform gives an analog project at its pins.

Contract: facts of the platform, from its analog specification, that more than
one layer needs. Nothing here depends on anything else in the repository.
Each is the specification's bound, not a typical value: a design that works
at the bound works on every chip the platform promises.
"""

from __future__ import annotations

#: Series resistance between an analog pad and the project's pin, ohms: the
#: analog switch, the bond wire and the trace. The specification gives an
#: upper bound.
R_PIN = 500.0
