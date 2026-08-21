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

Only the first four are ours to pin. `make check-tools` enforces the three
tools it can interrogate; the image tag is enforced by `make container` being
the only documented way in.

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

## UNRESOLVED

**CI and the container use different Verilator builds.** CI compiles the pinned
version from source; the container ships whatever it was built with. Until those
agree, local and CI lint with different tools. Two ways out: run CI inside the
container, or accept that CI is the reference and the container is not.

**CI has no Yosys and no Verible.** `make lint` and `make format-check` invoke
both. They are currently skipped because `hdl/rtl/` holds no `.v` files, so CI
passes by accident; the first RTL file will break it. This has to be settled the
same way as the Verilator split, which is why `make check-tools` is not wired
into CI yet -- it would fail on the missing tools rather than on a real mismatch.

**RESOLVED: the three native pins now describe the image rather than wishing at
it.** `make tool-versions` reported yosys `0.67` (not `0.68`) and verible
`v0.0-4084-gf3e4d98b` (not `v0.0-4148-g1ea007ec`); `versions.env` was corrected
to match and `make check-tools` passes. This matters most for Verible, whose
formatting output changes between releases — a skew between container and CI
turns `make format-check` into a coin flip.

**`ruff` is pinned but not present.** `requirements.txt` pins `ruff==0.16.4`;
the image ships no ruff at all, so `make lint-py` and `make format-check` fail
inside the container. Pinned is not the same as installed. Same story for the
Python stack generally: the image ships pytest 9.1.1 and numpy 2.5.1 against
pinned 8.4.2 / 2.5.2. The pytest and cocotb pins match the TinyTapeout template
exactly (verified against `TinyTapeout/ttsky-verilog-template`) and must not be
bumped to chase the image. The fix is a thin `FROM hpretl/iic-osic-tools:<tag>`
layer that installs `requirements.txt`, not a change to the pins.
