"""The chip's pins, and what each one carries.

Contract: this is the only place the pin assignment is declared. The top-level
port map, the bidirectional group's output enables and every bench that drives
or reads a pin derive from here. Nothing else names a pin number.

The platform fixes the four groups -- dedicated inputs, dedicated outputs,
bidirectional pins whose direction the design chooses per pin, and the analog
pins. A pin the design does not use still has to appear: an output left
undriven floats, and a bidirectional pin left enabled fights whatever is on
the other side of it.

The analog pins differ from the rest in that they are bought. They are
connected from index zero upward, as many as the submission declares, so their
order is a platform rule rather than a layout preference.
"""

from __future__ import annotations

from interface import N_BITS

#: Pins the platform gives in each group.
GROUP_WIDTH = 8

#: Which way a signal points, seen from the chip. An analog pin points both
#: ways: it reaches the pad through a switch, and what is on the other side of
#: it is the board's business rather than the design's.
OUT, IN, ANALOG = "out", "in", "analog"

CODE = "code"
DONE = "done"
HOLD = "hold"
START = "start"
SINGLE_SHOT = "single_shot"
EDGE_CAPTURE = "edge_capture"
SPI_CS_N = "spi_cs_n"
SPI_MOSI = "spi_mosi"
SPI_MISO = "spi_miso"
SPI_SCK = "spi_sck"
VIN = "vin"
VREF = "vref"
VCM = "vcm"

#: The bidirectional pins the platform's own conventions put SPI on, in order.
#: Following them is what lets an off-the-shelf daughterboard talk to the chip.
SPI_PINS = (SPI_CS_N, SPI_MOSI, SPI_MISO, SPI_SCK)


def code_bit(k: int) -> str:
    """One bit of the result, as the pin map names it."""
    return f"{CODE}[{k}]"


def _padded(signals: tuple[str, ...]) -> tuple[str | None, ...]:
    """A group, bit 0 first, with None on every pin left over."""
    if len(signals) > GROUP_WIDTH:
        raise ValueError(f"{len(signals)} signals do not fit {GROUP_WIDTH} pins")
    return signals + (None,) * (GROUP_WIDTH - len(signals))


#: Result bits the dedicated outputs cannot hold, least significant first.
#: The dedicated outputs keep the most significant bits, because those pins on
#: their own have to read as a number across the whole input range: the low
#: bits on their own wrap, once per output pin the result outgrows.
SPILLED = tuple(code_bit(k) for k in range(max(0, N_BITS - GROUP_WIDTH)))

#: Dedicated outputs. They cannot contend with anything, which is why the
#: result rather than a shared signal sits here.
UO_OUT = _padded(tuple(code_bit(k) for k in range(len(SPILLED), N_BITS)))

#: Bidirectional pins: SPI where the platform's conventions want it, then what
#: the dedicated outputs could not hold, then the flag that says the result
#: pins just changed.
UIO = _padded(SPI_PINS + SPILLED + (DONE,))

#: Dedicated inputs. The two modes are pins rather than register fields so the
#: part can be put in either one with a jumper and no firmware at all.
UI_IN = _padded((HOLD, START, SINGLE_SHOT, EDGE_CAPTURE))

#: Analog pins the platform will connect. The template draws eight and the
#: specification allows the first six; the other two exist in the port and on
#: the die and are not bonded, which is worse than absent -- a signal placed
#: there looks routed and is not.
ANALOG_WIDTH = 6

#: The analog pins, in order. The order is the platform's own rule and not a
#: preference: pins are bought one at a time and connected from zero upward
#: with no gaps, so a design using three uses `ua[0..2]`, and a gap left for
#: tidiness is a pin that was paid for and not connected.
#:
#: Which signal takes which index is still open. The pads do not decide it --
#: they are met4 shapes about a micrometre wide on a twenty-micrometre pitch,
#: where pad-to-pad coupling is not what limits anything -- so what decides it
#: is the routing behind them, and that waits on where the comparator lands in
#: the analog strip. The order below is therefore provisional, and the tests
#: hold the part of this that is not: the count, and that the pins are used
#: from zero with no gaps.
UA = _padded((VIN, VREF, VCM))

GROUPS = {"ui_in": UI_IN, "uo_out": UO_OUT, "uio": UIO, "ua": UA}

#: Every signal the pins carry, and which way it points.
DIRECTIONS = {
    **{code_bit(k): OUT for k in range(N_BITS)},
    DONE: OUT,
    SPI_MISO: OUT,
    SPI_CS_N: IN,
    SPI_MOSI: IN,
    SPI_SCK: IN,
    HOLD: IN,
    START: IN,
    SINGLE_SHOT: IN,
    EDGE_CAPTURE: IN,
    VIN: ANALOG,
    VREF: ANALOG,
    VCM: ANALOG,
}


def assignments() -> dict[tuple[str, int], str]:
    """Every pin that carries a signal, keyed by its group and bit."""
    return {(group, i): s for group, pins in GROUPS.items() for i, s in enumerate(pins) if s}


def analog_pins() -> list[str]:
    """The analog pins the design uses, in index order.

    Its length is what the submission has to declare and pay for: a pin the
    project does not claim is not connected, whatever the layout attaches to
    it.
    """
    return [signal for signal in UA[:ANALOG_WIDTH] if signal]


def uio_oe() -> int:
    """Output enables for the bidirectional group: a bit set where the design
    drives the pin, clear everywhere else. A pin the design does not drive --
    an input, or one it does not use -- then never contends."""
    return sum(1 << i for i, s in enumerate(UIO) if s and DIRECTIONS[s] == OUT)


def code_pins() -> list[tuple[str, int]]:
    """Where each bit of the result appears, least significant first."""
    found = {s: pin for pin, s in assignments().items()}
    return [found[code_bit(k)] for k in range(N_BITS)]
