"""What the TinyTapeout platform gives an analog project at its pins.

Contract: facts of the platform, from its analog specification, that more than
one layer needs. Nothing here depends on anything else in the repository.
Each is the specification's bound, not a typical value: a design that works
at the bound works on every chip the platform promises.
"""

from __future__ import annotations

#: The supplies the platform's Verilog template declares as ports, and the
#: ground both halves share. There is one ground and no analog counterpart to
#: it: an analog return is the tile's own ground, star-routed inside, and the
#: sources outside share one node on the board (`docs/topology.md`).
#:
#: These are the specification's names, and they are not the vendored DEF's.
#: That file carries a power special net called `VPWR`; the Verilog template
#: calls the 1.8 V supply `VDPWR`. The two come from different repositories and
#: they disagree. A port list has to match the Verilog, so the Verilog's name is
#: the one declared here, and the layout's is a question for submission.
GROUND = "VGND"
SUPPLY = "VDPWR"

#: The second, 3.3 V analog supply. A project asks for it and must then use a
#: different template; this one does not, every device in it being a 1.8 V
#: core device.
SUPPLY_ANALOG = "VAPWR"

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
