"""The wiring between a compiled module and the circuit: pins placed by name
in the compiler's order, and controller ports matched to block terminals.

None of these compile anything; the closed-loop tests do.
"""

from __future__ import annotations

import pathlib

import pytest

import cosim
import loop
from interface import TO_ANALOG, TO_DIGITAL

#: A port order as the compiler writes it: single bits stored narrow come
#: before a bus stored wide, whatever order the source declared them in.
ORDER = """/* Generated code: do not edit. */
VL_DATA(8,sample_o,0,0)
VL_DATA(8,done_o,0,0)
VL_DATA(16,dac_b_o,3,0)
"""


def test_pins_follow_the_compilers_order_each_bus_from_its_top_bit():
    assert cosim.pins(ORDER) == [
        "sample_o",
        "done_o",
        "dac_b_o[3]",
        "dac_b_o[2]",
        "dac_b_o[1]",
        "dac_b_o[0]",
    ]


#: A compiled model's interface, as the compiler declares the ports.
INTERFACE = """class Vlng {
    VL_IN8(&clk_i,0,0);
    VL_OUT16(&dac_b_o,9,0);
    VL_OUT8(&done_o,0,0);
    VL_INOUT8(&pad_io,0,0);
"""


def test_the_order_files_keep_each_direction_in_the_compilers_order():
    files = cosim.order_files(INTERFACE)
    assert files["IN"] == "VL_DATA(8,clk_i,0,0)\n"
    assert files["OUT"] == "VL_DATA(16,dac_b_o,9,0)\nVL_DATA(8,done_o,0,0)\n"
    assert files["INOUT"] == "VL_DATA(8,pad_io,0,0)\n"


def test_every_pin_is_placed_by_name():
    library = cosim.Library(pathlib.Path("m.so"), ["a_i"], cosim.pins(ORDER))
    nets = {p: f"n_{i}" for i, p in enumerate(library.inputs + library.outputs)}
    instance = cosim.element("u", library, nets)[0]
    placed = instance.split("[")[2].split("]")[0].split()
    assert placed == [nets[p] for p in library.outputs]


def test_a_pin_without_a_net_is_refused():
    library = cosim.Library(pathlib.Path("m.so"), ["a_i"], ["b_o"])
    with pytest.raises(ValueError, match="b_o"):
        cosim.element("u", library, {"a_i": "a"})


@pytest.mark.parametrize(
    "port, wire",
    [("sample_o", "sample"), ("cmp_out_n_i", "cmp_out_n"), ("rst_ni", "rst_n"), ("clk", "clk")],
)
def test_a_port_is_its_wire_without_the_direction(port, wire):
    assert loop.wire(port) == wire


def test_the_boundary_names_are_what_the_controller_ports_reduce_to():
    """Each crossing wire, suffixed the way the controller names a port of
    that direction, comes back to the interface's own name."""
    for port in TO_ANALOG:
        assert loop.wire(f"{port.name}_o") == port.name
    for port in TO_DIGITAL:
        assert loop.wire(f"{port.name}_i") == port.name


def test_the_glue_starts_with_every_output_unreported():
    glue = f"int a;\n{cosim.REPORTED}\nint b;\n"
    patched = cosim.reporting_every_output(glue)
    assert cosim.REPORTED_UNKNOWN in patched
    assert patched.startswith("#include <cstring>")


def test_glue_without_the_record_is_refused():
    with pytest.raises(cosim.BuildError, match="previous_output"):
        cosim.reporting_every_output("int a;\n")
