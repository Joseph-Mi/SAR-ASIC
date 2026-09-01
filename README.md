# SAR-ASIC

Successive-approximation-register ADC: RTL, verification, system models, and
physical design in one repo.

## Layout

Deliberately not documented here. Paths change, and a layout table is the
first thing to go stale without anyone noticing. Read the tree.

Coding rules live in [STYLE.md](STYLE.md). Read it before writing RTL.

Order of work is golden model -> tests -> RTL, and it is not optional.
STYLE.md's "Order of work" explains why.

## Setup

Everything runs in the **IIC-OSIC-TOOLS** container, pinned by dated tag in
`versions.env` — never `latest`. It ships the sky130A PDK plus Verilator,
cocotb, Yosys, xschem, ngspice, magic, KLayout, and netgen, so there is no venv
and no per-tool install.

On a machine that already has Docker, `make`, and git:

```bash
make designinit   # point the container's startup hook at pdk.env (once)
make doctor       # is this host ready? names what is missing if not
make container    # clone helpers at the pinned tag, then start the container
make shell        # bash inside it, at this design
```

`pdk.env` holds the sky130A selection and is the source of truth for it; the
image otherwise defaults to a different PDK. See
[docs/environment.md](docs/environment.md#pdk-selection).

`make container` clones `iic-osic-tools` beside this repo at the pinned tag if it
is missing, and verifies the tag if it is already there, so the helper scripts
and the image cannot drift apart unnoticed. Do not clone it by hand. That
checkout is read-only to us — make will refuse to move it and will print the
command instead.

From a bare machine, the one-time host bootstrap — WSL2, Docker Engine, `make` —
is in **[docs/environment.md](docs/environment.md)**. Those are the only steps
that are not a make target, because they need `sudo` and a restart.

Verilator has no native Windows build, so the container (or WSL2) is the only
place the suite actually runs. The Windows checkout is for editing and git.

If you want the exact pins from `requirements.txt` rather than whatever the
image ships, install them inside the container:

```bash
pip install -r requirements.txt
```

Native tool versions are recorded in [docs/tool-versions.md](docs/tool-versions.md);
`make check-tools` enforces them.

The analog side of the workflow — reaching the noVNC desktop, xschem, ngspice,
and the disposable experiments under `sandbox/` — is in
[docs/sandbox.md](docs/sandbox.md). None of it is a make target.

## Running

`make` is the entry point. `make` alone prints the target list.

```bash
make container           # start the container; make shell to get into it
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

`hdl/verification/unit/tb_smoke/` is a toolchain check, not part of the design —
delete it once real RTL has tests.
