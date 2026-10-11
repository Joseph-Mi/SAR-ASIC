"""What the result pins carry when they are not carrying a result.

Two of the design-for-test modes read nothing back over the configuration bus.
They put a signal on the result pins instead and let an instrument watch it: a
single read says what a signal was once, where what these two are for is what it
does across a conversion.

Contract: `shown` is the word the result pins carry, and the pin map alone
decides which pin each of its bits reaches. The code unless asked otherwise, so
a part nobody has configured reads as a converter.

A stream sits in the bits the dedicated outputs carry, lowest first. Those pins
cannot contend with anything on the board, which is what makes them the ones
worth clipping a probe to, and it is the pin map that says which bits of the
word they are.

Streaming is exempt from the rule that the result pins change only at the end of
a conversion: changing inside one is the whole point of it, and a stream is not
an accuracy measurement. Whatever is watching gets the flag as its frame marker
either way, because the flag still marks a conversion ending.
"""

from __future__ import annotations

from interface import N_BITS
from pins import SPILLED
from registers import VIEW_CODE, VIEW_COMPARATOR, VIEWS, bits_for

#: The lowest bit of the word that a dedicated output carries. The bits below
#: it are the ones the dedicated outputs could not hold.
PROBE_SHIFT = len(SPILLED)

#: Bits of the word the dedicated outputs carry, and so how wide a stream can
#: be.
PROBE_WIDTH = N_BITS - PROBE_SHIFT

#: Bits each stream needs: the latch's two outputs, and enough to count every
#: bit of the search.
COMPARATOR_WIDTH = 2
SEARCH_WIDTH = bits_for(N_BITS)


def shown(view: int, code: int, cmp_out: bool, cmp_out_n: bool, bit_index: int) -> int:
    """The word the result pins carry.

    Both latch outputs, not just the decision: the two being equal is the
    metastability flag, and on the pins it is visible as it happens rather than
    only as a bit a host has to go and read.
    """
    if view not in VIEWS:
        raise ValueError(f"{view} is not one of {VIEWS}")
    for name, value, width in (("code", code, N_BITS), ("bit_index", bit_index, SEARCH_WIDTH)):
        if not 0 <= value < (1 << width):
            raise ValueError(f"{name} {value} does not fit {width} bits")
    if view == VIEW_CODE:
        return code
    if view == VIEW_COMPARATOR:
        return (int(bool(cmp_out)) | int(bool(cmp_out_n)) << 1) << PROBE_SHIFT
    return bit_index << PROBE_SHIFT
