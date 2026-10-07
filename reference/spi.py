"""The frame that carries a register access, byte by byte.

Contract: a frame is one assertion of the select line. Its first byte says which
way and where; every byte after it is data, and the address steps on by one for
each -- so a field wider than the bus is set by one frame rather than by several,
and the frame is what makes those writes one change.

Nothing here is timing. Which clock edge a bit is sampled on, and how many of
them a byte takes, belong to the wire rather than to the frame.

A frame of all zeros -- a line nobody drives, or one stuck low -- reads address
zero and changes nothing. That is why the direction bit means write when it is
set: the quiet case has to be the harmless one.
"""

from __future__ import annotations

from registers import COUNT, REGISTER_WIDTH, Registers, writes_for

#: The command byte: the top bit says which way, the rest says where.
DIRECTION = REGISTER_WIDTH - 1
ADDRESS_MASK = (1 << DIRECTION) - 1
WRITE = 1 << DIRECTION

#: What the slave presents when it has nothing to say -- while the command byte
#: is still arriving, and throughout a write. It cannot know what was asked for
#: until that byte is whole.
IDLE_BYTE = 0


def command(address: int, write: bool) -> int:
    """A frame's first byte."""
    if not 0 <= address <= ADDRESS_MASK:
        raise ValueError(f"{address:#04x} does not fit a command byte")
    return (WRITE if write else 0) | address


class Slave:
    """The register file as the wire reaches it."""

    def __init__(self, registers: Registers | None = None) -> None:
        self.registers = Registers() if registers is None else registers
        self._address = 0
        self._writing = False
        self._expecting_command = True

    def select(self) -> None:
        """The select line asserted. A frame begins, and anything still in the
        previous one is already finished with."""
        self._expecting_command = True
        self.registers.selected(True)

    def transfer(self, byte: int) -> int:
        """One byte in, one byte out.

        An address past the end of the map takes no write and reads as nothing.
        Hardware cannot refuse: it has no way to tell the host, and a decoder
        that wrapped instead would land the write on a register that exists.
        """
        if not 0 <= byte < 1 << REGISTER_WIDTH:
            raise ValueError(f"{byte} is not a byte")
        if self._expecting_command:
            self._expecting_command = False
            self._writing = bool(byte & WRITE)
            self._address = byte & ADDRESS_MASK
            return IDLE_BYTE

        out = IDLE_BYTE
        if self._address < COUNT:
            if self._writing:
                self.registers.write(self._address, byte)
            else:
                out = self.registers.read(self._address)
        self._address += 1
        return out

    def deselect(self) -> None:
        """The select line released. The frame's writes take effect together,
        once no conversion is in the way."""
        self.registers.selected(False)

    def write(self, address: int, *values: int) -> None:
        """One frame: consecutive registers from `address`."""
        self.select()
        self.transfer(command(address, write=True))
        for value in values:
            self.transfer(value)
        self.deselect()

    def read(self, address: int, count: int = 1) -> list[int]:
        """One frame: consecutive registers from `address`."""
        self.select()
        self.transfer(command(address, write=False))
        out = [self.transfer(IDLE_BYTE) for _ in range(count)]
        self.deselect()
        return out

    def configure(self, **values: int) -> None:
        """Set these fields in one frame, so the analog half takes them together.

        The address steps on by one per byte, so the frame covers every register
        between the lowest and highest asked for. Any in between that nothing
        asked about are written with what they already hold, which is why a
        writable field reads back as what was last written to it.
        """
        pieces = dict(writes_for(**values))
        first, last = min(pieces), max(pieces)
        self.write(first, *(pieces.get(a, self.registers.read(a)) for a in range(first, last + 1)))
