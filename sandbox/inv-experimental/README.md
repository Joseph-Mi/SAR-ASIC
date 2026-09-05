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
| `make sim` | delay of the drawn cell against the designed one, across load |
| `make clean` | build products only, never sources |
| `make` | all of the above, in that order |

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

## How the cell is put together

Both devices keep their guard ring: it is the bulk tie, and a floating bulk is
the first thing LVS rejects. What is dropped is the solid metal over that ring,
which otherwise leaves nothing routed out of the device anywhere to go. One
edge of each ring is carried up to metal1 instead and serves as that device's
supply rail, leaving the other three as local interconnect, free to be crossed.

The gate contacts are placed facing each other, so the input is a single
column. The output cannot share that column, so it steps aside and climbs
outside it. Each source runs outward onto its own guard ring, at the same
offset within its own device's frame, which keeps the two halves symmetric.

The pad coordinates in the generator are read out of the generated device
cells. They are not derivable and not stable: change a device parameter and
they move, so re-read them rather than adjusting them by hand.

## Comparing the drawn cell against the designed one

`make sim` puts both subcircuits in one deck, drives them from one source into
equal loads, and sweeps the load. Reading a single load tells you almost
nothing; the shape of the penalty against load is the result. It is largest
where the cell drives little more than itself and falls away as an external
load takes over, which is what says whether post-layout simulation matters for
a given cell.

Two things have to be equalised or the difference stops being the parasitics.
The extracted subcircuit does not declare its terminals in the schematic's
order, so both are wired by terminal name rather than by position. It also
omits the source and drain sheet-resistance terms the schematic instance
carries, so those are stripped from the schematic side; left in, they slow one
side only and can make the drawn cell look faster than the designed one.

What extraction adds is the interconnect. The device models already carry
intrinsic overlap capacitance, so gate-to-drain feedback is visible in both --
the extracted cell simply has the metal's share on top.

## Why there are device cells in this directory

`sky130_fd_pr__nfet_01v8_<suffix>.mag` and its pmos counterpart are *generated*
cells, not library cells. sky130's transistors are parameterised, so no drawn
cell exists in the PDK for a given width, length, finger count and guard ring
choice. Magic synthesises one on demand and names it by a suffix.

They are outputs of the generator, which rebuilds them and `inv.mag` together
and bit-identically -- same cell names, same geometry -- so none of the three is
committed. Deleting one on its own leaves `inv.mag` naming a cell that cannot be
read, which is what an empty layout with two named boxes looks like; `make
layout` restores the set.

## Checking the device sizing

The parameters magic extracts back out of the drawn shapes are what LVS
compares, so they are the ones worth reading -- not the values handed to the
generator, and not the defaults the device dialog opens with, which are the
process minimum rather than anything this cell uses:

```bash
make lvs
grep sky130_fd_pr inv_magic.spice
```
