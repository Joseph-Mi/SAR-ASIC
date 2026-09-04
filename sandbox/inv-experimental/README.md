# Inverter layout

The layout is generated, not drawn. `gen_inv.tcl` builds `inv.mag` and both
device cells from nothing, so the committed artifact can always be rebuilt and
a change is a diff in a script rather than a diff in coordinates.

`inv.sch` is the reference the layout is checked against, and nothing here
writes to it.

## Targets

| | |
|---|---|
| `make layout` | build `inv.mag` and its device cells, discarding what was there |
| `make drc` | geometry rules; must report zero |
| `make lvs` | compare the layout against the schematic |
| `make pex` | extract parasitics into a simulatable netlist |
| `make clean` | extraction and comparison products only, never sources |
| `make` | layout, then drc, then lvs |

`make drc` runs in its own magic process on purpose. Counting in the session
that built the cell reports the checks queued while building it rather than the
state of what reached disk, and it will claim errors that are not there.

## Opening it

Magic needs a display, which a `docker exec` shell does not have:

```bash
make shell
cd sandbox/inv-experimental
export DISPLAY=:1
magic inv.mag &
```

The window appears on the noVNC desktop that `make container` points at. The
technology comes from the container's own startup file, so no local `.magicrc`
is needed here -- adding one that sources the PDK a second time is an error,
not a convenience.

A device renders as a named empty box until it is expanded, which is how magic
draws any subcell. The geometry is there; opening a device cell on its own
shows it because it is then the top cell rather than a subcell. To see through
the hierarchy in place:

```
select top cell
expand
```

`F` expands under the box, `Ctrl-F` unexpands, `/` toggles the selection.

**Opening it read-only is safe; saving from the GUI is not.** The next
`make layout` overwrites whatever was saved. To change the cell, change the
generator.

## Pointing a testbench at the extracted netlist

The extracted subcircuit does not take its ports in the schematic's order, so
the two are not interchangeable and a netlist swap miswires every net without
complaining. A symbol whose pin order matches the extracted subcircuit, holding
`spice_sym_def=".include inv.pex.spice"`, is what a post-layout testbench
instantiates. The upstream example carries one to copy.

The parasitics worth reading are the ones with no schematic counterpart at all:
the schematic netlist holds no capacitors, so gate-to-drain feedback exists
only after extraction.

## Why there are device cells in this directory

`sky130_fd_pr__nfet_01v8_<suffix>.mag` and its pmos counterpart are *generated*
cells, not library cells. sky130's transistors are parameterised, so no drawn
cell exists in the PDK for a given width, length, finger count and guard ring
choice. Magic synthesises one on demand and names it by a suffix.

They are outputs of the generator, and `inv.mag` refers to them by name, so
they live beside it and are committed with it. Deleting one leaves `inv.mag`
referring to a cell that cannot be read, which is what an empty layout with two
missing children looks like.

## Checking the device sizing

The parameters magic extracts back out of the drawn shapes are what LVS
compares, so they are the ones worth reading -- not the values handed to the
generator, and not the defaults the device dialog opens with, which are the
process minimum rather than anything this cell uses:

```bash
make lvs
grep sky130_fd_pr inv_magic.spice
```
