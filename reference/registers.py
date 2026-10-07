"""The configuration the host writes, and when each write takes effect.

Contract: a write names a register; a field is the unit that means something. A
field wider than one register occupies consecutive addresses, least significant
register first, and is written one register at a time -- so a word wider than the
bus is never half-applied to the analog half: see `held`.

Reading back a writable field returns what was last written to it, not what is in
effect. The two differ only while a conversion is running, and a host that needs
to know a held write has landed waits for the conversion to end.

Addresses are not written down. A register's address is its position in the
layout, so a field that outgrows one register pushes the rest along instead of
landing on top of them.

Nothing here decides how a write arrives. The framing on the wire belongs to
whatever carries it; this is only what the registers are and what they do.
"""

from __future__ import annotations

from dataclasses import dataclass

from interface import N_BITS

#: Bits in one register, and so the width of one write. A field wider than this
#: spans consecutive addresses.
REGISTER_WIDTH = 8

#: Whether the host may write a field, or only read what the converter reports.
RW, RO = "rw", "ro"

#: What the dedicated outputs show. The result unless asked otherwise, so a part
#: nobody has configured reads as a converter.
VIEW_CODE, VIEW_COMPARATOR, VIEW_SEARCH = range(3)
VIEWS = (VIEW_CODE, VIEW_COMPARATOR, VIEW_SEARCH)


def bits_for(count: int) -> int:
    """Bits needed to tell `count` things apart."""
    return max(1, (count - 1).bit_length())


@dataclass(frozen=True)
class Field:
    """One meaning, somewhere in a register."""

    name: str
    offset: int = 0
    width: int = 1
    access: str = RW
    #: Whether the write waits for a conversion to end. Anything the analog half
    #: acts on is held: changing the array's drive or the input's source part-way
    #: through a search abandons the charge the sample put there, and the code
    #: that comes out belongs to neither setting.
    held: bool = False
    reset: int = 0

    @property
    def registers(self) -> int:
        """Consecutive addresses the field occupies."""
        return -(-self.width // REGISTER_WIDTH)

    @property
    def mask(self) -> int:
        return (1 << self.width) - 1


#: The registers, in address order. A group holding a field wider than one
#: register holds nothing else: that field's bits are the whole of every address
#: it covers.
LAYOUT = (
    (
        "control",
        (
            Field("raw_dac", offset=0, held=True),
            Field("force_en", offset=1, held=True),
            Field("force_hi", offset=2, held=True),
        ),
    ),
    # The conversion clock divides the system clock by this plus one. It resets to
    # the slowest the field can ask for: a converter too slow out of reset still
    # converts correctly, while one too fast returns codes that are wrong and
    # plausible, which is the worse thing to ship.
    (
        "clk_div",
        (Field("clk_div", width=REGISTER_WIDTH, held=True, reset=(1 << REGISTER_WIDTH) - 1),),
    ),
    ("dac", (Field("dac", width=N_BITS, held=True),)),
    ("view", (Field("view", width=bits_for(len(VIEWS)), reset=VIEW_CODE),)),
    (
        "status",
        (
            Field("ready", offset=0, access=RO),
            Field("done", offset=1, access=RO),
            Field("metastable", offset=2, access=RO),
            Field("cmp_out", offset=3, access=RO),
        ),
    ),
    ("search", (Field("bit_index", width=bits_for(N_BITS), access=RO),)),
)


def _placed() -> tuple[dict[str, int], dict[str, int]]:
    """Each register's address, and each field's, by laying the groups out."""
    registers: dict[str, int] = {}
    fields: dict[str, int] = {}
    address = 0
    for name, group in LAYOUT:
        registers[name] = address
        for field in group:
            fields[field.name] = address
        address += max(field.registers for field in group)
    return registers, fields


#: Where each register and each field sits.
ADDRESS, FIELD_ADDRESS = _placed()

FIELDS = tuple(field for _, group in LAYOUT for field in group)
BY_NAME = {field.name: field for field in FIELDS}

#: Addresses the map answers to: a contiguous range from zero, so the decoder is
#: a bound check and a gap can never be read as a register that holds nothing.
COUNT = max(FIELD_ADDRESS[f.name] + f.registers for f in FIELDS)


def fields_at(address: int) -> list[Field]:
    """The fields any part of which lives at `address`."""
    spans = ((f, FIELD_ADDRESS[f.name]) for f in FIELDS)
    return [f for f, start in spans if start <= address < start + f.registers]


def placement(field: Field, address: int) -> tuple[int, int, int]:
    """Where `address` holds part of `field`: the field's own bit the register's
    slice starts at, how many bits it carries, and where in the register they
    sit."""
    if field.registers == 1:
        return 0, field.width, field.offset
    start = (address - FIELD_ADDRESS[field.name]) * REGISTER_WIDTH
    return start, min(REGISTER_WIDTH, field.width - start), 0


def writes_for(**values: int) -> list[tuple[int, int]]:
    """The register writes that set the named fields, in address order.

    A register is written whole, so every writable field of every address this
    touches has to be named: leaving one out would write it as zero, which is a
    setting nobody asked for. Refusing is better than quietly clearing it.
    """
    touched: dict[int, int] = {}
    for name, value in values.items():
        field = BY_NAME[name]
        if field.access != RW:
            raise KeyError(f"{name} is not the host's to write")
        if not 0 <= value <= field.mask:
            raise ValueError(f"{name}={value} does not fit {field.width} bits")
        for i in range(field.registers):
            address = FIELD_ADDRESS[name] + i
            start, width, offset = placement(field, address)
            touched[address] = touched.get(address, 0) | (
                ((value >> start) & ((1 << width) - 1)) << offset
            )
    missing = sorted(
        f.name
        for address in touched
        for f in fields_at(address)
        if f.access == RW and f.name not in values
    )
    if missing:
        raise KeyError(f"these share a register with what was asked for: {missing}")
    return sorted(touched.items())


class Registers:
    """The register file: what the host wrote, and what is in effect."""

    def __init__(self) -> None:
        self._written = {f.name: f.reset for f in FIELDS}
        self._live = dict(self._written)
        self._observed = {f.name: f.reset for f in FIELDS if f.access == RO}

    def _check(self, address: int) -> None:
        if not 0 <= address < COUNT:
            raise KeyError(f"no register at {address:#04x}")

    def write(self, address: int, value: int) -> None:
        self._check(address)
        if not 0 <= value < 1 << REGISTER_WIDTH:
            raise ValueError(f"{value} does not fit a register")
        for field in fields_at(address):
            if field.access != RW:
                continue
            start, width, offset = placement(field, address)
            piece = (value >> offset) & ((1 << width) - 1)
            kept = self._written[field.name] & ~(((1 << width) - 1) << start)
            self._written[field.name] = kept | piece << start
            if not field.held:
                self._live[field.name] = self._written[field.name]

    def read(self, address: int) -> int:
        self._check(address)
        out = 0
        for field in fields_at(address):
            start, width, offset = placement(field, address)
            source = self._observed if field.access == RO else self._written
            out |= ((source[field.name] >> start) & ((1 << width) - 1)) << offset
        return out

    def converting(self, busy: bool) -> None:
        """Whether a conversion is in progress. A held write reaches the analog
        half whenever one is not, so no write is ever stranded."""
        if not busy:
            self._live = dict(self._written)

    def observe(self, **values: int) -> None:
        """What the converter reports in the fields it owns."""
        for name, value in values.items():
            field = BY_NAME[name]
            if field.access != RO:
                raise KeyError(f"{name} is not the converter's to report")
            if not 0 <= value <= field.mask:
                raise ValueError(f"{name}={value} does not fit {field.width} bits")
            self._observed[name] = value

    def __getitem__(self, name: str) -> int:
        """The value in effect."""
        return self._observed[name] if BY_NAME[name].access == RO else self._live[name]

    def written(self, name: str) -> int:
        """The value last written, in effect or not."""
        return self._written[name]
