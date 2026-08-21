# SAR-ASIC

Successive-approximation-register ADC: RTL, verification, system models, and
physical design in one repo.

## Layout

| Path | What's in it |
|---|---|
| `hdl/reference/` | Python golden models. Written **first**, before any RTL. |
| `hdl/verification/` | cocotb unit tests; SystemVerilog for larger benches |
| `hdl/rtl/` | Verilog-2005. Written **last**. |
| `model/` | Python system models (transfer curve, noise, DNL/INL) |
| `sim/` | Analog simulation decks (ngspice/xyce) |
| `xschem/` | Schematics and symbols |
| `layout/` | magic/klayout, GDS, DRC/LVS decks |
| `docs/` | Specs, architecture notes, measurements |
| `build/` | Generated output. Not committed. |

Coding rules live in [STYLE.md](STYLE.md). Read it before writing RTL.

Order of work is golden model -> tests -> RTL, and it is not optional.
STYLE.md section 1 explains why.

## Setup

Everything runs in the **IIC-OSIC-TOOLS** container. It ships the sky130A PDK
plus Verilator, cocotb, Yosys, xschem, ngspice, magic, KLayout, and netgen, so
there is no venv and no per-tool install. Pin it by dated tag, never `latest`:

```bash
docker run -it --rm -v "$PWD":/foss/designs hpretl/iic-osic-tools:2026.07 bash
```

Verilator has no native Windows build, so the container (or WSL2) is the only
place the suite actually runs. The Windows checkout is for editing and git.

If you want the exact pins from `requirements.txt` rather than whatever the
image ships, install them inside the container:

```bash
pip install -r requirements.txt
```

Native tool versions are recorded in [docs/tool-versions.md](docs/tool-versions.md).

## Running

`make` is the entry point. `make` alone prints the target list.

```bash
make model               # validate golden models -- do this first
make verify-unit         # cocotb unit tests
make verify              # model, then every verification level in order
make lint                # verilator + verible + yosys structural check + ruff
make format              # rewrite Verilog and Python in canonical style
make format-check        # read-only; what CI runs
make clean
```

Flags: `WAVES=1 make verify-unit` dumps FST into `build/sim/<top>/`.

There is no synthesis target. TinyTapeout's GDS action owns synthesis with
shuttle-pinned Yosys and LibreLane, so anything produced locally would be an
estimate that does not match what gets fabricated, and estimates do not get
targets. What *is* deterministic -- inferred latches, combinational loops,
multiple drivers, undriven nets -- is a `yosys check -assert` pass inside
`make lint-rtl`, where it belongs.

Testbenches use cocotb's Python runner rather than cocotb Makefiles, so `make`
is not required. Each `test_*.py` holds both its `@cocotb.test()` coroutines and
a pytest entry point that builds the DUT.

`hdl/verification/unit/smoke/` is a toolchain check, not part of the design —
delete it once real RTL has tests.
