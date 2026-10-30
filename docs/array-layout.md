# Capacitor placement

`make array-layout` generates `build/layout/sar_array.gds`. `make verify-layout`
checks the coordinates and streamed plate geometry against the electrical
ordering. `make drc-array` regenerates the GDS and checks it with both Magic
and KLayout through `sak-drc.sh` in the pinned tool container.

`layout/array_place.py` takes the resolution from `interface.N_BITS`, unit side
from `sky130.mim_side()`, and available dimensions from `template.analog_strip()`.
It obtains the number of rows and columns from `sky130.mim_fit()`. The strip's
short dimension sets the rows; the width is checked before any GDS is written.
Coordinates are local to the analog strip, whose origin is the tile origin.

Electrical slot `j` is placed at physical index `interleaved(N_BITS)[j]`.
Physical indices increase left to right, then bottom to top. Branch ownership
comes from `sar.branch_slices()`. The terminating electrical unit has a slot
and belongs to `branch_N_BITS`; perimeter and unused interior sites belong to
`dummy` and have no electrical slot. These populations must stay distinct:
the terminating capacitor contributes to total capacitance, whereas the edge
and filler dummies supply the pattern surrounding the electrical units.

Every unit has an isolated metal3 bottom plate enclosing the capm plate and
a via3 contact to a metal4 landing pad on its upper plate. Electrical units
share a metal4 row bus and a vertical spine beside the left dummy column.
The spine is labelled `TOP_PLATE`, corresponding to the schematic
array terminal `top`; the terminating electrical capacitor joins it too.
Perimeter and filler dummies retain isolated upper pads. Layers, grid, contact
size, and minimum pad area are declared in `tech/sky130.py` and checked against
the running PDK decks. The bottom plate shields the floating upper plate as
required by DD-13. Separate bottom polygons use `mim_pitch(shared=False)` on
both axes. The narrower shared-plate pitch requires an actual merged bottom
polygon; equal branch names alone do not provide it.

The GDS contains a hierarchy of branch cells with electrical slot properties
on their references. Readback uses the transformed capm polygons to recover
positions and the branch cells to recover ownership, without a coordinate
sidecar. Tests compare the recovered physical ordering with the golden
permutation, verify plate dimensions and enclosure, and deliberately swap
units to demonstrate that the comparison detects a placement defect.

Upper-net tests union the streamed metal4 polygons, find the connected island
under the `TOP_PLATE` label, and check that it reaches every electrical contact
and no edge or filler dummy. Removing a row connection and shorting a dummy
are injected defects the tests must detect. These are geometric connectivity
checks; extracted LVS and the upper net's resistance and parasitic capacitance
remain checks of the assembled circuit.

In KLayout, reload the generated GDS and show the hierarchy below `sar_array`.
Enable metal4 drawing (71/20) and its label purpose (71/5) to see the row buses
and side spine. Toggle metal3, capm and via3 to inspect the plate stack.

Branch interconnect, dummy ties, guard rings, switches, and final LVS belong
to subsequent layout work. The branch names identify intended ownership, not extracted
connectivity. DRC checks the isolated unit geometry and spacing at macro scope;
chip density, antenna closure, and full-tile connectivity require the assembled
layout. The placement study's gradient is a scalar in physical-index order;
folding that order into rows preserves the permutation but does not establish
cancellation of every gradient direction in the plane.
