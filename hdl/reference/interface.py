"""The contract between the two halves of the chip.

Contract: this module is the only place the analog/digital boundary is
declared. The Xschem symbol, the RTL port list and the testbenches all derive
from it, and a test asserts the symbol still agrees. Adding or renaming a wire
is an edit here plus a redrawn symbol, and the test fails until both are done.

Resolution is a parameter rather than a constant everywhere else because the
array's area, its settling time and the comparator's least significant bit all
scale with it, and the choice is not settled until a tile budget and a measured
comparator exist. Nothing downstream may restate the width.
"""

from __future__ import annotations

from dataclasses import dataclass

N_BITS = 10


@dataclass(frozen=True)
class Port:
    """One terminal of the analog block, as the symbol must declare it."""

    name: str
    direction: str
    width: int = 1

    @property
    def declaration(self) -> str:
        """How the name appears on the symbol: a bus carries its range."""
        return self.name if self.width == 1 else f"{self.name}[{self.width - 1}:0]"


#: Driven by the digital half. The array's bottom plates, the sampling phase,
#: and the comparator strobe.
TO_ANALOG = (
    Port("dac_b", "in", N_BITS),
    Port("sample", "in"),
    Port("cmp_clk", "in"),
)

#: Returned to the digital half. Both latch outputs cross, so that the two
#: being equal is a metastability flag the FSM can act on.
TO_DIGITAL = (
    Port("cmp_out", "out"),
    Port("cmp_out_n", "out"),
)

#: The analog block's own terminals. The reference is a pin of its own rather
#: than a tap off the supply: the array draws charge from it on every bit
#: trial, and a shared pin has not recovered by the time the comparator fires.
ANALOG_ONLY = (
    Port("vin", "in"),
    Port("vref", "in"),
    Port("vdd", "inout"),
    Port("vss", "inout"),
)

#: Every terminal. What is frozen is the set, each name, each direction and
#: each width -- not the order, which the symbol editor assigns from geometry
#: and which a netlister then reports. Consumers wire by name and take the
#: order from whatever they are reading: a subcircuit wired by position against
#: a differently ordered declaration is miswired without complaint.
PORTS = TO_ANALOG + TO_DIGITAL + ANALOG_ONLY


def declarations() -> dict[str, str]:
    """Port names as the symbol declares them, keyed by name."""
    return {p.declaration: p.direction for p in PORTS}
