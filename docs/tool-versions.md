# Tool versions

Pinned native tool versions live in **[`versions.env`](../versions.env)**, which
the Makefile includes and CI sources. Python package versions live in
**`requirements.txt`**, enforced by pip at install time.

No version number is repeated in this file. It holds only the reasoning and the
tools whose versions this repo does *not* choose.

```
make tool-versions    # print what is installed
make check-tools      # fail if it disagrees with versions.env
make tool-manifest    # record the FULL inventory into tool-manifest.txt
```

`versions.env` holds the few tools we choose. [`tool-manifest.txt`](tool-manifest.txt)
records everything we got, including the dozen pinned transitively by the image
tag. It is generated, committed, and never hand-edited, so a version change
arrives as a reviewable diff instead of a surprise. Nothing runs it for you —
regenerating and bumping stay deliberate.

## Where each tool's version comes from

| Tool | Version source | Role |
|---|---|---|
| Verilator | `versions.env` | RTL simulation and lint |
| Yosys | `versions.env` | Structural check in `make lint-rtl` |
| Verible | `versions.env` | Verilog format and style lint |
| IIC-OSIC-TOOLS image | `versions.env` | Supplies everything below |
| Icarus Verilog | the image | Gate-level sim, run by TinyTapeout CI |
| LibreLane | the shuttle | RTL2GDS flow driver |
| OpenROAD | LibreLane | Place and route |
| Magic / Netgen / KLayout | the image | DRC / LVS / layout |
| ngspice / xschem | the image | Analog simulation and schematics |

Only the first four are ours to pin. `make check-tools` enforces the three tools
it can interrogate, locally and in CI; the image tag is enforced by
`make container` being the only documented way in.

## Notes

**You do not pick the Yosys, LibreLane, or OpenROAD versions that matter.** The
`versions.env` Yosys pin governs the local structural lint only. TinyTapeout's
GDS action pins its own Yosys and LibreLane per shuttle, and that is what gets
fabricated. Bumping locally does not change the silicon; it only makes your
result disagree with the shuttle's. Treat the shuttle as authoritative.

**Verilator cannot replace Icarus for gate-level simulation.** It supports UDP
tables, but ignores all `specify` blocks and timing checks, and does not support
3-state or MOS gate primitives. TinyTapeout's `GATES=yes` flow is written for
Icarus and runs on Icarus in CI regardless of local preference. Verilator is the
right tool for RTL simulation and lint; Icarus is the tool for the post-synthesis
netlist check.

**Verible's version decides what `make format-check` accepts.** Its formatting
output changes between releases, so a skew between the container and CI turns
that target into a coin flip. The pin is not cosmetic, and it is pinned to what
the image ships rather than to upstream latest, because the image is the one
version we cannot change.

## UNRESOLVED

**CI and the container use different Verilator builds.** CI compiles the pinned
version from source; the container ships whatever it was built with. Until those
agree, local and CI lint with different tools. Two ways out: run CI inside the
container, or accept that CI is the reference and the container is not.

**The container does not honor `requirements.txt`.** The pins are correct --
`pytest` and `cocotb` match the TinyTapeout template exactly, which is the
constraint that matters -- but the image ships different versions of the Python
stack and no `ruff` at all, so `make lint-py` and `make format-check` fail inside
the container. Pinned is not the same as installed. See
[`tool-manifest.txt`](tool-manifest.txt) for what the image actually ships.

The fix is a thin `FROM hpretl/iic-osic-tools:<tag>` layer that installs
`requirements.txt`, not a change to the pins. Bumping the pins to match the image
would break the TinyTapeout agreement, which is the wrong trade.
