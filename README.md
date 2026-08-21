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
docker run -it --rm -v "$PWD":/foss/designs hpretl/iic-osic-tools:2025.01 bash
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

```bash
python -m pytest                      # whole suite
python -m pytest -m unit              # one level: unit / integration / system
python -m pytest hdl/verification/unit/smoke -v
WAVES=1 python -m pytest              # dump FST into build/sim/<top>/
python scripts/lint_rtl.py            # verilator --lint-only -Wall over hdl/rtl
ruff check .                          # Python lint
```

Testbenches use cocotb's Python runner rather than cocotb Makefiles, so `make`
is not required. Each `test_*.py` holds both its `@cocotb.test()` coroutines and
a pytest entry point that builds the DUT.

`hdl/verification/unit/smoke/` is a toolchain check, not part of the design —
delete it once real RTL has tests.
