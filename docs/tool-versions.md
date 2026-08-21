# Pinned tool versions

Native tools are not pip packages; pin them by installing the tagged release or
by using a dated IIC-OSIC-TOOLS image. Verified 2026-08-20.

| Tool | Version | Role | Source |
|---|---|---|---|
| Verilator | 5.050 | RTL simulation + lint | github.com/verilator/verilator tag `v5.050` |
| Icarus Verilog | per OSS CAD Suite | gate-level sim only (see note) | TinyTapeout CI |
| Yosys | 0.68 | Synthesis | github.com/YosysHQ/yosys tag `v0.68` |
| LibreLane | per shuttle | RTL2GDS flow driver (invokes Yosys + OpenROAD) | pinned by the TT GDS action |
| OpenROAD | per LibreLane | Place & route | pinned by LibreLane |
| Magic / Netgen / KLayout | per IIC-OSIC-TOOLS | DRC / LVS / layout | IIC-OSIC-TOOLS image tag |
| ngspice / xschem | per IIC-OSIC-TOOLS | Analog simulation / schematics | IIC-OSIC-TOOLS image tag |

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
ngspice, OpenROAD, and netgen. Pin it by image tag (e.g. `2025.01`), not `latest`.
