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
comparator compares the top plate against Vcm. The FSM honours this by
driving the first trial word (`protocol.py:first_trial`) from reset and from
start, so `dac_b` is never all-zeros while a sample is held and the word does
not change between the sample and the first decision. In M3 Vcm is an ideal
source; whether silicon gets it from its own pin or an on-chip divider is an
open interface question, answered by M3's settling runs, not decided here.

**DD-09 — Circuit simulation harness lives in `sim/`, not `sandbox/`.**
Design code may not import from the sandbox, and M3's harness is design code:
its pass criterion is the golden model's decisions. So the deck runner moved to
`sim/`, the sandbox imports it from there (never the reverse), and `make
verify-analog` runs `sim/`'s tests. Tests needing the simulator skip where
ngspice is absent -- CI has none -- so the parser and generators stay checked
everywhere and the circuit runs are checked in the container.

**DD-10 — Vcm is its own analog pin, driven and decoupled off-chip.**
M3 Step 4b measured every on-chip option: a divider stiff enough costs ~mA of
static current; hung on the VREF pin it sags the reference into a gain error of
tens of LSB; a light one needs nF of decoupling, which the tile cannot hold; a
buffer is a new small-signal design. Off-chip, a divider from the Vref source
plus a 1-10 uF ceramic at the pin (or a bench supply) costs nothing on-chip,
and the pin's kick settles through R_pin * C_total -- in the same loop as
sampling Vin: the two pins are in series with the top switch, so sampling's
tau is (R_vin + R_top + R_vcm) * C_total (Step 6). Only its steadiness within a conversion matters, not
its accuracy (proven: a 10%-wrong steady Vcm converts identically). Bonus: a
settable Vcm is a zero-area DFT knob -- sweep it to measure comparator offset
vs common mode, and to find where the top plate starts to leak.
Pins: `vin`, `vref`, `vcm` = 3 of the 6 usable `ua`.

**DD-11 — Bottom-plate sampling, phases made inside the analog block by a
self-timed generator from the one `sample` wire.**
When sampling ends, the top switch (holding the top plate at Vcm) must let go
*before* the input switches (holding the bottom plates at Vin). Every MOS
switch dumps its channel charge when it turns off; the top switch passes a
constant Vcm, so its dump is the same every conversion -- an offset, removable.
The input switches' dump depends on Vin -- distortion -- and with the top plate
already sealed it lands on bottom plates that are about to be driven to
VREF/GND anyway, so it never reaches the sample. Measured (Step 4c): top first
leaves ~0.1 LSB that varies with Vin; together ~0.9; bottoms first ~1.7.

How the generator guarantees the order: three NOR gates, two of them
cross-coupled. phi_top (top switch) follows `sample`. phi_bot (input switches)
= NOR(NOR(sample, top_still_on), conv_still_on): it cannot fall until the top
line is off, nor rise until the conversion line is off. phi_conv (conversion
switches) = NOR(sample, bot_still_on): it cannot rise until the input line is
off. Each "still_on" is an off-detector on the line the switches' gates
actually hang on -- a skewed inverter (strong NMOS, weak PMOS lengthened
rather than narrowed) whose switching point sits near the transistor
threshold, below where the top switch conducts --
so each phase waits for the previous switch to be *really* off, however slow
its wire, load or corner. Like a relay baton: runner 2 cannot leave until the
baton is in hand, whereas a delay chain is runner 2 leaving on a stopwatch.
The first version read the lines at the NOR's mid-supply threshold and failed
a slowed-line test; the off-detectors are what made the order hold by
construction. Keeps the interface frozen; timing lives next to the switches.

**DD-12 — Single-ended, conventional binary switching.**
One array; the comparator sees the top plate against `vcm`. Differential was
weighed and not taken for risk and schedule, not area (a second array fits the
strip): what limits this design is settling time at the slow corner, and
differential doubles the switches and the load on the reference pin; it needs
a fourth `ua` pin and a differential bench source; and it reopens most of
M3. Vcm-based switching halves the array but makes `vcm` a
DAC level (Vcm != VREF/2 becomes INL, undoing DD-10's "steady is enough"),
adds a mid-rail switch per branch, and makes `dac_b` three-level. Revisit it
only if the floorplan stops fitting; differential is the second-tapeout
upgrade. Reasoning in `docs/topology.md`.

**DD-13 — The single-ended top plate is protected by layout, supplies and
timing.** Top plate on the MiM's upper plate (met3 bottom plate shields it
from substrate); comparator input pair in its own n-well; double guard ring
around array + comparator; nothing routed over the array; comparator inputs (top,
`vcm`) routed as a matched pair; `dac_b` buffers at the array edge;
star-routed analog ground; decap on the comparator supply; decap on
`vref`/`vcm` only as the settling laws size it. In the RTL (M4): one clock
domain, external SPI synchronised and register writes to the analog half held
until a conversion ends, result pins change only at the end of a conversion
(DFT streaming modes are exempt and are not accuracy measurements). Board:
`vin` clamped to ground..VREF with series R. Shields cost comparator margin,
never linearity (Step 1). List and reasoning in `docs/topology.md`.

**DD-14 — The result is read in parallel, its most significant bits on the
dedicated outputs; SPI carries configuration, never the result.**
A dedicated output cannot contend with anything on the board, so the result
sits there, and the bidirectional group carries what is left over, the flag,
and SPI where the platform's own conventions put it -- a convention worth more
than a tidier map, because it is what lets an off-the-shelf daughterboard talk
to the chip. Most significant bits first: those pins alone have to read as a
number across the whole input range, where the low bits alone wrap, a resistor
ladder on them draws a sawtooth instead of a ramp, and an analyser short of
channels reads nothing meaningful. Rejected, and why: serialising the result
(the conversion rate is nowhere near the pins' limit, so a protocol buys
nothing and costs a decoder at the other end), a second beat on the dedicated
outputs (measured, the bidirectional pins are electrically the same as the
dedicated ones, so there is nothing to save), and truncating (the spare pins
are there).

The register behind those pins takes a result under one of two modes, each
selected by a pin so the part moves between them with a jumper and no
firmware: every conversion while the hold pin is low, or one when that pin's
rising edge asks for it. A request outlives the edge that made it, so a press
between conversions is never lost and a bouncing contact captures once rather
than needing a debounce. The flag is up for exactly the cycle the register took
a result, in both modes, so firmware is written against one rule -- wait for
the flag, then read the pins -- and never has to know the mode. Holding the
result does not hold the converter: an asynchronous pin gating the search is
how a half-finished code gets latched.

`pins.py` declares the map and derives the bidirectional group's output
enables; a test fails if the RTL states either again.

**DD-15 — The part is specified at room temperature, and the corner set is
read against that.**
What is being built is a bench part on a Tiny Tapeout board, measured on a
desk. The industrial range the corner runs use was inherited rather than
required, and naming the real one changes what a failing corner means. Two of
the comparator's corners fail outside the bench range and neither is inside
it: fast silicon at high supply and 125 C leaves its noise margin at nothing,
and slow silicon at -40 C does not resolve inside the conversion clock. Both
are the tail's current spread -- the tail is a switch, so its current is
whatever the process, supply and temperature give it, and the extremes of
temperature are where that spread runs out of margin.

So the corners are still run over the wider range, because a result that only
exists inside the specification cannot say how close to the edge the design
sits. They are read as margin rather than as pass or fail. Widening the
specification later is a circuit change and not a re-run:
`docs/comparator.md` says what it costs, cheapest first.

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
| Figures | matplotlib through `figures/house.py` -- one dark house style, enforced by a test. `make figures` draws the lot |
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
- `make coverage` answers the question a passing suite cannot: how much of the
  design the suite reached. Verilator's line, toggle, branch and expression
  coverage merged over every bench, and `pytest --cov` over the model. A
  passing suite that never drove a path is the failure mode this exists to
  surface, and it found one the first time it ran.
- CI's `analog` job runs the figures, the proofs, the analog harness and the
  closed loop inside the pinned image, one step each so the run says where its
  time went and a wedged level is named rather than taking the job with it,
  with `SAR_REQUIRE_TOOLS=1` (root `conftest.py`: a skip fails). Each level
  writes a report under `build/verify/`, which becomes a table on the run's
  summary page and an artifact.
  The `digital` job still builds its tools on ubuntu-latest -- so it has no
  PyYAML and no container packages, and a test that imports one has to skip
  rather than fail there (`pytest.importorskip`); check a new dependency
  against that job, not against the container, which has everything.
- **`make verify-analog` is not the regression.** It is `sim/`. The controller
  running in ngspice, the formal proofs and the full-converter benches are
  behind `verify-integration`, `verify-formal` and `verify-unit`/`-system`,
  and only `make verify` runs the lot. A comparator sizing once landed gated
  on the narrow one, leaving the most sensitive bench in the repository --
  the real latch on a floating top plate -- never run against it. Anything
  that touches `strongarm.py` wants `verify-integration` at least. Consider
  mirroring the tag to GHCR if pull times get annoying -- the image is ~20 GB.

### Understanding the digital half beyond simulation

Simulation shows it does the right thing for the inputs tried. The rest:

| Question | Tool | What it says |
|---|---|---|
| Right for *every* input? | SymbiYosys (`sby`), `make verify-formal` | proves what the benches only sample: DONE within the protocol's step bound, `dac_b` never all-ground while a sample is held (DD-08's digital side), the strobe precharging between trials, the flag up for one step, the metastability flag both ways, and the phases being mutually exclusive — over every comparator answer, request and stall. Mutation-checked: four known defects are introduced and each must fail a proof |
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
  Sizing, noise, the corner reading of DD-15 and the preamp decision are in
  `docs/comparator.md`; the offset spread is measured per part and committed
  (`make offset` -> `sim/offset_baseline.txt`). What is left is the process'
  own threshold-mismatch coefficient, which `tech/` does not carry yet and
  which `model/latch.py`'s offset law cannot be evaluated without -- measured
  through the same netlister the benches use, the way the capacitors' is.
- **M6** — Cap array laid out (scripted), DRC clean. The drawing rules it has
  to obey are read out of the PDK rather than recalled (`tech/sky130.py`,
  `make verify-rules`), and they already decided the array's shape: it is not
  square, because a square one plus its dummy ring does not fit the strip. The
  two numbers every pitch comes in are the grouped and interleaved placements,
  and choosing between them is this milestone's work, not the rules'.
- **M7** — Comparator laid out, DRC/LVS clean. Its schematic was generated
  from the netlist the benches are measured on (`make schematic` ->
  `xschem/strongarm.sch` and its symbol), so what LVS is handed and what M5
  measured cannot be two circuits; `sim/tests/test_schematic.py` netlists the
  sheet back with the editor and compares it element by element.
  Generation is a bootstrap and not the steady state. The sheet's
  *arrangement* is drawn by hand from `schematic.ARRANGEMENT = "drawn"`
  onward, because a readable analog sheet needs things the generator has no
  vocabulary for and regenerating would throw them away: `make schematic`
  therefore leaves it alone and writes what it would have produced under
  `build/` (`FORCE=--force` overrides, asserted by a test, because the
  failure it prevents is silent). What the stage does not change is the
  guarantee -- netlisting the sheet back is what holds it to the circuit, and
  it is a stronger check once the sheet is hand-drawn than before, since
  against a generated sheet it compares the generator with itself. The symbol
  stays generated in both stages: it carries the interface and no
  arrangement. Two things only the netlist-back sees, both found by
  measuring rather than reasoning: **a symbol's port order is the order of
  its pin records**, so laying inputs out on one side and everything else on
  the other published `vref clk inp inn vdd vss outp outn` against a netlist
  declaring `vdd vss vref clk inp inn outp outn` -- an instance of it wired
  vdd to vref, and a test comparing the pins as a set passed. Sides are now a
  table and the records are emitted in the subcircuit's order. And **a port
  symbol deleted from a sheet does not show up in the element comparison**,
  because the net keeps its name from the wire it was drawn on, so the sheet's
  own port list is asserted separately.
  The tile's own sheet, `xschem/sar_analog.sch`, is drawn by hand -- above the
  device level a sheet is a block diagram, and a block diagram is a drawing --
  and held to `sim/analog.py` the same way: netlisted back and compared. It
  carries the comparator so far, with the array, the switches and the phase
  generator arriving as each is laid out, so its tests check the boundary,
  whatever is drawn, and which nets still float. The comparator's wiring lives
  in `analog.COMPARATOR_NETS` because the sheet and the bench both need it and
  a drawing cannot be diffed against a string: the latch's terminals are not
  symmetric (`inp` is Vcm, `inn` the top plate, which is what makes a high
  `cmp_out` mean the plate sat *below* Vcm), so swapping the pair draws a sheet
  that looks right and inverts every decision the converter makes.
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

Step 4 is split: 4a finite resistance (done), 4b Vcm source (done), 4c
sampling phases (done). Step 5, closed loop (done). Step 4d, transmission-
gate input switches (done). Step 6, sky130 sizing and the corner acceptance
(done): M3 is closed. Carried forward: the comparator's input common mode at
full scale (M5), the top plate's transient dip at the first trial, and
whether an on-chip vref decap earns its area (both in Step 6's notes).

`make show-loop` (`sim/show.py`): runs the RTL against the block and writes
`build/show/loop.png` + `loop.raw`. `VIN="0.3 0.95"`, `BITS=4`, `DESIGNED=1`
(uses `bench.DESIGNED` and `measure.law_clock` for the clock, and prints the
model code shifted by the block's measured sampling offset), `ZOOM=<i>` for
one conversion. Nothing asserted -- it's for looking.

Step 6 (done):
- **The "-482 LSB reference switch" was a netlister bug, not sky130.** The
  PDK's FET wrappers take `mult` only to scale their mismatch term
  (`/sqrt(l*w*mult)`); the device inside is one transistor. `devices.Sky130`
  made copies and fingers with `mult` alone, so every binary-sized sky130
  switch was a single unit (the MSB's 512 was 1) and every wide device one
  finger. Fixed: the instance carries `m=` too (`mult` kept equal, so the
  mismatch is the whole device's); `sim/tests/test_devices.py` fails on the
  old netlister. Generic models were never affected (`m=` on the M line).
  Everything measured with sky130 before this is suspect: the Vref sweep,
  "PMOS |Vt| ~1 V makes the reference switch useless", "the TG's PMOS is
  useless at Vin <= 1 V". Generic-model results stand.
- Re-measured (first trial after a settled sample, vin 0.05*Vref, Vref 1.0):
  the design's 1 um/unit pfet_01v8 settles to the sampling offset
  (-0.27 LSB) within a 10 ns trial at tt and ss; so do LVT, n-well-at-Vref and
  3.3 V thick-oxide NMOS variants. No device change needed; Vref stays 1.0 V.
  Exploration scripts in `build/step6/` (not committed).
- **Top switch: 2 -> 8 um.** sky130 on-resistance passing Vcm (DC, gate at
  VDD): 2 um 686 ohm tt / 1438 worst; 8 um 163 / 326; 12 um 109 / 217. The
  worst corner for it is ss *hot* (125 C, 1.62 V), not cold. 8 um keeps it
  under one pin (500 ohm) at every corner. Cost: channel charge on the top
  plate grows with width -- sky130 first-trial error at 12 um is -1.6/-1.1/
  -0.6 LSB at 0.05/0.5/0.95 Vref (offset + ~1 LSB gain, bend ~0.06), ~6x
  the 2 um figures; 8 um is two-thirds of that. The two-gap tau method is
  unreliable for a switch alone (large-signal slewing, solver floor); use
  DC resistance for the switch and the two-gap method only on the whole loop.
- **Sampling charges through both pins in series.** The loop is vin pin ->
  array -> top switch -> vcm pin: tau = (R_vin + R_top + R_vcm) * C_total
  (`settling.sampling_loop_resistance`, circuit test in `test_settle.py`).
  The vcm pin's off-chip decoupling is behind its pin R, so it does not take
  the pin out of the loop -- DD-10's "same law as Vin" understated it 2x.
- `bench.DESIGNED` is now behind `tinytapeout.R_PIN` (500 ohm, the spec's
  bound, `tech/tinytapeout.py`) on `vin`, `vref` and `vcm`. `measure.law_clock`
  takes its tau from `sampling_tau` (renamed from `top_switch_tau`): the
  whole loop, pins included; it raises when the loop is too fast for its two
  sample lengths instead of dividing by zero. `Block.temp` sets `.temp`.
- **The reference pin sags at the first trial.** The ground-side NMOS
  switches (no pin) pull their half down at once; the reference-side PMOS,
  behind the pin, cannot keep up, so the top plate and the MSB plate are
  dragged down (0.11 V / 0.23 V at vin 0.5, generic), the pin supplies ~1 mA
  and sags to ~0.48 V -- which starves the PMOS, whose gate drive is the
  sagging level. Recovery ~4 ns generic, not the R*C/4 = 1 ns law. At the
  loop's clock it is long over; at `bench.PHASE` (10 ns) it is not, and
  `first_trial_error` read a -44 LSB "offset" the loop never sees.
  `first_trial_error(..., phase=)` now reads at the loop's clock. Open: the
  transient dip of the top plate toward ground at high inputs (DD-08's
  contract, transiently) and whether an on-chip vref decap is worth it.
- **Acceptance with sky130 (done):** `test_sky130_devices_convert_within_budget_at_every_corner`
  in `test_sar_loop.py`. The designed block, sky130 devices, 500 ohm on
  `vin`/`vref`/`vcm`, the real RTL; mid-code inputs either side of every
  carry (top code included); one clock for all corners, from the slowest
  sampling corner (ss, 0.9*VDD, 125 C): tau 13.6 ns (the three-resistance
  law says ~10.9 -- the measured loop is ~25% slower, so the clock takes the
  measurement), clock 135 ns at 0.05 LSB, ~21 clocks per conversion. Every
  code right with each corner's offset removed at tt / ss hot / ss cold /
  ff cold / ff hot; no metastability flag. Mutation: at half the clock the
  slowest corner gets 6/23 wrong. ~20 min in the container (needs the PDK;
  skips without it).
- The generic designed-block acceptance now runs behind the same pins, its
  clock from its own loop.

Step 4d (`sim/analog.py`, `model/injection.py:beyond_a_line`,
`sim/tests/test_sampling_phases.py`, the designed-block tests in
`test_sar_loop.py`):
- Input switches are transmission gates (`MosSwitches.w_unit_p`, 1 um per
  unit), and the sky130 slow-cold comparison that was outstanding now says
  why. Measured per unit switch at ss / -40 C / 0.9*VDD: at half the
  reference the PMOS contributes nothing at all (the two are equal to a part
  in a thousand -- it has less than a threshold across it), and at the whole
  reference the NMOS alone reads 2.8 Gohm against the gate's 140 kohm. In
  settling that is 26 us against 1.3 ns, or about 1800 sampling phases
  against a tenth of one. The NMOS does not become slow at the top of the
  range, it stops conducting; the gate carries that end on its own, and it is
  necessary. At nominal supply the margin is narrower (10x at full scale, and
  nothing below three quarters), which is why measuring at tt alone said the
  opposite. `sim/tests/test_probe.py` holds both ends.
  A loop test asserting "NMOS alone fails" flipped between ngspice 42 and 46
  (one code, at the budget edge) and was removed.
  CAUTION -- an earlier measurement with *ideal* conversion switches showed a
  ~0.96 LSB kink for NMOS alone; that was mostly the ideal switch snapping
  shut in the float window, an artifact. Don't trust float-window numbers
  taken with ideal conversion switches.
- Bottom-plate DAC switches are transistors in the designed block
  (`NonOverlap`): NMOS to ground, PMOS to Vref per branch
  (`w_dac_n`/`w_dac_p`, binary-sized), gates as smooth B-source functions of
  c_cnv and the bit. This is what ended the full-scale "timestep too small /
  bvcm#branch" stalls in ngspice 46 (conversion 21 of 23, vin 1023.5 LSB,
  where the top plate sits ~0 V and the top switch conducts while ideal
  switches snap). Gapped keeps ideal DAC switches (its results are verified).
  Gotcha found on the way: a node named `gnd` IS ground in ngspice -- the
  dummy's gate "g" + "n" + "d" collided; gate nodes are gate_n{tag}.
- Generator: `phi_bot_n` from `bot_pre` through a 3-stage buffer starting
  one taper step up; a mirrored off-detector (`_still_on_p`, strong PMOS vs
  long-L NMOS) on it; conversion waits on a 3-input NOR of sample and both
  input lines. Order checked for the PMOS line at every supply/temp corner
  and with the PMOS line alone slowed; mutation (NOR ignoring the PMOS
  detector) caught.
- Acceptance: the closed loop with transistor switches, the generator and
  the RTL, clocked at the top switch's settling-law clock (tau measured from
  a two-length gap ratio), inputs at mid-code around every carry, model given
  the measured offset (`cmp_offset`): every code right. NMOS-only input
  switches fail it at full scale (1020/1021 for 1023).
- Solver lessons, all three needed for transistor benches:
  (1) `chgtol` default (1e-14 C) exceeds one LSB of charge (C_unit * Vref,
  8 fC at 8 fF): floating top plate drifted ~0.16 LSB per edge. Now
  `bench.options`: chgtol = 1% of an LSB's charge on the smallest unit.
  (2) Conversion switches read `phi_conv` as a 0-1 level with the switch's
  own hysteresis, not a u() step (stalled at -40 C / 1.98 V: the jump
  coupled back through the TG gates onto the line the step sat on).
  (3) Ideal bottom-plate switches are defined by a time constant
  (`IDEAL_UNIT_TAU`, 1 ps) not by 1 ohm: scaled per branch that was 2 mOhm
  on the MSB, a sub-ps event the solver could not resolve with transistors
  mid-transition (the "bvcm#branch timestep too small" stalls).
  Tried and reverted: tighter reltol (stalls the ideal switches), smooth
  ramps on every digital read (hung with (3); `limit()` in B-sources also
  misbehaves -- use max/min), minbreak (no effect).
- The order experiment (Gapped top-first/together/bottoms-first) now pins
  NMOS-only switches: with TGs the "together" distortion falls to 0.496 LSB,
  just under its 0.5 threshold -- the TG's cancelling charges, a separate
  effect.

Step 5 (`sim/cosim.py`, `sim/loop.py`, `sim/tests/test_cosim.py`,
`hdl/verification/integration/tb_sar_loop/test_sar_loop.py`) done:
- `sar_fsm.v` runs inside ngspice as an XSPICE `d_cosim` element, compiled by
  ngspice's `vlnggen` script (Verilator underneath), with `adc_bridge` /
  `dac_bridge` as the input gates / output drivers at the boundary. ~0.1 s per
  conversion. What the suite as a whole costs is in its own report rather than
  here, where it would be true of whichever benches existed when it was typed.
- `cosim.build` runs vlnggen's steps itself (verilator --cc, write the order
  headers, verilator --build --exe with ngspice's `scripts/src/` glue, g++
  --shared) instead of calling the script. Through the script it broke in the
  IIC image (ngspice 46): the argument reached Verilator as `--mdir`,
  lowercased by ngspice's command interpreter (not reproduced on 42, even
  with ngbehavior=hsa -- cause unconfirmed; bypassing makes it moot).
  ngspice 46's `d_cosim` never initialises its record of the last value it
  drove on each output (`cm_event_alloc(1, ...)`, no memset). A first change
  that matches the leftover bytes is taken as no change and never reaches
  the wire: in the IIC image `dac_b_o[2]`'s first rise was dropped, the
  first 4-bit conversion read 4 for 0 (the FSM itself was right -- the
  word on the wire lacked bit 2). 42 happens to get zeros. Fix: `build`
  compiles a patched copy of the glue whose `previous_output` starts at 2,
  so its first scan reports every output and overwrites the garbage
  (`cosim.reporting_every_output`). Worth reporting upstream.
  Other gotchas that stand: the element's pin order is Verilator's storage
  order (1-bit ports first, then 16-bit buses at 10 bits; declaration order
  at 4 bits) -- parsed from `Vlng.h` every build; `d_cosim` wants a third
  (inout) port list, `null` when empty; the `.so` path must be absolute.
- Solver stall found: an edge in a PWL at the same instant as a PULSE edge,
  each computing the time its own way, lands two breakpoints ~1e-19 s apart
  and ngspice never advances (only at clock periods whose multiples don't
  round the same way both routes). Start/vin/reset edges now sit a quarter
  cycle off the clock (`loop.START_OFFSET`).
- Tests: every threshold at 4 bits, every carry at 10 bits, flag never raised,
  top plate never below the model's lowest between sampling and result
  (DD-08's contract, the RTL's side), and the pin settling law's clock converts
  while half of it does not (the FSM samples for exactly one clock).
  Mutation-checked: scrambled bus bit order -> 10/23 codes wrong; an FSM that
  detours through all-ground after sampling -> top plate to -0.5 V, caught.
- Ideal-switch block only. With the real generator the loop is badly wrong --
  see the NMOS input switch open finding.

Step 4c (`model/injection.py`, `sim/devices.py`, `sim/tests/test_sampling_phases.py`,
plus the Vcm pin from DD-10) done:
- Real MOS switches for top and input (generic BSIM4 everywhere; sky130 via
  `devices.Sky130(corner)`). Measured at the decision point, realistic 8 fF
  unit: see DD-11 numbers.
- sky130 device rules the first container run taught: no model below
  W = 0.42 um (the detector's weak PMOS was 0.3 -> "could not find a valid
  modelname"); size bins are bounded, so wide devices are split into equal
  fingers <= 5 um (`devices.SKY130_W_FINGER_MAX`); to weaken a device at
  minimum width, lengthen it. The detector (NMOS 2 um, PMOS 0.42 x 1 um)
  switches at 0.41 V generic and 0.51-0.68 V across sky130 corners -- an
  inverter cannot flip below its NMOS threshold. That is well below where the
  top switch (at Vcm) conducts; an input switch at Vin ~ 0 may still conduct
  faintly as conversion starts, costing the Vin pin a little current, not a
  code (top plate already sealed). Corner test passes tt/ff/ss/fs/sf, run in
  the cloud against the raw skywater-pdk-libs-sky130_fd_pr models (a trimmed
  nfet/pfet library; the container's open_pdks "combined" library is the
  authority).
- Offset doubles with the top switch's width (the model's channel charge).
- Generator: every edge ordered at VDD +-10% and -40/27/125 C; ordering held
  with a line slowed >5x; the top switch's step is the same for every input
  (varies 0.0007 LSB). Mutation-checked: without the off-detectors, fails.
- Confirmed with real devices: holding the array at all-zeros after sampling
  drives the top plate to Vcm - Vin, below ground, and the off top switch leaks
  -- DD-08's "go straight to the first trial word" contract.

Step 4b (`model/common_mode.py` + `sim/tests/test_vcm_source.py`) done:
- What a threshold sees is Vcm(at end of sampling) - Vcm(at the decision).
  A steady but 10%-wrong Vcm converts exactly as the model; sampling to one
  Vcm and comparing against another fails (mutation-checked).
- Sampling kicks Vcm by charge ~ C_total * (Vin_new - Vin_previous): the kick
  is the *input's change between conversions*, not VREF. Same inputs through
  the same divider: in order they convert, zig-zagged they don't -- predicted
  by `drift_within_conversion` before the circuit confirmed it. A memory
  effect that grows with input frequency.
- A divider hung on the VREF pin draws its static current through the pin R:
  the array's reference sags (`loaded_reference`) = gain error. Circuit
  matches the model at the sagged reference, not the source's.
- Illustrative real numbers (C_total 8 pF assumed, VREF 1.8 V, 50 ns sample,
  1/2 LSB): a bare divider stiff enough for a full-scale jump needs R_th
  <= ~820 ohm, ~0.55 mA / ~1 mW static; on the VREF pin that sags 3 LSB at
  10 ohm, 30 LSB at 100 ohm, 135 LSB at 500 ohm. A light 45 uA divider needs
  ~1.3 nF decoupling (160x the array) -- not buildable on-chip -- and even a
  1 LSB/conversion input shifts it 0.5 LSB bare.
- Recommendation (not yet a DD -- Joseph decides): Vcm on its own `ua` pin,
  driven off-chip with off-chip decoupling. Its kick then settles through
  R_pin * C_total, the same law as Vin sampling, which already binds -- no new
  constraint, no on-chip current, costs one pin (vin, vref, vcm = 3 of 6).
  The alternative is an on-chip buffer, which is an M5-style small-signal
  design (loop stability, output impedance), not an M3 one.
- Harness lessons: the open-loop replay must replay the same model it is graded
  against (`sweep.convert(model_vref=...)`), and only a replay's *first*
  disagreeing decision means anything -- `mismatches` reports that bit.

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

**The order of the terminals is part of the freeze, and was not at first.**
The reasoning for leaving it out was that consumers wire by name; a SPICE
subcircuit instance does not, it wires by position, and a symbol's port order
is the order of its pin records -- which a person drawing one assigns by where
the pins looked best. So `sar_analog.sym` published `dac_b[9:0] cmp_out sample
cmp_out_n vdd cmp_clk vss ...` against `analog.terminals()`'s `dac_b[9:0]
sample cmp_clk force_en force_hi cmp_out ...`, and an instance of it tied the
strobe to the sampling phase and a supply to an output. Nothing failed,
because both agreed on the set and the test compared sets. `interface.PORTS`
is now the one order, the symbol's records are in it, and the test is ordered.
Where a pin sits on the symbol stays free -- that is the lesson both times
this bit: the side is a drawing choice, the order is electrical, and tying
one to the other is what made a correct-looking symbol wrong.

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

**Where sky130 keeps its capacitor numbers.** Not in a datasheet: inside the
device subcircuits, as a mismatch term proportional to `1/sqrt(area)` and a
density multiplying the plate.

**The PDK ships them twice and the two disagree.** `libs.tech/combined/
continuous/` is what a simulation reads — the PDK's own xschem setup selects
it — and `libs.ref/sky130_fd_pr/spice/` plus `libs.tech/ngspice/r+c/` are the
superseded micro-binned originals. They differ by about six times on matching,
and on the MiM they are not even the same equation: the originals add a fringe
term on a plate biased inward, the continuous models use area alone on a plate
biased outward by more than a tenth of a micrometre. A grep that finds a
plausible number in the wrong tree is the expensive mistake here, because
nothing about the number looks wrong.

`mc_mm_switch` also defaults to 0, so a Monte Carlo run without setting it
shows exactly zero spread and invites a different wrong conclusion. Both traps
cost real time once.

**And the drawing rules are shipped three times, which is worse.** The tree
carries `klayout/drc/sky130A.lydrc`, `klayout/drc/sky130A_mr.drc` and
`magic/sky130A.tech`, and `sak-drc.sh` -- our own DRC script -- runs the second
and the third. Not the first, which is the one named after the process, the one
a search finds, and the one whose capacitor rules each name the metal a layer
below the device's plate: `m2` and `via2` where the plate is on met3 and its
contact is via3. Its numbers are mostly the right numbers attached to the wrong
layers, so nothing about reading it looks like a mistake.

The rule to distrust most is `capm.11`, the keep-away from unrelated metal,
because the tree states it three ways: 0.14 in the unused deck's code, 0.5 in
that same deck's message *and* in the running deck's own `capm.11`, and 1.34 in
Magic. What settles it is that the running deck states the constraint a second
time as 1.2 from the bottom plate (`capm.2b_a`), and the bottom plate runs 0.14
past the plate -- so two independent expressions give 1.34 and one gives 0.5.
The strictest is also the corroborated one, which is the only direction in
which guessing is safe.

The reverse trap is `capm.6`, the largest a plate may be drawn: a real rule of
the process that *only* the unused deck codes, so a plate too large passes our
own DRC and fails at whoever checks it next. It is declared and guarded in
arithmetic for that reason. The array is nowhere near the bound; one shape
drawn as a decoupling or bias capacitor could be.

`tech/sky130.py` declares all of them, `tech/tests/test_drc.py` reads them back
out of the decks -- each from the deck that is actually its authority -- and
`make verify-rules` is the seconds-long CI step that runs it.

A seeded Monte Carlo has the same failure from the other end: ngspice applies
`.option seed` again on every redraw, so one run of many draws is one part
measured many times, reporting a spread of zero while looking in every other
way like a finished sweep. `set rndseed` does not seed the draws at all. A
population is therefore one run per seed, each seed derived from what the draw
is rather than where it sits, and `strongarm.deck` refuses a seed with more
than one draw instead of explaining itself.

No number is repeated here. `tech/sky130.py` declares the continuous tree's
parameters, `mim_unit()` evaluates the device's own expression, and a test
reads them back out of the PDK and checks the expression against the capacitor
ngspice instantiates. `sandbox/cap-matching/` measures the mismatch spread the
same way.

```
make shell first, then:

  C=$PDK_ROOT/$PDK/libs.tech/combined/continuous

  # The MiM as a simulation builds it: area times a biased plate, no fringe
  sed -n '/subckt .*cap_mim_m3_1/,/^.ends/p' $C/models_capacitors.spice

  # Its density and plate bias, per capacitance corner
  grep -H 'sw_cap_mim_' $C/parameters_cap_{nom,low,high}.spice

  # The matching coefficient, as a ratio: times 100 for percent-micrometres
  grep -n sw_mm_cmim $C/models_global.spice

  # What a section actually pulls in -- the capacitance corner rides with the
  # device corner, so tt is the only typical one and ff_hh / ss_ll the extremes
  grep -A8 '^.lib ss_ll$' $PDK_ROOT/$PDK/libs.tech/combined/sky130.lib.spice

  Then measure it yourself -- takes about a minute:

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

## Cleanup branch (architecture + STYLE)

- Layers, bottom first: `tech/` (sky130 facts: device names, W_MIN,
  W_FINGER_MAX, CAP_A_C, CAP_MIN_AREA_*, mosfet geometry) -> `reference/`
  (moved out of hdl/: it is the chip's contract) -> `model/` (laws, metrics)
  -> `studies/` (yield/noise sweeps, baselines, plots) and `sim/` -> 
  `hdl/verification/`. Declared and enforced in `tests/test_layers.py` (also
  fails on duplicate module names and stdlib shadowing), run by `make lint`.
  `docs/architecture.md` explains; the README defers to both.
- `bench.Block` holds the block's settings; `Bench(phases, block, ...)` and
  `loop.Loop(inputs, library, block, clock)`. `sweep.convert(..., phase=,
  **block_args)`. Measurements shared by tests live in `sim/measure.py`
  (settled_for, tau_from_gaps, first_trial_error). `BATCH` is in `ngspice`.
  Studies share `studies/study_points.py` (seeding, table widths).
- One N-input `_nor` in analog.py (was _nor + _nor3).
- STYLE: languages now say cocotb/pyuvm for benches, SystemVerilog only for
  formal properties (`<block>_props.sv`, SymbiYosys). Literals named across
  production and tests; the ngspice parser tests keep their text fixtures
  inline (the literal and its expected parse are one fact on one line).
- Prose test finds the root by pyproject.toml and scans `git ls-files`.
- cocotb 2.0 needs Verilator >= 5.036: the cloud sandbox's 5.020 cannot run
  the unit tests (fails on main too); the container and CI can.

## Open findings

Delete each one when it is fixed.

- **Sampling error with the designed block is offset + gain.** Settled
  first-trial error, TG input switches: -0.90 LSB at 0.05 V to -0.45 at
  0.95 V, straight to 0.005 LSB (endpoint fit). Offset -0.68 LSB at
  mid-scale (generic, 2 um top switch). With sky130 and the 8 um top switch,
  at the loop's clock, the mid-scale offset is -0.66 to -1.27 LSB across
  corners (largest ff, smallest ss cold): it moves with the corner, so a
  one-time factory calibration is not enough -- M4's DFT modes (forced
  input) let firmware measure it in the field.
  The designed latch adds its own, and it is an offset and nothing else:
  measured over every threshold of the 4-bit loop with the transistor latch
  on the floating top plate, each one sits 0.05 LSB below the model's,
  constant to within the measurement's own resolution. Pinned by
  `test_what_the_latch_adds_is_an_offset_and_not_a_shape`, which bisects every
  threshold and holds the spread of their errors to that resolution and no
  finer -- the claim this rests on is a test rather than prose and a scratch
  script. The apparent gain in the first run of it was a line fitted through
  one bisection step; there is no gain to calibrate.
  Which cost a day's confusion once, and the lesson generalises:
  `test_the_array_converts_with_the_comparator_it_will_be_built_with` judged
  codes from inputs `EDGE_OFFSET_LSB` (0.05 LSB) from a threshold against the
  bare model, so its tolerance *was* the offset. It failed three codes, and
  calibrating it at one threshold only moved the failures to the other end of
  the range -- a criterion whose margin is finer than the resolution of the
  thing it measures reports the measurement, not the circuit. It now uses
  mid-code inputs like every other designed-block run, which leaves the
  offset ten times inside tolerance and still sees what only that bench can:
  a kick that varies with the code, a latch that cannot resolve against a
  floating node, a flag raised.
- **`dac_b` load imbalance** — see Verification. Needs buffer chains + `set_load`.
- ~~**Array pitch vs analog strip height.**~~ Answered, and it binds. The
  rules are read now, and a square array plus a dummy ring comes to 97.00 um
  on a side, 99.68 once unrelated metal is held off the plates, against a
  95.76 um strip. `docs/floorplan.md` had estimated 76 um, so it was wrong by
  twenty-three micrometres in the direction that does not announce itself.
  What fits is the same array not drawn square: the strip is three times as
  wide as it is tall, so the height sets the rows and the width has room to
  spare. The cost is not area but symmetry -- a gradient is no longer the same
  length both ways, so a placement scheme has a long axis and a short one to
  treat differently.
  The compact figure is a bound and not a layout, which is worth keeping
  straight because the first version of this arithmetic was not: the narrow
  pitch is what two units of *one branch* get, so applying it to a whole row
  assumes no branch boundary falls on that row, and a ring never qualifies at
  all -- a dummy carries no charge, so it is tied off on its own and the step
  across it is the wider one whatever the branches inside do. That ring is the
  entire 3.9 um by which the compact square array misses, and charging it
  correctly cost a row at two of the three splits in that document's table.
  The pitch itself turns on something that is not a property of the
  capacitors. Units of one branch share a bottom plate and step at the
  plate-to-plate spacing (2.84 um); units of different branches are different
  nets, so the metal under them is two polygons that must be apart *as metal*,
  and the step is 3.48 um. Grouping each branch is the compact array and
  interleaving them is the matched one -- a common-centroid scheme interleaves
  on purpose, so the gradient it cancels is paid for in rows, six of them at
  this split. What is still open is which of the two the array is placed as,
  which is M6's to decide with the yield study beside it.

- **The unit capacitor's size is a choice nobody has made.**
  `CAP_MIN_AREA_MIM` is 4.00 um2 and its comment claimed it was the smallest
  the process would draw, so that no array could match worse. It is not:
  neither running deck states a minimum area for the MiM, the only size rule
  is a minimum width of 1.0 um, and the device's own model defaults to a
  micrometre each way -- so a square a quarter of this is legal to draw and
  matches half as well. Nothing is wrong today, because the project draws the
  larger one and the test now holds it to the rule rather than to itself. What
  is open is that the yield study's "worst matching buildable" line is drawn
  at an area that is a decision, and `studies/plots.py` says "cannot be made"
  of a device that can. Decide the unit's size deliberately, then say so there.
- **Values still restated in docs:** `docs/floorplan.md`'s die is read out of
  the vendored template by a test, and the height it splits that die at is
  declared beside it now (`template.DIGITAL_HEIGHT`, `template.analog_strip()`)
  rather than living in that document -- the analog half's budget is arithmetic
  on it, and a budget checked against a number in prose is checked against
  nothing. It is still a decision rather than a measurement, and the LibreLane
  run that would replace it has not happened.

- **The platform names its supplies twice, differently.** The vendored DEF
  carries `VPWR`/`VGND` as special nets; the shuttle's Verilog template names
  them `VGND`/`VDPWR`. Our copy is not stale -- it is byte-identical to
  upstream's `tt-support-tools` today -- so the two upstream repositories
  disagree. The tile top follows the Verilog, which is what a port list has to
  match, and `tech/tinytapeout.py` declares it with the reason. What is open is
  what M9's power stripes are called in the layout; resolve it against the
  shuttle actually targeted, not from the file that happens to be open.

- **The clock the board is asked for is undecided**, and `info.yaml` carries
  the platform's zero placeholder until it is. The settling law fixes how
  short a conversion *step* may be at the slowest corner; the divider stands
  between that and the clock a board supplies, so the rate is a board choice
  and nothing on the die waits on it. Decide it before submission, because it
  is what the datasheet advertises the part at.

- **Which analog pin carries which signal.** `ua[0..2]` are claimed in order,
  because the platform bonds them that way and bills per pin; `pins.py` fixes
  the count and the no-gap rule and marks the assignment provisional. It
  follows the analog strip's own placement -- pad coupling does not decide it
  at a twenty-micrometre pitch, routing does -- so it is answered when the
  strip is drawn, and `info.yaml` regenerates from the map when it is.

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

- Xschem `.sch`/`.sym` and Magic `.mag` are text — diff and merge normally,
  and a sheet can therefore be generated and checked rather than only drawn.
  Two things about writing one cost real time once. **The two FET symbols are
  drawn opposite ways round**: `pfet_01v8.sym` keeps its drain where
  `nfet_01v8.sym` keeps its source, so pin offsets taken from one flavour swap
  the other's drain and source -- a circuit that is wrong and draws right, and
  invisible without netlisting it back. Read each symbol's own `B` records.
  **And the editor suppresses `m=1`** while emitting `m=3`, so an instance
  that does not state its multiplier netlists without one; that multiplier is
  what the parallel fingers of a device too wide for the models are made of,
  the same quantity whose absence once read as a reference switch five hundred
  times too small.
  **An instance's name is written through verbatim**, and a SPICE subcircuit
  call is spelled with a leading X -- which is why the editor's own default
  instance name is `x1`. A block named `cmp` on a sheet netlists to a line
  beginning `cmp`, which is not a call and not an element any simulator
  knows, and the sheet looks right.
  **And the editor runs an electrical rule check of its own**: `xschem -b -n
  -q` exits 10 when a net has nothing driving it and 0 otherwise, measured
  by giving one such net a driver and watching the same sheet go to zero. It
  is a flag and not a count, so it says that something floats and never
  which thing -- the netlist is still written and still correct. Worth
  knowing because an unfinished sheet has the condition by construction, so
  the status cannot be a gate until the block is whole; `sim/tests/
  test_top_sheet.py` asserts which nets float instead, from the netlist,
  which is a check that tightens by itself as blocks are drawn.
- GDS is binary — gitignored and regenerated. LFS only for final submission.
- `.gitignore` must cover `runs/`, `*.raw`, ngspice output dirs. Otherwise the
  first commit is a gigabyte of waveforms.
- Treat `.sym` like a C header: freeze the interface early, parallelize after.

## Tinytapeout Analog Requirements
https://tinytapeout.com/specs/analog/
analog R2R DAC: https://youtu.be/DQAA4MrG8pM?si=YeRKnLGhNBUwcbCK: https://github.com/mattvenn/tt06-analog-r2r-dac (github for it)

## Tinytapeout GPIO Pins
https://tinytapeout.com/specs/gpio/