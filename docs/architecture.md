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

**`reference/`** -- the golden model and the contract between the halves: what
a conversion is, when each pin moves, and which wires cross the boundary. Both
the RTL and the analog simulation are judged against it, which is why it sits
outside `hdl/`: it is not the digital half's, it is the chip's.

**`model/`** -- the physics the tests hold the circuit to: settling, charge
injection, the common-mode source, mismatch, and the static and dynamic
metrics of an array. Laws and measures, each a function of its inputs.

**`studies/`** -- the questions asked of the model: the yield and noise sweeps,
their committed baselines, and the plots. A study is run, not imported;
nothing depends on one.

**`sim/`** -- the analog block as a generated netlist, the benches that drive
it, the Verilog co-simulation that closes the loop, and the measurements the
tests make of it. It imports the model for its expectations and the reference
for its interface.

**`hdl/verification/`** -- the RTL under test: cocotb benches for the digital
half, and the closed loop that runs the RTL against the analog block.

`hdl/rtl/` is Verilog and imports nothing. `sandbox/` holds disposable
experiments that may use any layer and that no layer may use.

## Where a new file goes

Ask what it needs to import, and put it in the lowest layer that has all of
it. A fact about the process goes in `tech/`; a formula with no circuit in it,
in `model/`; anything that builds or runs a netlist, in `sim/`. If a file
seems to need a layer above its own, one of the two is in the wrong place.
