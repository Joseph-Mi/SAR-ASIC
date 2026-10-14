# Which artifact is authoritative

Every part of this chip is described more than once: as a generator, as a
schematic, as a netlist, as a layout. Exactly one of those descriptions is
written by hand. The rest are produced from it by a tool and checked against
it, and none of them is ever edited.

Two hand-maintained descriptions of the same circuit cannot be kept equal.
Each one is self-consistent, each reads correctly on its own, and the
disagreement between them is visible in neither -- only in silicon, or in a
check that compares them. So the question for any artifact is not whether it
is correct but whether it is the authored one.

## The rule

An artifact is authored, generated, or stale. There is no fourth kind, and a
generated artifact that someone has edited is stale whatever it says.

A generator is as good an author as a drawing. What disqualifies an artifact
is not how it was made but being a copy that someone maintains by hand.

## Where authority sits, and where it moves to

| What | Authored | Produced from it |
|---|---|---|
| The boundary between the halves | `reference/interface.py` | the xschem symbol, the RTL's ports |
| The capacitor array | its generator | netlist, layout |
| The comparator, until its topology is fixed | its generator | netlist |
| The comparator, from then on | its xschem schematic | netlist, layout |
| The digital half, until synthesis | `hdl/rtl/` | nothing yet |
| The digital half, from then on | the gate netlist | placement, routing, layout |
| The tile | the two hardened halves | the merged layout |

Authority moves three times, and each move is an event with a date rather than
a drift:

**At the comparator's topology freeze.** A generator can sweep a width across
twenty values; a drawing cannot, so sizing is done on a generator. Once the
transistors and their connections stop changing, the schematic is drawn with
its sizes as parameters, and authority moves to it the moment it exists. It
has to: layout is compared against a schematic, so a generator that disagreed
with the schematic would be a comparison failure belonging to nobody. The
generator keeps its other job, which is driving the benches, and stops
emitting a netlist that anything is built from.

**At synthesis.** The gate netlist becomes authoritative and the RTL stops
being the reference, because what is placed, routed and compared against the
layout is the netlist. The RTL's correctness transfers to it only through a
proof that the two are the same logic.

**At layout.** Nothing becomes authoritative here, which is the point: layout
is always the generated side of a comparison, never the authored one.

## What proves each handover

A handover is only as good as the check that one artifact still says what the
other does, and each check compares structure rather than text. Two netlisters
format the same circuit differently and a difference in text is not a
difference in circuit.

- Symbol against interface: a test reads both and fails on disagreement.
- Schematic against generator: `netgen` compares the two netlists as graphs,
  so a swapped drain and source or a width typed once fails it.
- Layout against schematic: the same tool, as LVS.
- Gate netlist against RTL: an equivalence proof, not a simulation. Synthesis
  is a program with bugs, and a bench only samples the inputs it was given.

## What is kept

The authored artifact, and the check. A generated netlist belongs in a build
directory: a copy in the tree is a second description of the circuit, which is
the thing this page exists to prevent, and it will be read as authoritative by
whoever finds it next.

One exception, at signoff. What is submitted is frozen and archived, netlist
included, because it must be reproducible when the tools that made it have
moved on. That copy is a record of what was built, and is never an input to
anything.
