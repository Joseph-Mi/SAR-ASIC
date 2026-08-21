# 8-bit SAR ADC (Tiny Tapeout, Sky130)

## What we're building

A mixed-signal 8-bit charge-redistribution SAR ADC on a Tiny Tapeout analog tile
(2x2, fallback 1x2). A binary-weighted capacitor array serves as both
sample-and-hold and internal DAC; a StrongARM latch comparator makes bit
decisions; a Verilog FSM runs the binary search and hands results out over the
digital pins.

Analog half is hand-drawn custom layout. Digital half goes through LibreLane.
Both live in the same tile, and **we own the merged GDS** — TT hardens nothing on
our behalf for an analog submission. The flow is:

```
hdl/      --LibreLane-->  macro.gds + macro.lef  --+
                                                    +--> tile GDS --> DRC/LVS --> submit
xschem/   --Magic-->      analog GDS             --+
```

Not targeting a near-term shuttle. A first custom analog layout on a two-week
deadline is how you miss a submission.

---

## Design decisions

**DD-01 — RTL is pure Verilog-2005. No SystemVerilog in the RTL tree.**
The TT-mandated `tt_um_*` top must be Verilog-2005 regardless; a single dialect
avoids a synthesis-support boundary running through the middle of the digital
half. Consequence: no `always_comb` latch detection, so we compensate with
default-assignment style and `yosys check -assert` in CI.

**DD-02 — Container tag is pinned, never `:latest`.**
Image: `hpretl/iic-osic-tools:2026.07`. The `iic-osic-tools` helper repo is
checked out at tag `2026.07` to match — the start scripts and the image are
versioned together. Bump both at once, deliberately, and re-run the M0 smoke
test after any bump. The devcontainer image is a separate tag namespace; pin it
independently.

**DD-03 — Vref gets its own analog pin, separate from VDD.**
The array pulls charge from Vref on every bit trial and TT analog pins have real
series R (mux switch + bond wire + trace). Sharing with VDD means Vref hasn't
recovered when the comparator fires.

**DD-04 — Comparator interface carries both outputs (`cmp_out`, `cmp_out_n`).**
Their being equal is a free metastability flag.

**DD-05 — Host OS is not a project dependency. No EDA tools installed outside
the container.**
Course docs warn against Ubuntu 24; that applies to the manual-install path, not
to us. The WSL2 distro only runs `docker`, `git`, and bash — everything else
lives in the pinned image (itself Ubuntu 24.04). We ended up on Ubuntu 26.04
"resolute" and it is irrelevant.

**DD-06 — Docker Engine installed natively inside WSL2 Ubuntu, not Docker
Desktop integration.**
Docker Desktop's WSL shim failed to relocate its proxy binary into 26.04
(`install: No such file or directory` across `/run`, `/tmp`, `/dev/shm`). Native
Engine removes the shim entirely, drops a filesystem hop on every container I/O,
and decouples the daemon from Docker Desktop's update cycle. Requires
`systemd=true` in `/etc/wsl.conf` (WSL default now) and the apt repo pinned to
`noble` — Docker publishes no `resolute` directory. Revisit that pin when they do.

**DD-07 — All work lives on ext4, never `/mnt/c`.**
drvfs adds per-syscall latency across the VM boundary (brutal for the
hundred-thousand-file LibreLane runs), mishandles the symlink forest `open_pdks`
builds under `sky130A/libs.tech/`, and forces uid/gid regardless of what the
container start scripts pass. Repo lives at `~/github/SAR-ASIC`. Note: files
copied in from drvfs arrive mode 777 and show up as spurious git mode changes —
normalize to 644/755 before committing.

---

## Environment

Everything runs inside **IIC-OSIC-TOOLS**
(https://github.com/iic-jku/iic-osic-tools). We do not install EDA tools on the
host. Ever.

Layout:

| Path | What |
|---|---|
| `~/github/SAR-ASIC` | this repo |
| `~/github/iic-osic-tools` | helper scripts only, never committed, never edited |
| `/foss/designs/SAR-ASIC` | the same repo, seen from inside the container |

`DESIGNS=$HOME/github` is bind-mounted to `/foss/designs`. Host and container see
the same bytes — edit on the host, run tools in the container, no syncing.

Three doors into the container:

| Mode | Use for |
|---|---|
| `./start_vnc.sh` -> `http://localhost` (pw `abc123`) | Xschem, Magic, KLayout, GTKWave — anything GUI |
| `docker exec -it iic-osic-tools_xvnc_uid_$(id -u) bash` | CLI work in the *same running* container |
| `.devcontainer/` in VS Code | RTL, cocotb, Python model, git |

XQuartz is macOS-only and irrelevant here; VNC mode needs no X server on any
platform.

`.designinit` in the designs dir is sourced at container start — put project env
vars there rather than retyping them.

**Never** `pip install` or `apt install` a tool into a running container and rely
on it. It vanishes on restart and isn't in anyone else's environment. If we
genuinely need something absent, add a thin `FROM hpretl/iic-osic-tools:2026.07`
layer and commit it. Check the tool list first — `gdsfactory`, `gdspy`, `pygmid`,
`cocotb`, `pyuvm`, `spicebind`, `cace`, `chipify` are all already in there.

---

## Toolchain

| Layer | Tool |
|---|---|
| Schematic capture | Xschem |
| Analog simulation | ngspice (`spicebind` for mixed-signal co-sim) |
| Mismatch / sweeps / yield | `chipify` (new in 2026.07 — wraps xschem+ngspice) |
| Device sizing | `pygmid` (gm/Id) |
| Layout | Magic |
| Array generation | `gdsfactory` / `gdspy` — the 256-cell array is scripted, not hand-placed |
| DRC / LVS / PEX | `sak-drc.sh`, `sak-lvs.sh`, `sak-pex.sh` (reworked in 2026.07) |
| Synthesis / P&R | LibreLane (yosys + OpenROAD) |
| Digital sim | Verilator (fast), iverilog (fallback) |
| Waveforms | GTKWave, surfer |
| Verification | cocotb; pyuvm if the testbench wants agents/scoreboards |
| Lint | `verilator --lint-only -Wall`, `verible-verilog-lint`, `yosys check -assert` |
| Format | `verible-verilog-format` |
| PDK | sky130A |

Two things that are easy to get wrong:

- **Verilator lints, it does not format.** Formatting is `verible-verilog-format`.
- **SystemVerilog OOP testbenches do not work in the open-source flow.** Classes,
  constrained random, mailboxes, and UVM need a commercial simulator. Verilator
  and iverilog don't implement them. The equivalent here is **pyuvm** — UVM
  structure in Python on cocotb. So: cocotb for everything, pyuvm when the
  testbench wants drivers/monitors/scoreboards rather than a flat coroutine.

---

## Verification

- cocotb + Verilator on the SAR FSM, including deliberately hostile comparator
  responses (all-ones, all-zeros, random) — the FSM must still terminate in N+2.
- Every combinational `always @(*)` block default-assigns all outputs at the top,
  then overrides. Latch inference becomes structurally impossible.
- `yosys -p "read_verilog ...; hierarchy -top sar_top; proc; check -assert"` in
  CI. Fails on inferred latches and undriven wires. Runs in seconds.
- Python Monte Carlo model runs in CI as a regression, so changing the unit cap
  size shows up as a diff in DNL/INL numbers rather than a vibe.
- CI runs the same pinned container image as local dev. Consider mirroring the
  tag to GHCR if Actions pull times get annoying — the image is ~20 GB.

---

## Milestones

- **M0** — Container running, `tt06-analog-relax-osc` LVS test clean, tag recorded.
- **M1** — Python Monte Carlo model: unit cap size, 8 vs 10 bit, MiM vs VPP decided.
- **M2** — Interface frozen: 11 wires, Xschem `.sym` committed, ports locked.
- **M3** — Architecture converges in ngspice with ideal switches and comparator.
- **M4** — Digital half: FSM, SPI, clock divider, all six DFT modes, cocotb green.
- **M5** — StrongARM sized, Monte Carlo offset known, preamp decision made.
- **M6** — Cap array laid out (scripted), DRC clean.
- **M7** — Comparator laid out, DRC/LVS clean.
- **M8** — Digital hardened by LibreLane, macro + LEF fit the floorplan budget.
- **M9** — Merged tile GDS, DRC/LVS against TT template, `info.yaml`, docs.

M4 has no analog dependency and runs fully parallel from M2 onward.

**Floorplan budget is decided at M2, not M8.** Fix how many um of tile height the
digital macro gets, over-budget it deliberately, and give LibreLane a hard
`DIE_AREA`. Finding out at M8 that the macro doesn't fit means redoing layout
under deadline.

---

## The interface (freeze at M2)

Digital -> analog:

| Wire | Meaning |
|---|---|
| `dac_b[7:0]` | bottom-plate select per binary branch (VREF or GND) |
| `sample` | sampling phase, drives bottom-plate sampling switches |
| `cmp_clk` | StrongARM strobe (rising = evaluate, low = precharge) |

Analog -> digital:

| Wire | Meaning |
|---|---|
| `cmp_out`, `cmp_out_n` | differential latch outputs; equal = metastable |

Eleven wires. Freeze the `.sym` around that and the two halves decouple.

---

## Key numbers

Worst-case DNL is at the MSB transition (code 127->128), where every LSB cap
switches off and the MSB switches on — no shared devices, mismatch maximally
exposed:

    sigma_DNL_MSB = sqrt(2^N - 1) * (sigma_u / C_u)   [LSB]

N=8 gives sqrt(255) ~ 16x amplification. Wanting 3-sigma < 1 LSB means
sigma_u/C_u < ~2%, which is loose. N=10 gives ~32x *and* quarters the LSB — that
is why 10 bits is much harder, and the model should confirm it before we commit.

kT/C is a non-issue at 8 bits: sigma_noise < LSB/6 ~ 1.2 mV needs only
C_total > ~3 fF. Matching and manufacturability set the unit cap, not noise.

---

## Design for test (non-negotiable)

Lives entirely in the digital half, costs near-zero area:

1. Raw DAC mode — drive cap array bottom plates from a register, bypass the FSM.
   Characterizes the array independently of the comparator. Highest value item.
2. Comparator output exposed on `uo_out`.
3. SAR state / bit index exposed.
4. Internal forced-input mode — short Vin to Vref and to GND on-chip.
5. Programmable conversion clock.
6. Single-shot and continuous modes with a ready flag.

---

## Repo conventions

- Xschem `.sch`/`.sym` and Magic `.mag` are text — diff and merge normally.
- GDS is binary — gitignored and regenerated. LFS only for final submission.
- `.gitignore` must cover `runs/`, `*.raw`, ngspice output dirs. Otherwise the
  first commit is a gigabyte of waveforms.
- Treat `.sym` like a C header: freeze the interface early, parallelize after.

