"""The register map as something other than Python reads it.

Contract: the layout declares the map once, and every rendering of it is derived
from that declaration. Nothing here decides anything -- it restates what the
registers already are, in the two forms a host outside this repository can use:
a C header for firmware to include, and the same facts as data for anything that
is not C.

A rendering that is written by hand agrees with the layout on the day it is
written and never again. These are generated, committed, and compared against a
fresh generation by a test, so a field that moves either comes with regenerated
outputs or fails.

Neither rendering states a fact of its own. The map's identity and the hash it
comes from are the layout's, carried through to where a host can check them: at
compile time against the whole hash, and at run time against the byte the part
reports.
"""

from __future__ import annotations

import json
import pathlib

from registers import (
    ADDRESS,
    COUNT,
    FIELD_ADDRESS,
    FIELDS,
    HASH_BITS,
    IDENTITY,
    IDENTITY_VALUE,
    LAYOUT,
    MAP_HASH,
    REGISTER_WIDTH,
    REPORTED,
    RW,
    description,
    fields_at,
    placement,
)
from spi import ADDRESS_MASK, IDLE_BYTE, WRITE

#: The hash as hex: one digit per four bits.
HASH_DIGITS = HASH_BITS // 4

#: Prefix on every name the C header defines, so a host including it cannot
#: collide with its own.
PREFIX = "SAR"

#: What the generated files are written as.
ENCODING = "utf-8"
INDENT = 2
NEWLINE = "\n"

#: How a C header spells an unsigned constant, and the width firmware needs to
#: hold a field wider than one register.
SUFFIX = "u"
WIDE_TYPE = "uint32_t"
BYTE_TYPE = "uint8_t"

#: Names the two language renderings share, so one register's facts are found
#: under the same spelling whichever file a reader has open.
ADDR, SHIFT, WIDTH, REGISTERS, VALUE = "addr", "shift", "width", "registers", "value"

#: The command `make` runs to rewrite these files. Named here because a
#: generated file whose reader cannot tell how to regenerate it gets edited.
REGENERATE = "make regmap"

GUARD = f"{PREFIX}_REGS_H"


def _name(*parts: str) -> str:
    return "_".join((PREFIX, *parts)).upper()


def slices() -> list[dict]:
    """Every address in the map, with the part of each field that lives there.

    A field wider than one register occupies several, so it appears once per
    address it reaches, each time carrying which of its own bits that address
    holds. Reading a field back means collecting those pieces; writing it means
    handing them over in address order.
    """
    groups = {address: name for name, address in ADDRESS.items()}
    out = []
    group = None
    for address in range(COUNT):
        group = groups.get(address, group)
        parts = []
        for field in fields_at(address):
            start, width, shift = placement(field, address)
            parts.append(
                {
                    "field": field.name,
                    "field_bit": start,
                    "width": width,
                    "shift": shift,
                    "access": field.access,
                }
            )
        out.append({"address": address, "group": group, "parts": parts})
    return out


def as_data() -> dict:
    """The map as data, for a host that is not C."""
    return {
        "generated": f"Do not edit. Regenerate with `{REGENERATE}`.",
        "map_hash": f"{MAP_HASH:#0{HASH_DIGITS + 2}x}",
        "identity_value": IDENTITY_VALUE,
        "register_width": REGISTER_WIDTH,
        "register_count": COUNT,
        "frame": {
            "write_bit": WRITE,
            "address_mask": ADDRESS_MASK,
            "idle_byte": IDLE_BYTE,
            "address_steps_per_byte": 1,
        },
        "fields": description(),
        "registers": slices(),
    }


def as_json() -> str:
    return json.dumps(as_data(), indent=INDENT) + NEWLINE


def _header_lines() -> list[str]:
    lines = [
        "/* The register map, generated from the layout that declares it.",
        " *",
        f" * Do not edit. Regenerate with `{REGENERATE}`.",
        " *",
        " * A frame is one assertion of the select line: a command byte saying which",
        " * way and where, then one byte per register, the address stepping on by one",
        " * for each. A field wider than one register is carried least significant",
        " * register first, and one frame is what makes those writes one change.",
        " *",
        " * A register is written whole, so setting one field of an address means",
        " * reading the others back and writing them with what they hold. Writing a",
        " * value nobody asked for is what leaving one out does.",
        " */",
        f"#ifndef {GUARD}",
        f"#define {GUARD}",
        "",
        "#include <stdint.h>",
        "",
        f"#define {_name('REGISTER_WIDTH')} {REGISTER_WIDTH}{SUFFIX}",
        f"#define {_name('REGISTER_COUNT')} {COUNT}{SUFFIX}",
        "",
        "/* The map both ends have to agree on. Firmware states the map it was written",
        f" * against once, and {_name('REQUIRE_MAP')} refuses to compile against another.",
        " *",
        " * That check is against this header. The part itself is asked at run time:",
        f" * read {_name(IDENTITY, 'ADDR')} and compare it against {_name(IDENTITY, 'VALUE')}",
        " * before writing any configuration, because the map a part was taped out",
        " * with is frozen and this one is not. The value is never what an undriven",
        " * line reads as, so the same check catches a bus that is not answering. */",
        f"#define {_name('MAP_HASH')} {MAP_HASH:#0{HASH_DIGITS + 2}x}{SUFFIX}",
        f"#define {_name(IDENTITY, 'VALUE')} {IDENTITY_VALUE:#04x}{SUFFIX}",
        f"#define {_name('REQUIRE_MAP')}(hash) \\",
        f'  _Static_assert((hash) == {_name("MAP_HASH")}, "the register map has moved")',
        "",
        "/* The command byte. The direction bit means write when it is set, so a line",
        " * nobody drives reads the first register and changes nothing. */",
        f"#define {_name('FRAME_WRITE')} {WRITE:#04x}{SUFFIX}",
        f"#define {_name('FRAME_ADDRESS_MASK')} {ADDRESS_MASK:#04x}{SUFFIX}",
        f"#define {_name('FRAME_IDLE_BYTE')} {IDLE_BYTE:#04x}{SUFFIX}",
        "",
    ]

    lines += [
        f"static inline {BYTE_TYPE} {PREFIX.lower()}_command({BYTE_TYPE} address, int write)",
        "{",
        f"  return ({BYTE_TYPE})((write ? {_name('FRAME_WRITE')} : 0{SUFFIX})"
        f" | (address & {_name('FRAME_ADDRESS_MASK')}));",
        "}",
        "",
        "/* One register's worth of a field, least significant register first: the bytes",
        " * a frame carries, in the order it carries them. */",
        f"static inline {BYTE_TYPE} {PREFIX.lower()}_field_byte({WIDE_TYPE} value, unsigned index)",
        "{",
        f"  return ({BYTE_TYPE})(value >> (index * {_name('REGISTER_WIDTH')}));",
        "}",
        "",
        f"#define {_name('FIELD_GET')}(reg, shift, mask) (((reg) >> (shift)) & (mask))",
        f"#define {_name('FIELD_SET')}(reg, shift, mask, value) \\",
        "  (((reg) & ~((mask) << (shift))) | (((value) & (mask)) << (shift)))",
        "",
    ]

    for group, fields in LAYOUT:
        address = ADDRESS[group]
        span = max(field.registers for field in fields)
        reach = f"{address:#04x}" if span == 1 else f"{address:#04x}..{address + span - 1:#04x}"
        lines.append(f"/* {group} @ {reach} */")
        lines.append(f"#define {_name('ADDR', group)} {address:#04x}{SUFFIX}")
        for field in fields:
            tags = [field.access]
            if field.held:
                tags.append("held")
            if field.name in REPORTED:
                tags.append("constant")
            lines.append(f"/* {field.name}: {field.width} bit, {', '.join(tags)} */")
            lines.append(
                f"#define {_name(field.name, 'ADDR')} {FIELD_ADDRESS[field.name]:#04x}{SUFFIX}"
            )
            lines.append(f"#define {_name(field.name, 'REGISTERS')} {field.registers}{SUFFIX}")
            lines.append(f"#define {_name(field.name, 'WIDTH')} {field.width}{SUFFIX}")
            lines.append(f"#define {_name(field.name, 'SHIFT')} {field.offset}{SUFFIX}")
            lines.append(f"#define {_name(field.name, 'MASK')} {field.mask:#x}{SUFFIX}")
            lines.append(f"#define {_name(field.name, 'WRITABLE')} {int(field.access == RW)}")
            lines.append(f"#define {_name(field.name, 'HELD')} {int(field.held)}")
            if field.name not in REPORTED:
                lines.append(f"#define {_name(field.name, 'RESET')} {field.reset:#x}{SUFFIX}")
        lines.append("")

    lines.append(f"#endif /* {GUARD} */")
    return lines


def as_c_header() -> str:
    return NEWLINE.join(_header_lines()) + NEWLINE


def packed(per_address) -> list[str]:
    """One constant holding a byte per register, as the concatenation Verilog
    reads it: the highest address first, so a part-select at an address times a
    register's width lands on that register's byte."""
    lines = []
    for address in reversed(range(COUNT)):
        value = per_address(address)
        comma = "" if address == 0 else ","
        lines.append(
            f"    {REGISTER_WIDTH}'h{value:0{REGISTER_WIDTH // 4}x}{comma}"
            f"  // {address:#04x} {_group_at(address)}"
        )
    return lines


def _group_at(address: int) -> str:
    """The register's own name, or the name of the group that reaches into it."""
    reaching = {start: name for name, start in ADDRESS.items() if start <= address}
    return reaching[max(reaching)]


def _bits(address: int, wanted) -> int:
    """The bits at `address` belonging to fields `wanted` accepts, in place."""
    value = 0
    for field in fields_at(address):
        if not wanted(field):
            continue
        start, width, shift = placement(field, address)
        value |= ((field.reset >> start) & ((1 << width) - 1)) << shift
    return value


def _placed_mask(address: int, wanted) -> int:
    value = 0
    for field in fields_at(address):
        if not wanted(field):
            continue
        _, width, shift = placement(field, address)
        value |= ((1 << width) - 1) << shift
    return value


def _verilog_lines() -> list[str]:
    writable = f"{PREFIX}_WRITABLE"
    held = f"{PREFIX}_HELD"
    reset = f"{PREFIX}_RESET"
    count = _name("REGISTER_COUNT")
    width = _name("REGISTER_WIDTH")
    word = f"[{count}*{width}-1:0]"

    lines = [
        "// The register map, generated from the layout that declares it.",
        "//",
        f"// Do not edit. Regenerate with `{REGENERATE}`.",
        "//",
        "// Declarations, not macros: these are included inside the module that needs",
        "// them, so they are scoped to it. A macro would outlive the file that set it",
        "// and reach every file compiled after.",
        "//",
        "// The scalars are untyped on purpose. Declared as integers they would be",
        "// thirty-two bits wide, which widens every comparison against an address bus",
        "// and every part-select that uses one, and the lint warning for it would be",
        "// raised in the module rather than here.",
        "//",
        "// The packed words carry one register per byte, the lowest address in the",
        "// lowest byte, so a part-select at an address times a register's width",
        "// lands on that register's byte. A bit set in them means, in turn: the host",
        "// may write it, that write waits for a conversion to end, and what it comes",
        "// up as out of reset. A bit no writable field claims is not stored, so it is",
        "// clear in all three.",
        "",
        f"localparam {width} = {REGISTER_WIDTH};",
        f"localparam {count} = {COUNT};",
        "",
        "// What reading the identity register must return. A host checks it to know",
        "// it means the same map, and because the value is never what an undriven",
        "// line reads as, the same read catches a bus that is not answering.",
        f"localparam [{width}-1:0] {_name(IDENTITY, VALUE)} ="
        f" {REGISTER_WIDTH}'h{IDENTITY_VALUE:02x};",
        "",
        f"localparam {word} {writable} = {{",
        *packed(lambda a: _placed_mask(a, lambda f: f.access == RW)),
        "};",
        "",
        f"localparam {word} {held} = {{",
        *packed(lambda a: _placed_mask(a, lambda f: f.access == RW and f.held)),
        "};",
        "",
        f"localparam {word} {reset} = {{",
        *packed(lambda a: _bits(a, lambda f: f.access == RW)),
        "};",
        "",
    ]

    for field in FIELDS:
        lines.append(f"// {field.name}")
        for suffix, value in (
            (ADDR, FIELD_ADDRESS[field.name]),
            (SHIFT, field.offset),
            (WIDTH, field.width),
            (REGISTERS, field.registers),
        ):
            lines.append(f"localparam {_name(field.name, suffix)} = {value};")
    return lines


def as_verilog() -> str:
    return NEWLINE.join(_verilog_lines()) + NEWLINE


#: Where each rendering is written, and what fills it. A path rather than a bare
#: name: the one the RTL includes belongs with the RTL, and the two a host reads
#: belong somewhere a firmware repository can vendor without taking a layer.
RENDERINGS = {
    "firmware/sar_regs.h": as_c_header,
    "firmware/sar_regs.json": as_json,
    "hdl/rtl/sar_regs.vh": as_verilog,
}

REPO = pathlib.Path(__file__).resolve().parent.parent


def rendered() -> dict[str, str]:
    return {path: render() for path, render in RENDERINGS.items()}


def main() -> None:
    for path, text in rendered().items():
        out = REPO / path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding=ENCODING)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
