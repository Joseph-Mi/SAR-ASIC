"""Verilog inside an ngspice run: the RTL compiled into one circuit element.

Contract: a compiled module is wired by port name, never by position. The
element takes its pins in the order the compiled model stores its ports, and
that order is the compiler's -- ports grouped by how wide a word holds them,
so it changes when a bus is resized. `build` reads the order back out of the
compiled model every time, and `element` places each net by name against it.

The bridges are the boundary a real chip has at the same place: a digital
output is a driver pulling a wire to one rail or the other, and a digital
input is a gate that reads a wire as one above its switching point and zero
below it.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
from dataclasses import dataclass

#: One port as the compiled model's interface declares it: direction, the
#: width of the word that stores it, name, then its top and bottom bit.
PORT = re.compile(r"VL_(INOUT|IN|OUT)(\d*)\(&(\w+),\s*(\d+),\s*(\d+)")

#: One port as the order files list it: name, top bit, bottom bit.
ORDERED = re.compile(r"VL_DATA\(\d+,\s*(\w+),\s*(\d+),\s*(\d+)\)")

#: The order files the element's glue code includes, per direction.
ORDER_FILES = {"IN": "inputs.h", "OUT": "outputs.h", "INOUT": "inouts.h"}

#: The name the compiled model's classes and files are given. The glue code
#: expects this one.
PREFIX = "Vlng"


#: Where the glue declares what it last reported on each output, and what it
#: is given in its place. The simulator side compares every reported change
#: against its own record of the last value it drove, and in some releases
#: that record starts as uninitialised memory: a first change that happens to
#: match the garbage is taken for no change and never reaches the wire. The
#: glue's own record starts at zero, so it reports nothing until an output
#: moves. Starting it at a value no bit can have makes its first scan report
#: every output, which sets the simulator's record before anything moves.
REPORTED = "static unsigned char previous_output[outs + inouts];"
REPORTED_UNKNOWN = (
    REPORTED
    + "\nstatic const bool reported_unknown ="
    + " (std::memset(previous_output, 2, sizeof previous_output), true);"
)


class BuildError(RuntimeError):
    """A module that did not compile into a loadable element."""


def glue() -> pathlib.Path:
    """The C++ that turns a compiled Verilog model into an ngspice element.

    ngspice installs it beside the simulator, in the shared directory of the
    same prefix the binary lives under.
    """
    found = shutil.which("ngspice")
    if found is None:
        return pathlib.Path("/nonexistent")
    prefix = pathlib.Path(found).resolve().parent.parent
    return prefix / "share" / "ngspice" / "scripts" / "src"


def available() -> bool:
    return shutil.which("verilator") is not None and (glue() / "verilator_shim.cpp").exists()


def pins(order: str) -> list[str]:
    """Every bit of every port, in the compiled model's order: ports as the
    order lists them, each bus from its top bit down."""
    out = []
    for name, msb, lsb in ORDERED.findall(order):
        msb, lsb = int(msb), int(lsb)
        if msb == lsb == 0:
            out.append(name)
        else:
            out.extend(f"{name}[{k}]" for k in range(msb, lsb - 1, -1))
    return out


def order_files(interface: str) -> dict[str, str]:
    """The order files' contents, from the compiled model's interface."""
    files = {direction: "" for direction in ORDER_FILES}
    for direction, width, name, msb, lsb in PORT.findall(interface):
        files[direction] += f"VL_DATA({width or 8},{name},{msb},{lsb})\n"
    return files


@dataclass(frozen=True)
class Library:
    """A compiled module and the order its element takes its pins in."""

    path: pathlib.Path
    inputs: list[str]
    outputs: list[str]


def reporting_every_output(glue_source: str) -> str:
    """The glue, changed so its first scan reports every output."""
    if REPORTED not in glue_source:
        raise BuildError(f"the glue no longer declares: {REPORTED}")
    return "#include <cstring>\n" + glue_source.replace(REPORTED, REPORTED_UNKNOWN)


def _run(command: list[str], workdir: pathlib.Path, what: str) -> None:
    proc = subprocess.run(command, cwd=workdir, capture_output=True, text=True)
    if proc.returncode:
        raise BuildError(f"{what} failed\n{' '.join(command)}\n{proc.stdout}\n{proc.stderr}")


def build(source: pathlib.Path, workdir: pathlib.Path, parameters: dict | None = None) -> Library:
    """Compile `source`'s top module, with `parameters` overridden, in `workdir`.

    The steps are those of the compile script ngspice ships, run directly:
    the script goes through the simulator's command interpreter, whose
    handling of the compiler's arguments differs between releases and setups.
    """
    workdir = workdir.resolve()
    objects = workdir / f"{source.stem}_obj_dir"
    library = workdir / f"{source.stem}.so"
    shutil.rmtree(objects, ignore_errors=True)
    library.unlink(missing_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)

    src = glue()
    verilator = ["verilator", "--Mdir", str(objects), "--prefix", PREFIX, "--CFLAGS", "-fpic"]
    design = [f"-G{name}={value}" for name, value in (parameters or {}).items()]
    design.append(str(source.resolve()))

    _run([*verilator, "--cc", *design], workdir, "translating the Verilog")
    patched = objects / "verilator_shim.cpp"
    patched.write_text(reporting_every_output((src / "verilator_shim.cpp").read_text()))
    files = order_files((objects / f"{PREFIX}.h").read_text())
    for direction, name in ORDER_FILES.items():
        (objects / name).write_text(files[direction])
    order = {direction: pins(text) for direction, text in files.items()}
    if order["INOUT"]:
        raise BuildError(f"{source.name}: bidirectional ports are not wired: {order['INOUT']}")

    _run(
        [
            *verilator,
            "--CFLAGS",
            f"-I{src}",
            "--cc",
            "--build",
            "--exe",
            str(src / "verilator_main.cpp"),
            str(patched),
            *design,
        ],
        workdir,
        "compiling the model",
    )
    runtime = sorted(str(p) for p in objects.glob("verilated*.o"))
    _run(
        [
            "g++",
            "--shared",
            str(objects / "verilator_shim.o"),
            *runtime,
            str(objects / f"{PREFIX}__ALL.a"),
            "-pthread",
            "-lpthread",
            "-o",
            str(library),
        ],
        workdir,
        "linking the element",
    )
    return Library(library, order["IN"], order["OUT"])


def element(name: str, library: Library, nets: dict[str, str]) -> list[str]:
    """The module as one element, each pin on the digital net `nets` names.

    Every pin has to be named: a pin left off would take whatever net fell
    into its position.
    """
    missing = [p for p in library.inputs + library.outputs if p not in nets]
    if missing:
        raise ValueError(f"{name}: no net for {missing}")
    ins = " ".join(nets[p] for p in library.inputs)
    outs = " ".join(nets[p] for p in library.outputs)
    return [
        f"A{name} [{ins}] [{outs}] null {name}_model",
        f'.model {name}_model d_cosim simulation="{library.path}"',
    ]


def reads(name: str, wires: list[str], digital: list[str], threshold: float) -> list[str]:
    """Gates reading `wires` onto `digital`, one above `threshold`."""
    return [
        f"A{name} [{' '.join(wires)}] [{' '.join(digital)}] {name}_model",
        f".model {name}_model adc_bridge in_low={threshold:.9g} in_high={threshold:.9g}",
    ]


def drives(name: str, digital: list[str], wires: list[str], high: float, edge: float) -> list[str]:
    """Drivers pulling `wires` to ground or `high` as `digital` says, each
    transition taking `edge`."""
    return [
        f"A{name} [{' '.join(digital)}] [{' '.join(wires)}] {name}_model",
        f".model {name}_model dac_bridge out_low=0 out_high={high:.9g} "
        f"t_rise={edge:.9g} t_fall={edge:.9g}",
    ]
