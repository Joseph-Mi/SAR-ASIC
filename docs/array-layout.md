# Capacitor array layout

`make array-layout` generates `build/layout/sar_array.gds`. `make verify-layout`
checks placement, streamed plate geometry, and extracted conductor connectivity.
`make drc-array` regenerates the GDS and checks it with both Magic and KLayout
through `sak-drc.sh` in the pinned tool container.

## Placement and contact access

`layout/array_place.py` takes the resolution from `interface.N_BITS`, unit side
from `sky130.mim_side()`, and available dimensions from `template.analog_strip()`.
The short dimension sets the rows; the width check reserves room for the
contacted field and the branch output trunks. Coordinates are local to the
analog strip, whose origin is the tile origin.

Electrical slot `j` is placed at physical index `interleaved(N_BITS)[j]`.
Physical indices increase left to right, then bottom to top. Branch ownership
comes from `sar.branch_slices()`. The terminating electrical unit has a slot
and belongs to `branch_N_BITS`; perimeter and unused interior sites belong to
`dummy` and have no electrical slot. The terminating capacitor contributes to
total capacitance; the edge and filler dummies supply the surrounding pattern.

The bare-unit pitch from `sky130.mim_pitch()` is a lower bound once contacts
and wires are present. `layout/array_geometry.py` derives the horizontal pitch
from the metal3 contact tab's reach and its separation from the neighbouring
capacitor. It derives the vertical pitch from the row-channel track count and
via landing widths. Rows are fitted with that pitch, not with the bare-unit
bound. Both the plate locations and the final routed GDS are checked against
the analog strip.

Every unit has a metal3 bottom plate enclosing capm and a via3 contact to a
metal4 landing pad on its upper plate. A metal3 tab reaches left of capm to a
via2 contact and metal2 landing. The via2 cut stays outside the capacitor;
Magic's effective contact edge includes the enclosure that must be added
back when computing the drawn-cut clearance. Perimeter and filler units use
the same contacted geometry as electrical units but retain isolated terminals.
The layers, grid, spacings and enclosures are declared in `tech/sky130.py` and
checked against the running PDK decks.

## Upper and bottom connections

Electrical upper plates share metal4 row buses and a spine beside the left
dummy column. The spine is labelled `TOP_PLATE`, corresponding to the schematic
array terminal `top`; the terminating electrical capacitor joins it too.
Perimeter and filler dummies retain isolated upper pads.

Each electrical bottom plate reaches metal2 through its outside-capm via2.
A metal2 drop reaches the row track assigned to its branch, where a via1 joins
it to a horizontal metal1 bus. Row buses join vertical metal2 trunks to the
right of the field through via1. A crossing without a via is not a connection.
The trunks are labelled `b0`, `b1`, and so on for the weighted branches, and
`bd` for the terminating bottom terminal, matching the schematic's array
boundary. They are access points for the sampling and reference switches;
`bd` is not hard-wired to ground because the terminating unit also samples.

Track spacing includes the landing pads rather than only minimum-width wire.
The output margin and row pitch are reserved before placement, so adding
routing cannot silently extend a valid plate placement outside the strip.
Bottom connections run under the capacitor stack; metal3 shields the floating
upper plate as required by DD-13. Separate metal3 polygons use the distinct-net
spacing even when their branch names match. Shared-plate pitch requires an
actual merged polygon, not just a shared electrical owner.

## Checks and remaining circuit work

GDS references carry electrical slot properties. Readback uses transformed
capm polygons to recover positions and branch cells to recover ownership,
without a coordinate sidecar. Tests compare the physical ordering with the
golden permutation and check plate geometry and enclosure.

Upper-net tests union streamed metal4 polygons and identify the island under
`TOP_PLATE`. It must reach every electrical contact and no edge or filler
dummy. Removing a row or shorting a dummy are injected defects it must detect.

Bottom-net tests use KLayout's conductor extraction across metal1, via1,
metal2, via2 and metal3. Probing each bottom plate and labelled output must
recover exactly the slot sets in `sar.branch_slices()`, plus the separate
terminating unit. Distinct branch labels must identify distinct extracted
nets, and no branch may reach a perimeter or filler dummy. Removing a via2
must disconnect its unit, and an injected branch bridge must merge the nets.
This is extracted conductor connectivity, not capacitor-device LVS.

Dummy ties, guard rings, switches, capacitor-device LVS and parasitic
extraction remain circuit work. DRC runs at macro scope; chip density,
antenna closure and full-tile connectivity require the assembled layout.
The row/trunk routing establishes connectivity, not a measured bound on
branch resistance, settling or coupling. The placement study's gradient is
a scalar in physical-index order; folding that order into rows preserves the
permutation but does not establish cancellation of every gradient direction
in the plane.

## Inspecting the layout

Reload the generated GDS in KLayout and show the hierarchy below `sar_array`.
Enable metal4 drawing and its label purpose to see the upper row buses and
spine. Enable metal1, metal2 and the via layers to see branch collection and
the labelled outputs on the right. Toggle metal3 and capm to inspect each
bottom contact tab and its separation from the capacitor plate.
