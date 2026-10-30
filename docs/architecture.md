# How the repository is layered

The layers, and which may import which, are declared once, in
`tests/test_layers.py`, and `make lint` fails when an import runs the wrong
way. This page is the reasoning behind that list; the list itself is the test.

## The rule

A layer may import only the layers beneath it. Nothing lower ever learns that
something higher exists, so a change at the top cannot break the bottom, and
the bottom can be read and tested alone.

Every source folder shares one import path, so a module's name is its whole
identity. The same test fails when two modules share a name, or when one takes
a name the Python standard library already has -- both have happened, and both
broke imports silently.

## The layers, bottom first

**`tech/`** -- what the process is: device names, the sizes sky130 draws, the
capacitor matching it gives. It knows nothing else in the repository. A second
copy of a process number anywhere else is the drift this layer exists to stop.

**`figures/`** -- how a picture looks: the palette, the type, the canvas and
the one function that writes a file. It knows nothing else in the repository,
and everything that draws reads it, which is why it sits at the bottom rather
than beside the scripts that use it.

**`reference/`** -- the golden model and the contract between the halves: what
a conversion is, when each pin moves, which wires cross the boundary, how long
a board has to hold a pin for the chip to see it, and what the converter asks
of its comparator -- the margin, the time and the noise, which are the
converter's half of a comparator specification and can be written before one
exists. Both the RTL and the
analog simulation are judged against it, which is why it sits outside `hdl/`:
it is not the digital half's, it is the chip's.

**`model/`** -- the physics the tests hold the circuit to: settling, charge
injection, junction capacitance, the common-mode source, mismatch, what a
moving input costs, what a conversion costs the reference, and the static and
spectral metrics of an array. Laws and measures, each a function of its
inputs.

**`studies/`** -- the questions asked of the model: the yield and noise sweeps,
their committed baselines, and the plots. A study is run, not imported;
nothing depends on one.

**`sim/`** -- the analog block as a generated netlist, the benches that drive
it, the Verilog co-simulation that closes the loop, the schematic sheets
generated from those netlists, and the measurements the tests make of all of
it. The sheets sit here rather than in a layer of their own because a sheet is
checked by netlisting it back and comparing it against the netlist the benches
simulate, so drawing one and running one are the same layer's work: `sheet.py`
is the editor's vocabulary and knows no circuit, and `schematic.py` and
`cap_array.py` each hold one circuit's arrangement. It imports the model for its expectations and the reference
for its interface. A measurement too slow to take on every run is swept here
and its baseline committed beside the code that draws it, the same way a study
commits one: the sweep belongs to whichever layer can run the thing being
swept, and running a netlist is this one's.

**`layout/`** -- physical placement and stream-out. It takes electrical unit
ordering from the model and geometry from the process and tile template.
Readback checks the emitted geometry against the same electrical ordering;
branch connectivity is checked by extraction once routing exists.

**`hdl/verification/`** -- the RTL under test: cocotb benches for the digital
half, the closed loop that runs the RTL against the analog block, and the
formal properties, which are the only place SystemVerilog is used and which
are bound to the design from outside it.

`hdl/rtl/` is Verilog and imports nothing. `sandbox/` holds disposable
experiments that may use any layer and that no layer may use.

## Where a new file goes

Ask what it needs to import, and put it in the lowest layer that has all of
it. A fact about the process goes in `tech/`; a formula with no circuit in it,
in `model/`; anything that builds or runs a netlist, in `sim/`. If a file
seems to need a layer above its own, one of the two is in the wrong place.
