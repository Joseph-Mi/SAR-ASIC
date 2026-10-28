"""The analog block's own sheet, against the netlist its benches are built on.

`xschem/sar_analog.sch` is the tile's analog half as a drawing. It is drawn by
hand -- there is no generator for it, because above the device level a sheet is
a block diagram and a block diagram is a drawing -- so what holds it to the
design is the same thing that holds the comparator's: the editor netlists it
back, and what comes out is compared against `sim/analog.py`, which is what
every closed-loop measurement was taken on.

The sheet is incomplete on purpose. The comparator and the array are drawn;
the switches and the phase generator arrive as each is laid out. So what is
checked here is the boundary and whatever is drawn, and a block that is not on
the sheet yet is not an error. What would be an error is the boundary
drifting, or a block that *is* drawn being wired a way the measurements were
never taken at.

Each block is held to the design twice over: here, where the instance's own
wiring is compared against the netlist the benches use, and on the block's own
sheet, where every device in it is (`test_schematic.py`, `test_cap_array.py`).
That chain is what makes this drawing worth trusting rather than just worth
reading -- an instance of the right symbol wired to the right nets is the
measured circuit, whatever is inside it.
"""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest

import analog
import sheet
import strongarm

needs_xschem = pytest.mark.skipif(shutil.which("xschem") is None, reason="xschem not on PATH")

SHEET = "sar_analog.sch"

#: A continued line in a SPICE netlist. The editor wraps at a width of its
#: own choosing, so a parse that reads lines has to undo that first. A
#: commented line continues as `*+` rather than `+`, which is how the sheet's
#: own header wraps -- and a fold that misses it reads a boundary that stops
#: wherever the editor happened to break the line.
CONTINUED = re.compile(r"\n\*?\+\s*")

#: The header the editor writes for the sheet it was asked for: commented,
#: because a top-level sheet is a deck rather than a subcircuit, and carrying
#: the terminals in the order an instance of its symbol would wire them.
HEADER = re.compile(r"^\*\*\.subckt\s+(?P<name>\S+)\s+(?P<ports>.+)$", re.M)

#: How the editor separates the bits of a bus in that header.
BITS = ","


#: Elements and how many of their leading fields are nets. A subcircuit call
#: carries nets between its name and the subcircuit's; a two-terminal device
#: carries two and then a value. Anything else in the block fails the parse
#: rather than being counted wrong, so the array arriving on the sheet is a
#: deliberate edit here and not a silently weaker check.
TWO_TERMINAL = ("C", "R", "L")


def _block(netlisted: str) -> list[str]:
    """The lines of the sheet's own subcircuit, not what it expands into."""
    lines = netlisted.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("**.subckt"))
    end = next(i for i, line in enumerate(lines) if line.startswith("**.ends"))
    return lines[start + 1 : end]


def _ports(netlisted: str) -> set[str]:
    """Every terminal the sheet declares, the bus split into its bits."""
    return {
        bit
        for line in _block(netlisted)
        if line.startswith("*.")
        for name in line.split()[1:]
        for bit in name.split(BITS)
    }


def _connections(netlisted: str) -> dict[str, int]:
    """How many element terminals each net carries."""
    counted: dict[str, int] = {}
    for line in _block(netlisted):
        if line.startswith("*") or not line.strip():
            continue
        fields = line.split()
        if fields[0][0].upper() == "X":
            nets = fields[1:-1]
        elif fields[0][0].upper() in TWO_TERMINAL:
            nets = fields[1:3]
        else:
            raise AssertionError(f"this parse does not know what {fields[0]} is: {line!r}")
        for net in nets:
            counted[net] = counted.get(net, 0) + 1
    return counted


@pytest.fixture(scope="module")
def netlisted(tmp_path_factory) -> str:
    """The committed sheet as the editor netlists it."""
    drawn = sheet.SHEET_DIR / SHEET
    if not drawn.exists():
        pytest.skip(f"{SHEET} not drawn yet")
    return CONTINUED.sub(" ", sheet.netlist(SHEET, tmp_path_factory.mktemp("top")))


def instance(netlisted: str, name: str) -> list[str]:
    """One instance's nets, in the order it wires them.

    Case-insensitively, because SPICE is and the editor writes a name through
    unchanged, so the sheet and the netlist may spell it differently and mean
    the same element.
    """
    line = next(
        (
            text
            for text in netlisted.splitlines()
            if text.split()[:1] and text.split()[0].lower() == name.lower()
        ),
        None,
    )
    assert line is not None, f"{name} is not on the sheet"
    return line.split()[1:-1]


@needs_xschem
def test_the_sheet_declares_exactly_the_blocks_terminals(netlisted):
    """The boundary, in the order an instance of the symbol would wire it.

    Against `analog.terminals()` rather than against the contract directly,
    because that function is what builds the `.subckt` line the benches
    simulate: if the drawing and the bench disagree about the boundary, the
    two are not the same block however much they agree with the contract.
    """
    header = HEADER.search(netlisted)
    assert header is not None, "the editor wrote no subcircuit header"
    assert header["name"] == analog.NAME
    drawn = [bit for port in header["ports"].split() for bit in port.split(BITS)]
    assert drawn == analog.terminals()


@needs_xschem
def test_the_comparator_is_wired_the_way_the_measurements_were_taken(netlisted):
    """Every terminal of the latch, against the one table that declares them.

    This is the check the sheet exists for. The latch's terminals are not
    symmetric -- `inp` carries Vcm and `inn` the top plate, which is what
    makes a high `cmp_out` mean the plate sat *below* Vcm -- so swapping the
    pair draws a sheet that looks right and inverts every decision the
    converter makes.
    """
    assert instance(netlisted, analog.COMPARATOR) == [
        analog.COMPARATOR_NETS[terminal] for terminal in strongarm.TERMINALS
    ]


@needs_xschem
def test_the_comparator_instance_is_a_subcircuit_call(netlisted):
    """Its name begins with the letter that makes the line one.

    The editor writes an instance's name verbatim and its own default is
    `x1`, so a comparator named `cmp` on the sheet netlists to `cmp vdd vss
    ...`, which is not a subcircuit call and not an element any simulator
    knows. It netlists without complaint, and the sheet looks correct.
    """
    name = next(
        text.split()[0]
        for text in netlisted.splitlines()
        if text.lower().startswith(analog.COMPARATOR.lower())
    )
    assert name.lower().startswith("x")
    assert name.lower() == analog.COMPARATOR.lower()


@needs_xschem
def test_the_comparator_on_the_sheet_is_the_comparators_own_sheet(netlisted):
    """The instance resolves to the latch, not to a symbol of the same shape.

    The sheet instantiates `strongarm.sym`, whose own sheet is the one held
    element by element to `strongarm.subckt`. So the latch inside this block
    is the measured circuit by construction, and that chain is what makes a
    drawing of the whole tile worth trusting rather than just worth reading.
    """
    assert f".subckt {strongarm.NAME} " in netlisted
    assert netlisted.count(f".subckt {strongarm.NAME} ") == 1


@needs_xschem
def test_the_array_is_wired_the_way_the_benches_are(netlisted):
    """Every plate of the array, against the order its block declares.

    There is no table of nets for this one, unlike the comparator's: the
    array's terminals carry the nets they are named after. So the check is
    against `analog.array_terminals()` itself, which is also what the array's
    symbol published its pin records in -- the two have to agree, because a
    SPICE instance wires by position, and a bottom plate wired to its
    neighbour's switch is a converter whose code is a permutation.
    """
    assert instance(netlisted, analog.ARRAY) == analog.array_terminals()


@needs_xschem
def test_the_array_on_the_sheet_is_the_arrays_own_sheet(netlisted):
    """The instance resolves to the drawing that is held to the netlist."""
    assert netlisted.count(f".subckt {analog.ARRAY_NAME} ") == 1


@needs_xschem
def test_nothing_floats_but_the_switches_that_are_not_drawn_yet(netlisted):
    """Every internal net reaches something at both ends, or is named here.

    This is the sheet's own electrical rule check, and the editor runs one
    too: it exits 10 when a net has nothing driving it, which is how the
    floating top plate below was found rather than reasoned about. The status
    is a flag and says only that one net floats somewhere, so the check is
    made here instead, where it can say which -- and where it tightens by
    itself, because a net stops being listed the moment something else on the
    sheet connects to it.

    What is left are the array's bottom plates, which reach their branch and
    nothing else until the sampling and conversion switches are drawn. The
    top plate is no longer among them: it was, until the array arrived on the
    sheet, which is this check tightening by itself as blocks are drawn. When
    the switches are drawn this set is empty and that is the assertion to
    leave behind.
    """
    once = {
        net
        for net, count in _connections(netlisted).items()
        if count == 1 and net not in _ports(netlisted)
    }
    assert once == set(analog.array_terminals()) - {analog.COMPARATOR_NETS["inn"]}


@needs_xschem
def test_every_terminal_the_block_declares_is_a_net_or_waits_for_its_block(netlisted):
    """A declared terminal that reaches nothing is named, so it cannot be a typo.

    A port whose net is spelled one way on the symbol and another on a wire
    netlists as two nets, and the sheet looks wired. So the ones nothing
    touches yet are listed by name: each belongs to a block that is not drawn,
    and a name appearing here that is not in that list is a mistake.
    """
    waiting = {"dac_b", "sample", "force_en", "force_hi", "vin"}
    connected = set(_connections(netlisted))
    loose = {port for port in _ports(netlisted) if port not in connected}
    assert {port.split("[")[0] for port in loose} == waiting


def test_the_sheet_is_committed():
    """A drawing nobody committed is a drawing the next checkout does not have."""
    tracked = subprocess.run(
        ["git", "ls-files", "xschem"],
        cwd=sheet.REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert f"xschem/{SHEET}" in tracked
