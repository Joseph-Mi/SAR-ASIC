# Pinned tool versions

Native tools are not pip packages; pin them by installing the tagged release or
by using a dated IIC-OSIC-TOOLS image. Verified 2026-08-20.

| Tool | Version | Role | Source |
|---|---|---|---|
| Verilator | 5.050 | RTL simulation + lint | github.com/verilator/verilator tag `v5.050` |
| Verible | v0.0-4148-g1ea007ec | Verilog format + style lint | github.com/chipsalliance/verible |
| Icarus Verilog | per OSS CAD Suite | gate-level sim only (see note) | TinyTapeout CI |
| Yosys | 0.68 | Synthesis | github.com/YosysHQ/yosys tag `v0.68` |
| LibreLane | per shuttle | RTL2GDS flow driver (invokes Yosys + OpenROAD) | pinned by the TT GDS action |
| OpenROAD | per LibreLane | Place & route | pinned by LibreLane |
| Magic / Netgen / KLayout | per IIC-OSIC-TOOLS | DRC / LVS / layout | IIC-OSIC-TOOLS `2026.07` |
| ngspice / xschem | per IIC-OSIC-TOOLS | Analog simulation / schematics | IIC-OSIC-TOOLS `2026.07` |

| Python | Version |
|---|---|
| cocotb | 2.0.1 (matches TinyTapeout) |
| pytest | 8.4.2 (matches TinyTapeout) |
| numpy | 2.5.2 |
| ruff | 0.16.4 |

## Notes

**You do not pick the Yosys/LibreLane/OpenROAD versions.** The TinyTapeout GDS
GitHub Action pins them per shuttle. Bumping them locally does not change what
gets fabricated — it only makes your local result disagree with the shuttle's.
Treat the shuttle as the source of truth.

**Verilator cannot replace Icarus for gate-level simulation.** It supports UDP
tables, but ignores all `specify` blocks and timing checks, and does not support
3-state or MOS gate primitives. TinyTapeout's `GATES=yes` flow is written for
Icarus and runs on Icarus in CI regardless of local preference. Verilator is the
right tool for RTL simulation and lint; Icarus is the tool for the post-synthesis
netlist check.

**IIC-OSIC-TOOLS** is Ubuntu 24.04-based and ships sky130A, gf180mcuD, and
ihp-sg13g2 PDKs plus Verilator, Yosys, LibreLane, cocotb, xschem, magic, KLayout,
ngspice, OpenROAD, and netgen. Pin it by image tag (`2026.07`), not `latest`.

## UNRESOLVED: these pins are not enforced, and two of them conflict

`make check-tools` prints what is actually installed. Nothing compares that to
the table above yet, so every number here is aspirational until it does.

Two known conflicts, to settle once the container is running:

1. **Verilator.** CI builds `v5.050` from source. The IIC-OSIC-TOOLS `2026.07`
   image ships whatever Verilator it was built with, which is almost certainly
   a different version. Local and CI therefore lint with different tools. Either
   CI adopts the container's version, or the container is not the reference.

2. **Verible.** `make format-check` fails CI when formatting differs. Verible's
   output changes between releases, so a version skew between your container and
   CI turns `format-check` into a coin flip. This must be pinned to whatever the
   image ships, not to upstream latest.

Run `make check-tools` in the container and replace the guesses with real
numbers.
