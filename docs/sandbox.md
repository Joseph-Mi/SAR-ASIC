# Sandbox

`sandbox/` is where you learn the analog tools on circuits that do not matter.
Nothing in it is part of the ADC. No model, testbench, or RTL file may import
from it, and no result from it is evidence about the design. Delete any
subdirectory the moment it has taught you what it was going to teach you.

It exists because the alternative — learning xschem and ngspice on the
comparator — means debugging your schematic and your understanding of the tool
at the same time, and being unable to tell which one is wrong.

| Directory | What it is |
|---|---|
| `inv-example/` | Upstream's inverter, copied in whole. Read it, run it, do not edit it — it is the reference for what a working setup looks like. |
| `inv-experimental/` | The same circuit rebuilt by hand. This is the one you break. |
| `cap-matching/` | One question about the PDK's capacitor mismatch coefficient, and a deck that answers it. No schematic. |
| `tools/` | Shared helpers. Agnostic mechanism only — running a deck, restamping instances — plus the PDK's device parameters. |

The example is built on the thick-oxide `g5v0d10v5` devices; the experimental
one on core `nfet_01v8` / `pfet_01v8`. The device name carries its own supply
voltage, so a testbench copied from one to the other will be driving the wrong
rail. That is the single most likely reason a rebuilt circuit "works but the
output never switches".

---

## From a cold terminal

Assumes the host, a fresh shell, nothing running. New-machine setup, the PDK
variables, and why the container exists at all are in `environment.md`; this is
only the shortest path from a prompt to a schematic on screen.

```bash
cd ~/github/SAR-ASIC
make container
```

That command is idempotent and covers every state the container can be in: it
creates one if none exists, starts it if it is stopped, and prints `already
running` if it is up. Then it prints the noVNC URL with the password already in
the query string, and opens a browser at it.

The address and the password are deliberately not written down here. `make
container` is what knows them, and a URL copied into a document is a URL that
goes stale. Pass `OPEN=0` if you would rather it not launch a browser.

From there, two doors:

| Door | Use it for |
|---|---|
| The noVNC desktop in the browser | xschem, magic, KLayout, GTKWave — anything that draws |
| `make shell` | netlisting, batch ngspice, git — same container, no desktop |

`make shell` lands you in bash already at this repo, so it is the faster door
whenever you do not need pixels.

Two failures worth recognising rather than debugging:

- **The browser tab shows nothing.** The container is up but has no published
  port. `make container` says so in place of the URL rather than printing a dead
  link, so read its last line.
- **You are in the container but the repo is not under `/foss/designs`.** The
  bind mount did not take, which means `DESIGNS` was wrong when the container
  was *created*. `make doctor` checks for this.

### A long-running container drifts off the pin

`make container` will not re-create a container that is already running, so one
created before the version pin existed keeps whatever image it was built from
— indefinitely, and silently. Check what you are actually running:

```bash
docker ps --format '{{.Image}}'
```

If that disagrees with `OSIC_TOOLS_TAG` in `versions.env`, the toolchain under
you is not the pinned one and not what CI uses. Recreate it:

```bash
docker rm -f iic-osic-tools_xvnc_uid_$(id -u)
make container
docker exec -it iic-osic-tools_xvnc_uid_$(id -u) bash
```

The repo is a bind mount and survives untouched. What you lose is the
container's own home directory, which is the reason nothing of value is ever
installed there.

---

## Why each experiment has its own xschemrc

xschem reads `./xschemrc` from the directory it was launched in, *instead of*
the one in `$HOME`. Not in addition to. So a sandbox directory containing an
`xschemrc` gets that file and nothing else, which has two consequences worth
internalising before the first confusing failure:

**The PDK rc must be sourced explicitly.** If it is not, the sky130 symbol
libraries are not on `XSCHEM_LIBRARY_PATH`, and every device in the schematic
netlists as `IS MISSING`. The schematic looks correct on screen. Only the
netlist shows the problem.

**Netlists land beside the schematic.** The default is a directory under
`$HOME`, which is container-local and dies with the container — and worse,
leaves you with two possible netlist locations and no way to know which one
ngspice just read. Setting the local netlist directory collapses that to one.

Both lines are already in the sandbox `xschemrc` files, commented. Copy that
file when you start a new experiment; it is the smallest thing that makes a
directory work.

---

## The loop

Launch xschem from the experiment directory, never from the repo root — the
whole point of the previous section is that the launch directory selects the
configuration.

```bash
make shell
cd sandbox/<experiment>
xschem <cell>.sch &
```

Then:

1. **Draw the cell.** Devices come from the sky130 libraries; pins come from
   `ipin.sym`, `opin.sym`, `iopin.sym`. Supplies are pins, not globals — an
   inverter has four terminals, and forgetting the two supply pins produces a
   netlist that simulates and is wrong.

2. **Make a symbol.** Symbol -> "Make symbol from schematic". This is what lets
   a testbench instantiate the cell instead of duplicating it. Redo it whenever
   the pin list changes; a stale symbol silently connects the wrong nets.

3. **Draw a separate testbench schematic.** The cell has no stimulus, no supply
   values, and no simulator commands in it. That separation is the reason the
   same cell can be driven by a DC sweep and a transient without editing it.
   A testbench holds:

   - the cell's symbol, instantiated;
   - `vsource.sym` for supply and input, `gnd.sym` for the reference,
     `capa.sym` for a load;
   - a `code.sym` block that `.lib`s in the sky130 models at the desired
     process corner;
   - a `code_shown.sym` block holding the `.control` / `.endc` analysis;
   - optionally `launcher.sym` buttons that save, netlist, simulate, and load
     the waveforms without leaving the schematic.

   The example testbench has one of each, which is why it is worth reading
   before drawing your own.

4. **Simulate**, either from the launcher button or from a shell.

5. **Look at the waves.** xschem draws them in-canvas from the raw file, so
   the schematic and the result sit in one window. GTKWave and surfer are
   available if you would rather have a separate viewer.

---

## Without the GUI

Netlisting and simulation both run headless, which is what makes them scriptable
and what lets you check a change without a VNC session:

```bash
xschem --no_x -n -s -q <cell>.sch     # schematic -> simulation/<cell>.spice
ngspice -b simulation/<tb>.spice      # batch run, no interactive prompt
```

Useful for confirming that a schematic still netlists after an edit, and for
diffing a netlist against the previous one — the netlist is text, and a diff
that surprises you is a schematic edit you did not mean to make.

A netlist whose `.subckt` line is commented out was netlisted as a *top-level*
circuit rather than as an instantiable cell. That is what xschem produces when
you netlist a cell directly, and it is fine — it just means that file is not the
one a testbench includes.

---

## Driving a sweep from Python

Hand-editing a schematic between runs stops scaling once the question has two
axes. It also puts every run one bad edit away from a corrupted cell: a width
typed over the length leaves a property the netlister silently drops, and the
device then takes the model's default length while the schematic still reads as
though it did not.

So a sweep reads the netlist as a parts bin rather than running it. The model
library line and the cell's subcircuit come out of it, the deck is built around
them, and the schematic is never written to. What the schematic still owns is
the topology — change the circuit there, and every sweep follows.

### The model library dominates the cost

Selecting the sky130 library takes roughly 45 seconds, and it is paid per
ngspice process, not per analysis: an operating point on a bare resistor with
that `.lib` costs the same as a full sweep. Two consequences shape every deck
here.

**A parameter sweep is one deck, not N decks.** Each geometry is instantiated as
its own subcircuit, sharing one input source and read out on its own node. One
sweep, one library load, N results — flat in the number of points, where a
process per point is not.

**A Monte Carlo loops around `reset`, not around a new process.** `reset` is
what redraws the PDK's mismatch terms, and it keeps the library already loaded.

### Reading a Monte Carlo

`mc_mm_switch` enables local device mismatch — the variation between two
devices on one die. `mc_pr_switch` is the global process spread, which moves a
whole die together. A comparator sees the corner as common mode and rejects it,
so mismatch is the switch that matters for offset.

Neither is on by default, and a run without setting one shows exactly zero
spread, which reads as a PDK carrying no matching data.

Nothing about the geometry changes across draws. What is being read is the
spread of a measured quantity, and its standard error is about `1/sqrt(2N)` of
itself — so a few hundred draws pin the spread to a few percent, and two runs
of the same deck disagree by about that much. Read several runs, not one run's
digits.

### Isolating area from bias

Pelgrom predicts a spread falling as the square root of device area. Testing
that by widening the device does not work: width moves the trip point too, so
the two legs are measured at different operating points and the ratio comes out
wrong in a way that looks like a broken model.

Scale multiplicity instead. The PDK spends its mismatch as
`slope/sqrt(l*w*mult)`, so replicating a device raises area exactly as widening
it does — but current density, trip point and every bias hold still. The means
of the two legs landing on top of each other is the evidence that nothing but
area moved.

---

## What is committed

Schematics and symbols are text: committed, diffed, reviewed like source.

Everything under `simulation/` is generated from them, along with raw waveform
files, and is ignored. Never commit a netlist. It is a build product of a
schematic that is already in the repo, and a stale one that disagrees with its
schematic is the most confusing artifact this flow can produce.

---

## Starting a new experiment

```bash
mkdir sandbox/<name>
cp sandbox/inv-experimental/xschemrc sandbox/<name>/
cd sandbox/<name> && xschem <cell>.sch &
```

Give it a name that says what question it answers, not what circuit it contains.
The value of a sandbox directory is the question, and once that is answered the
directory is disposable.
