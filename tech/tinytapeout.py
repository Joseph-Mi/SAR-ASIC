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

#: Capacitance an analog pin presents, farads. It sits at the pad, outside the
#: series resistance, so it loads whatever drives the pin rather than adding to
#: what the pin charges through that resistance.
C_PIN = 5e-12

#: Current a pin may carry, amps. Applies to the analog pins and to a digital
#: pin's drive alike.
I_PIN = 4e-3

#: Supply current, amps, that drops the on-chip supply by V_PDN_DROP volts
#: through the power network. A budget for everything the project switches at
#: once, not a limit on any one device.
I_PDN_DROP = 20e-3
V_PDN_DROP = 0.1
