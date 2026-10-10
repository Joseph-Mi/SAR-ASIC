"""The configuration the host writes, and when each write takes effect.

Contract: a write names a register; a field is the unit that means something. A
field wider than one register occupies consecutive addresses, least significant
register first, and is written one register at a time.

A held write reaches the analog half only once no conversion is running and no
frame of writes is open. Both conditions earn their place, for different
reasons: a conversion must not have the array's drive change under it, and a
field wider than the bus takes more than one write, so the frame is what makes
those writes one change rather than several. A host that spreads such a field
over two frames gets no such promise -- which is the reason a frame may carry
more than one write.

Reading back a writable field returns what was last written to it, not what is in
effect. The two differ only while a conversion is running, and a host that needs
to know a held write has landed waits for the conversion to end.

Addresses are not written down, with one exception. A register's address is its
position in the layout, so a field that outgrows one register pushes the rest
along instead of landing on top of them. The exception is the identity register,
which is declared first and so sits at the bottom of the map.

The identity is a constant the hardware reports, derived from everything else
the layout says. A host compares it against the value it was built against and
stops rather than writing configuration into a map it does not share -- a check
worth having because the map the silicon holds is frozen at tapeout while this
one keeps moving. It sits at the bottom for two reasons: a check whose own
address can move cannot be found by the host that needs it, and a frame of all
zeros reads the bottom register, so the value a line nobody drives returns is
the one that proves the part is answering at all. For that second reason the
identity is never a value a line that is not being driven can produce.

What the identity is derived from does not include the identity: a number
covering itself would have nothing to settle on. Nor does it include the
framing, which is not this map's to state -- but the width of a register is,
and the framing follows from that.

Nothing here decides how a write arrives. The framing on the wire belongs to
whatever carries it; this is only what the registers are and what they do.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from interface import N_BITS

#: Bits in one register, and so the width of one write. A field wider than this
#: spans consecutive addresses.
REGISTER_WIDTH = 8

#: Whether the host may write a field, or only read what the converter reports.
RW, RO = "rw", "ro"

#: The register that says which map this is.
IDENTITY = "identity"

#: Bits of the derived hash a host checks at compile time. The identity register
#: carries as many of them as a register holds.
HASH_BITS = 32

#: What a line nobody drives reads as, high or low. The identity takes
#: neither, so a host can tell the part from a dead wire.
UNDRIVEN = (0, (1 << REGISTER_WIDTH) - 1)

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
    (IDENTITY, (Field(IDENTITY, width=REGISTER_WIDTH, access=RO),)),
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


def description() -> list[dict]:
    """Everything about this map a host could act on, in address order.

    Where each field sits, how wide it is, whether the host may write it, whether
    it waits for a conversion, and what it comes up as. A change to any of these
    misleads a host built against the map it replaced; a change to anything else
    here -- prose, the order fields are declared within one address -- cannot, so
    it is not described.
    """
    return [
        {
            "name": field.name,
            "address": FIELD_ADDRESS[field.name],
            "registers": field.registers,
            "shift": field.offset,
            "width": field.width,
            "access": field.access,
            "held": field.held,
            "reset": field.reset,
        }
        for field in FIELDS
    ]


def hash_of(described: list[dict]) -> int:
    """The number two ends compare to tell whether they mean the same map.

    Derived, never set: a version somebody has to remember to raise is a version
    that stays where it was. Order is not part of a description, so the fields
    are hashed by name -- reordering the declaration does not read as a map
    change to every host already in the field.
    """
    canonical = {
        "register_width": REGISTER_WIDTH,
        "register_count": COUNT,
        "fields": sorted(described, key=lambda field: field["name"]),
    }
    text = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(text.encode()).digest()
    return int.from_bytes(digest, "big") >> (len(digest) * 8 - HASH_BITS)


#: The whole hash, which a host checks where it has room for all of it.
MAP_HASH = hash_of(description())

#: As much of it as the identity register holds, mapped onto the values a line
#: that is not being driven cannot produce.
IDENTITY_VALUE = min(UNDRIVEN) + 1 + MAP_HASH % ((1 << REGISTER_WIDTH) - len(UNDRIVEN))

#: What the hardware reports in a field nothing else drives: a tie-off, not a
#: register, so no reset and no write reaches it.
REPORTED = {IDENTITY: IDENTITY_VALUE}


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
        self._observed = {f.name: REPORTED.get(f.name, f.reset) for f in FIELDS if f.access == RO}
        self._converting = False
        self._selected = False

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
        """Whether a conversion is in progress."""
        self._converting = bool(busy)
        self._settle()

    def selected(self, open_frame: bool) -> None:
        """Whether a frame of writes is open. Nothing a frame carries takes
        effect until it closes, so the writes that make up one field wider than
        the bus become one change."""
        self._selected = bool(open_frame)
        self._settle()

    def _settle(self) -> None:
        """Held writes reach the analog half whenever it is safe, so no write is
        left stranded by a part that is never asked to convert again."""
        if not self._converting and not self._selected:
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
