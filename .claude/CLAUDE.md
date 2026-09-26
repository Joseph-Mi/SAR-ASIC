# SAR ADC (Tiny Tapeout, Sky130)

## What we're building

A mixed-signal charge-redistribution SAR ADC on a Tiny Tapeout analog tile
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
test after any bump. `make container` enforces the match: it checks the helper
repo out at `OSIC_TOOLS_TAG` before starting the image at that same tag. No
devcontainer — VNC plus VS Code over WSL covers it, and a devcontainer image is
a separate tag namespace that would be a third thing to keep in sync.

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

**DD-08 — The top plate is referenced to Vcm, not ground.**
The reference cancels out of every decision, so both choices convert the same
codes; they differ in where the node travels. The widest swing is the first
trial, +-VREF/2 around the sampling reference. Referenced to ground that is
-VREF/2..+VREF/2: switch junctions on the node forward-bias below roughly
-0.5 V and leak the held charge, and an NMOS-input StrongARM cannot resolve
near 0 V. Referenced to Vcm (`VCM_FRACTION` of VREF in `sar.py`) it is
0..VREF, inside the rails, with the same ratios, so every matching and yield
result carries over. Contract this creates: leaving the sample phase, bottom
plates go straight to the first trial word -- never through all-ground, which
would drop the node to Vcm - Vin, down to -VREF/2 even with Vcm. The
comparator compares the top plate against Vcm. In M3 Vcm is an ideal source;
whether silicon gets it from its own pin or an on-chip divider is an open
interface question, answered by M3's settling runs, not decided here.

**DD-09 — Circuit simulation harness lives in `sim/`, not `sandbox/`.**
Design code may not import from the sandbox, and M3's harness is design code:
its pass criterion is the golden model's decisions. So the deck runner moved to
`sim/`, the sandbox imports it from there (never the reverse), and `make
verify-analog` runs `sim/`'s tests. Tests needing the simulator skip where
ngspice is absent -- CI has none -- so the parser and generators stay checked
everywhere and the circuit runs are checked in the container.

---

## Environment

Everything runs inside **IIC-OSIC-TOOLS**
(https://github.com/iic-jku/iic-osic-tools). We do not install EDA tools on the
host. Ever.

Layout:

| Path | What |
|---|---|
| `~/github/SAR-ASIC` | this repo |
| `~/github/iic-osic-tools` | helper scripts, cloned by `make osic-tools` at the pinned tag. Never committed, never edited — we only ever read them and check out the tag |
| `/foss/designs/SAR-ASIC` | the same repo, seen from inside the container |

`DESIGNS=$HOME/github` is bind-mounted to `/foss/designs`. Host and container see
the same bytes — edit on the host, run tools in the container, no syncing.

Two doors into the container, both opened by make from the host:

| Command | Use for |
|---|---|
| `make container` -> `http://localhost` (pw `abc123`) | Xschem, Magic, KLayout, GTKWave — anything GUI |
| `make shell` | CLI work in the *same running* container |

`make shell` is exactly `docker exec -it iic-osic-tools_xvnc_uid_$(id -u) bash`
with `-w /foss/designs/SAR-ASIC`. Use the raw form when make is unavailable or
when a second terminal is wanted. Editing is done on the host (VS Code over WSL)
against `~/github/SAR-ASIC` — same bytes, no third environment.

`make container` is the only supported way in. A hand-rolled `docker run`
misses the uid/gid mapping the start scripts pass and leaves root-owned files
in the designs tree.

XQuartz is macOS-only and irrelevant here; VNC mode needs no X server on any
platform.

**PDK selection is not optional and does not live in the designs dir.** The
image defaults to `PDK=ihp-sg13g2` and derives `PDKPATH`, `STD_CELL_LIBRARY`,
`SPICE_USERINIT_DIR`, and `KLAYOUT_PATH` from it *before* sourcing anything of
ours — so setting `PDK` alone leaves four variables pointing into the IHP tree,
and magic, ngspice, and KLayout load the wrong technology with no error.

All five live in `pdk.env`, in this repo, under git. `$DESIGNS/.designinit` is
reduced to a three-line shim that sources it, written by `make designinit` and
never edited again. Project env goes in `pdk.env`, never in `.designinit`: the
designs dir is outside every repo, shared with sibling projects, and invisible
to CI and to anyone who clones. `make doctor` refuses to start the container if
the shim is missing.

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
  responses (all-ones, all-zeros, random) — the FSM must still terminate, in the
  bound the protocol model declares. A bit trial is two cycles: the comparator
  precharges while the array settles and evaluates on the strobe, so a strobe
  held across trials would decide once and repeat itself.
- Every combinational `always @(*)` block default-assigns all outputs at the top,
  then overrides. Latch inference becomes structurally impossible.
- `yosys -p "read_verilog ...; hierarchy -top sar_top; proc; check -assert"` in
  CI. Fails on inferred latches and undriven wires. Runs in seconds.
- Python Monte Carlo model runs in CI as a regression, so changing the unit cap
  size shows up as a diff in DNL/INL numbers rather than a vibe.
- CI runs the same pinned container image as local dev. Consider mirroring the
  tag to GHCR if Actions pull times get annoying — the image is ~20 GB.

### Understanding the digital half beyond simulation

Simulation shows it does the right thing for the inputs tried. The rest:

| Question | Tool | What it says |
|---|---|---|
| Right for *every* input? | SymbiYosys (`sby`) formal — check it is in the image | proves properties, e.g. "DONE is always reached within the protocol's cycle bound"; the hostile-comparator tests only sample this |
| What hardware was built? | `yosys stat` / `show` | cell and flop counts, the actual gates |
| Limiting path | OpenSTA (inside LibreLane) | critical path = slowest flop-to-flop chain; its slack sets the max clock |
| Current-limited nets | STA max-slew / max-cap checks | a small gate on a big load charges slowly (I = C dV/dt) |
| Unbalanced clock network | CTS report | skew between flops -> hold violations |
| Supply current | OpenROAD IR-drop | whether the power stripes droop under switching |

**The imbalance that matters most is at the boundary.** `dac_b[MSB]` drives half
the array's bottom plates and `dac_b[0]` drives one unit: a 2^(N-1):1 load
spread across one bus. The macro drives one small inverter per bit; the analog
side owns per-branch tapered buffer chains sized to each branch's load.
LibreLane's SDC must `set_load` those outputs, or STA reports slack that does
not exist.

Digital area check (floorplan assumption #1): rough RTL for SPI, register file,
divider (right flop count, not right behaviour), then `yosys stat -liberty` on
the whole tree under the `tt_um_*` top. Bottom-up flop count says ~3x the FSM.
Make the divider a clock-enable tick, not a divided clock — one clock domain.

### Parasitics and junctions — three ways to get a number

1. **Hand**: MATH.md formulas + PDK params (its grep). Says whether to worry.
2. **Simulate**: DC-bias the node, 1 V AC source, C = |I|/(2 pi f V) — the
   `sandbox/cap-matching/` trick. Sweep the DC bias to get C(V) directly, with
   every junction the models carry. `.op` also prints per-device caps
   (`@m.xm1.msky130_fd_pr__nfet_01v8[cgd]`).
3. **Extract**: Magic `extract` -> `ext2spice` (`sak-pex.sh`). 2 vs 3 = routing.

---

## Milestones

- **M0** — Container running, `tt06-analog-relax-osc` LVS test clean, tag recorded.
- **M1** — Python Monte Carlo model: unit cap size, resolution, MiM vs VPP decided.
- **M2** — Interface frozen: declared once, Xschem `.sym` committed and checked
  against it, floorplan budget fixed.
- **M3** — Architecture converges in ngspice with ideal switches and comparator.
  Broken down under "M3 — what it is made of" below.
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

### M3 — what it is made of

The question M3 answers: does the architecture work in a circuit simulator, and
does the frozen interface survive contact with it? Treat the `.sym` as "frozen
pending M3" — M3 is the evidence the interface is right.

Progress: Step 0 (DD-08 Vcm, DD-09 harness in `sim/`) done. Step 1
(`top_plate_voltage()` in `sar.py`, with Vcm and a top-plate parasitic;
`test_top_plate.py`) done. Step 2 (`sim/analog.py` generates the block from
`N_BITS`/`PORTS`/unit constants, ideal switches, behavioural StrongARM with
precharge-high outputs, Vcm = `VCM_FRACTION`*vref internally, force mode;
`sim/bench.py` drives it phase by phase; `sim/tests/test_analog.py` replays
`protocol.py` open loop) done — which is most of Step 3 too: every top-plate
voltage and every decision matches the model at 4 and 10 bits. The MiM
variant (`analog.Mim`: `w`/`l`/`m`, top-then-bottom) verified in the container.
Step 3 (`sim/tests/test_sweep.py`) done: the pass criterion. Inputs sit
`EDGE_OFFSET_LSB` either side of thresholds -- every threshold at 6 bits, every
carry plus a random spread at `N_BITS` -- and the circuit's codes must equal
the model's, i.e. its thresholds are within that offset of the model's.
Checked by mutation: a 0.1 LSB comparator offset fails it, 0.01 LSB passes.
Also proven: moving the pin after sampling changes no code (the comparator
never sees the pin).

Step 4 is split: 4a finite resistance (done), 4b Vcm source (pin vs divider,
next), 4c sampling phases (one `sample` wire vs two).

Step 4a (`model/settling.py` + `sim/tests/test_settle.py`) done:
- Law: residual = step * e^(-t/tau); `settle_time(tau, step, tol)`. The
  textbook (N+1) ln2 tau is this at a full-scale step and half-LSB tolerance.
- Paths, each measured in ngspice to within 1% of the law:
  sampling through the Vin pin, tau = R_pin * C_total;
  top-plate switch while sampling, tau = R_top * C_total;
  reference at the first trial, tau = R_ref * C_total/4
  (`c_seen_by_reference`: selected in series with unselected, worst at half);
  bottom switches binary-sized (branch k is 2^k units wide) settle every branch
  with the same tau = R_unit * C_u -- checked by mutation (unscaled fails).
- The comparator now decides on the strobe's rising edge and holds, like a
  latch. A continuous one got the evaluate phase free and hid settling;
  mutation-checked (it passes a sweep the latched one correctly fails).
- The law is conservative: the sweep holds from ~0.65x its phase, fails at 0.5x.
- Minimum phase for the real design = settle_time(R * C, VREF, tolerance) per
  path, with R_pin from the TT analog spec (not yet read -- blocked from the
  cloud session) and C_total = 2^N_BITS * (MiM unit capacitance, which the
  container can measure with the PDK). Sampling through the pin is the slowest
  path: it charges the whole array, the reference only a quarter.

Solver notes, all measured:
- ngspice's default reltol (1e-3) let the floating top plate drift ~40 uV at
  10 bits; 1e-4 gives ~1 uV at the same speed; 1e-5 stalls on the ideal
  switches' edges. `bench.RELTOL`.
- Times need ~12 significant digits: at 5, a read 0.5 ns before a phase end
  rounds by 1 ns at tens of microseconds -- into the wrong phase or past the
  run. `bench.TIME_DIGITS`.
- One simulation of a whole sweep (thousands of ideal-switch edges) eventually
  aborts with "timestep too small"; the same conversions in batches of tens
  never do. Smoothing the switch controls (tanh) did not fix it and tripled
  run time. `sweep.BATCH`.
- Aperture: the pin must not move on the edge that ends sampling -- the switch
  opens mid-move and samples a blend. A real constraint on the pin's driver,
  worth remembering for the Vin source spec in Step 4.

Step 1 overturned a belief: a top-plate parasitic to a fixed potential moves
**no threshold**, linear or not. At every decision the node is back at Vcm,
where it was sampled, so the parasitic holds the charge it started with. Its
real cost is dividing the comparator's input swing by C_tot/(C_tot+C_par), i.e.
multiplying input-referred comparator offset and noise by the inverse. It is a
comparator-budget item (M5), not gain error or INL.

1. **Schematic** (xschem): real PDK capacitors for the array, ideal `sw`
   switches, behavioural comparator (B-source `v(top) > v(vcm)`).
2. **Control**: PWL waveforms generated from `protocol.py` first; then the real
   `sar_fsm.v` through `spicebind`/cocotb co-sim.
3. **Pass criterion**: over a Vin sweep, ngspice's codes equal `sar_convert`'s.
   The same model-first gate the RTL answers to.
4. **Then add realism, one item per run**, and record what each one costs:
   - top plate sampled to Vcm, not ground (MATH.md, "Top plate at Vcm")
   - TT pin series R on `vin` and `vref` (value from the TT analog spec)
   - a top-plate parasitic C -> codes unchanged, swing divided as `top_plate_voltage` predicts
   - one `sample` wire vs two non-overlapping phases (bottom-plate sampling)
5. **Outputs**: settling margin per bit trial against the conversion clock
   (MATH.md, "Settling through the pin"); Vref recovery after the MSB trial;
   a yes/no on each interface question. If the interface changes, change
   `interface.py` then, before M4 grows around it.

In MATH.md's fidelity ladder ("How each number is obtained"), M3 is level 2.

---

## The interface (freeze at M2)

Digital -> analog:

| Wire | Meaning |
|---|---|
| `dac_b` | bottom-plate select, one per binary branch (VREF or GND) |
| `sample` | sampling phase, drives bottom-plate sampling switches |
| `cmp_clk` | StrongARM strobe (rising = evaluate, low = precharge) |
| `force_en`, `force_hi` | forced-input mode: enable, and which rail. An enable and a level rather than one control per rail, so no encoding shorts the reference to ground |

Analog -> digital:

| Wire | Meaning |
|---|---|
| `cmp_out`, `cmp_out_n` | differential latch outputs; equal = metastable |

The bus is as wide as the resolution, and neither its width nor the number of
wires is written down twice: the interface module declares them, the symbol is
drawn to match, and a test fails when the two disagree. Freeze the `.sym`
around this and the two halves decouple.

---

## Key numbers

Worst-case DNL is at the MSB transition, where every LSB cap
switches off and the MSB switches on — no shared devices, mismatch maximally
exposed:

    sigma_DNL_MSB = sqrt(2^N - 1) * (sigma_u / C_u)   [LSB]

Amplification therefore grows with resolution, and each added bit shrinks the
LSB as well, which is why raising resolution costs more than it first appears.
The model sweeps this rather than asserting it; read the committed study for
where the trade lands, and do not restate its numbers here.

Whether kT/C matters is a function of resolution: the noise budget scales with
the square of the LSB, so a constraint that is irrelevant at low resolution
becomes real a few bits up. At the resolutions under consideration the unit
capacitor is set by the smallest geometry the process will draw, not by
matching and not by noise -- both have margin at minimum size.

**MiM vs VPP** — sky130's two capacitor flavours for the array.
- *MiM* (metal-insulator-metal, `cap_mim_m3_*`): an extra thin-dielectric layer
  and plate sandwiched between two metal layers. High capacitance per area.
- *VPP* (vertical parallel plate, `cap_vpp_*`): interdigitated fingers in the
  ordinary metal stack, coupling through their sidewalls. No extra layer, lower
  density.

Matching depends on area, and both share a coefficient, so MiM does not match
better — it buys more farads in the same area. More farads: less kT/C, but
slower settling and a bigger charge kick on Vref. Fewer farads (VPP): faster,
but top-plate parasitics become a larger fraction of the array, dividing the
comparator's swing further (no threshold moves -- see M3 Step 1). Decided with M3's settling numbers and MATH.md's kT/C line.

---

**Where sky130 keeps capacitor matching.** It is not in a datasheet. Each
capacitor's subcircuit carries a mismatch term proportional to `1/sqrt(area)`,
under `libs.ref/sky130_fd_pr/spice/` — *not* the `libs.tech/ngspice/` files,
which only `.include` those, so grepping there finds nothing and looks like
proof that no matching data exists. `mc_mm_switch` also defaults to 0, so a
Monte Carlo run without setting it shows exactly zero spread and invites the
same wrong conclusion. Both traps cost real time once.

The coefficient itself is not repeated here: the model names it, and a second
copy in this file is a second thing to keep true. `docs/model.md` has the grep
that reads it out of the PDK, and `sandbox/cap-matching/` measures it in
ngspice to confirm the expression behaves the way it reads.

```
make shell first, then:

  # 1. Read the coefficient straight out of the 
  PDK
  grep -n czero \
    /foss/pdks/sky130A/libs.ref/sky130_fd_pr/spice
  /sky130_fd_pr__cap_mim_m3_1.model.spice

  # See the whole device while you're there
  grep -v '^\*' \
    /foss/pdks/sky130A/libs.ref/sky130_fd_pr/spice
  /sky130_fd_pr__cap_mim_m3_1.model.spice

  # The VPP equivalent, same shape
  grep -n 'ctot_a =' \
    /foss/pdks/sky130A/libs.ref/sky130_fd_pr/spice
  /sky130_fd_pr__cap_vpp_04p4x04p6_m1m2_noshield.m
  odel.spice

  # Densities, per corner (camimc, farads per 
  um^2)
  grep -rn camimc
  /foss/pdks/sky130A/libs.tech/ngspice/r+c/

  Then measure it yourself — takes about a minute:

  cd /foss/designs/SAR-ASIC/sandbox/cap-matching
  ngspice -b mim_mc.spice 2>/dev/null | grep -oE
  'c = [0-9.e+-]+' | awk '{print $3}' >
  /tmp/caps.txt
  python3 -c "
  import statistics as st
  v = [float(x) for x in open('/tmp/caps.txt')]
  print(f'n={len(v)}  mean={st.mean(v)*1e15:.3f} 
  fF  sigma/C={100*st.pstdev(v)/st.mean(v):.3f} 
  %')
  "
```

## Open findings

Delete each one when it is fixed.

- **Noise study overstates comparator cost.** `effective_bits` adds the
  comparator's code error to quantisation noise in power, assuming the two are
  independent. They are not: noise flips a code only near a threshold, where
  the quantisation error was already largest (correlation measured ~ -0.5).
  Measured against the true Vin, 0.25 LSB of noise costs ~0.4 bit, not the
  ~0.9 the baseline implies. Below gross-error onset the answer is the dithered
  quantiser, sqrt(q^2 + sigma_n^2). Fix = model + test, regenerate
  `noise_baseline.txt`. M5's preamp decision reads this table — fix it first.
- **Vcm source: pin or on-chip divider?** DD-08 decided the top plate is
  referenced to Vcm; where Vcm comes from is open. A pin costs one of the six
  usable `ua` pins and adds the pin R to its settling; a divider costs static
  current and its own settling. M3 Step 4 measures both. `sar.py`'s physics and
  `docs/model.md` still describe ground sampling until M3 Step 1 lands.
- **One `sample` wire vs bottom-plate sampling's two phases.** Either the analog
  block makes the non-overlap locally or the interface grows. Decide in M3.
- **`dac_b` load imbalance** — see Verification. Needs buffer chains + `set_load`.
- **Array pitch vs analog strip height.** A square array plus dummy ring at MiM
  DRC pitch may not fit the analog strip once power-stripe margins come off.
  Check capm/met3 spacing rules before layout; the digital budget has slack.
- **Coefficient recipe below points at `libs.ref`**; `docs/model.md` says read
  the continuous models (the originals differ ~6x). Trust model.md.
- **Prose test walks every file.** `test_no_document_restates_the_resolution`
  does `rglob("*")` and filters after; once LibreLane `runs/` exist that is
  slow. Switch to `git ls-files` — tracked is "ours" by definition.
- **Values still restated in docs:** `docs/floorplan.md` numbers vs a future
  LibreLane config.

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

## Tinytapeout Analog Requirements
https://tinytapeout.com/specs/analog/
analog R2R DAC: https://youtu.be/DQAA4MrG8pM?si=YeRKnLGhNBUwcbCK: https://github.com/mattvenn/tt06-analog-r2r-dac (github for it)

## Tinytapeout GPIO Pins
https://tinytapeout.com/specs/gpio/