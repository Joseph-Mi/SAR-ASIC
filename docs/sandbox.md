# Sandbox

`sandbox/` is where you learn the analog tools on circuits that do not matter.
Nothing in it is part of the ADC. No model, testbench, or RTL file may import
from it, and no result from it is evidence about the design. Delete any
subdirectory the moment it has taught you what it was going to teach you.

It exists because the alternative — learning xschem and ngspice on the
comparator — means debugging your schematic and your understanding of the tool
at the same time, and being unable to tell which one is wrong.

Two subdirectories today:

| Directory | What it is |
|---|---|
| `inv-example/` | Upstream's inverter, copied in whole. Read it, run it, do not edit it — it is the reference for what a working setup looks like. |
| `inv-experimental/` | The same circuit rebuilt by hand. This is the one you break. |

The example is built on the thick-oxide `g5v0d10v5` devices; the experimental
one on core `nfet_01v8` / `pfet_01v8`. The device name carries its own supply
voltage, so a testbench copied from one to the other will be driving the wrong
rail. That is the single most likely reason a rebuilt circuit "works but the
output never switches".

Getting into the container, PDK variables, and the VNC desktop are in
`environment.md` and are not repeated here.

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
