# Which artifact is authoritative

Every part of this chip has electrical and physical descriptions: a model,
a schematic, a netlist and geometry. Each domain has one maintained source;
exports from that source are generated artifacts and are not edited.

The schematic defines the intended electrical circuit. The layout source
defines physical geometry, maintained either in a generator or an editable
layout cell. These are different domains, held together by extraction and
LVS. A hand-maintained schematic and a hand-maintained layout are valid;
independently editing a generated layout and its generator is not.

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
| The comparator circuit, from then on | its xschem schematic | netlist |
| Custom layout geometry | its designated editable cells | exported layout, extracted netlist |
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

**At layout.** The schematic stays the electrical reference; the designated
layout source owns geometry. For a scripted cell the source is its generator.
For a hand-maintained cell it is the tracked editable layout. GDS can be an
export or an editable source, depending on the declared ownership and tool.
A transfer to hand maintenance must preserve the editable source outside the
build directory and disable ordinary regeneration of that source. The transfer
is complete only when checks validate exports from the maintained artifact,
not a freshly generated substitute.

The capacitor array remains generator-owned. `make check-layout LAYOUT=...`
validates a supplied saved GDS without regeneration; `make validate-layout`
also checks a private DRC snapshot. Their unit metadata contract and scope
are in `docs/array-layout.md`. These commands support checking edited exports;
they do not transfer ownership or establish device LVS or parasitic accuracy.

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
