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

#: One port as the compiled model declares it: name, then the top and bottom
#: bit of its range.
PORT = re.compile(r"VL_DATA\(\d+,\s*(\w+),\s*(\d+),\s*(\d+)\)")

#: The files the build leaves the port order in, per direction.
ORDER_FILES = {"inputs": "inputs.h", "outputs": "outputs.h", "inouts": "inouts.h"}


class BuildError(RuntimeError):
    """A module that did not compile into a loadable element."""


def generator() -> pathlib.Path:
    """The script ngspice ships for compiling Verilog into an element.

    It is installed beside the simulator, in the shared directory of the same
    prefix the binary lives under.
    """
    found = shutil.which("ngspice")
    if found is None:
        return pathlib.Path("/nonexistent/vlnggen")
    prefix = pathlib.Path(found).resolve().parent.parent
    return prefix / "share" / "ngspice" / "scripts" / "vlnggen"


def available() -> bool:
    return shutil.which("verilator") is not None and generator().exists()


def pins(order: str) -> list[str]:
    """Every bit of every port, in the compiled model's order: ports as the
    order lists them, each bus from its top bit down."""
    out = []
    for name, msb, lsb in PORT.findall(order):
        msb, lsb = int(msb), int(lsb)
        if msb == lsb == 0:
            out.append(name)
        else:
            out.extend(f"{name}[{k}]" for k in range(msb, lsb - 1, -1))
    return out


@dataclass(frozen=True)
class Library:
    """A compiled module and the order its element takes its pins in."""

    path: pathlib.Path
    inputs: list[str]
    outputs: list[str]


def build(source: pathlib.Path, workdir: pathlib.Path, parameters: dict | None = None) -> Library:
    """Compile `source`'s top module, with `parameters` overridden, in `workdir`."""
    workdir.mkdir(parents=True, exist_ok=True)
    overrides = [f"-G{name}={value}" for name, value in (parameters or {}).items()]
    # Everything after the separator reaches the Verilog compiler; before it,
    # the simulator would take a parameter override for one of its own options.
    proc = subprocess.run(
        ["ngspice", "-b", str(generator()), "--", *overrides, str(source.resolve())],
        cwd=workdir,
        capture_output=True,
        text=True,
    )
    library = (workdir / f"{source.stem}.so").resolve()
    objects = workdir / f"{source.stem}_obj_dir"
    if not library.exists():
        raise BuildError(f"{source.name} did not compile\n{proc.stdout}\n{proc.stderr}")
    order = {k: pins((objects / f).read_text()) for k, f in ORDER_FILES.items()}
    if order["inouts"]:
        raise BuildError(f"{source.name}: bidirectional ports are not wired: {order['inouts']}")
    return Library(library, order["inputs"], order["outputs"])


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
