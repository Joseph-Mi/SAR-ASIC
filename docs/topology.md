# Topology, and how a single-ended node is protected

What kind of converter this is, why it is that kind and not another, and what
the layout and the RTL owe the one sensitive node a single-ended design has.
The decisions are recorded in the project instructions as DD-12 and DD-13;
this page is the reasoning.

---

## What the converter is

| Choice | Taken | Rejected |
|---|---|---|
| Signal path | single-ended: one array, one top plate | fully differential |
| Switching | conventional binary: each bottom plate at VREF or ground | Vcm-based (three levels), monotonic, split array |
| Sampling | bottom-plate, phases from the self-timed generator (DD-11) | top-plate |
| Top plate referenced to | `vcm`, an analog pin (DD-08, DD-10) | ground |

The comparator is a StrongARM, which has two inputs whatever the array does.
In a single-ended design they are the top plate and `vcm`. The two outputs that
cross to the digital half (DD-04) are the latch's, not the signal's.

## Where each analog pin is used

| Pin | Used when | For |
|---|---|---|
| `vin` | sampling | the input switches drive every bottom plate to it |
| `vref` | every bit trial | the bottom plates the guess selects are driven to it |
| `vcm` | **sampling and every decision** | the top switch holds the top plate at it while sampling; the comparator's other input is it at every strobe |

`vcm` is not optional. It is half of every comparison and the level the array's
charge is sampled against. Take it away and the top plate has to be referenced
to ground, which DD-08 rules out, or to an on-chip source, which the Vcm-source
study measured and ruled out (DD-10).

### What `vcm` asks of whatever drives it

Only steadiness within one conversion. The value sampled and the value compared
against cancel, so their difference is the only error (`threshold_shift` in
`model/common_mode.py`): a steady but wrong `vcm` converts exactly as the model
does, and `test_a_steady_but_wrong_vcm_converts_exactly_as_the_model` holds
the circuit to that.

It moves because sampling pushes charge into it, in proportion to how far the
input moved since the previous conversion. The kick settles through the pin's
resistance times the array, the same law sampling `vin` already obeys, provided
the off-chip source is stiff: a divider from the reference source with a large
ceramic capacitor at the pin, or a bench supply. `drift_within_conversion`
sizes the capacitor. An unbypassed divider is the failure the study found.

### What `vcm` gives the bench

Because it is a pin, it is a knob that costs no area:

- **Comparator offset against common mode.** Step `vcm` with a fixed input and
  watch the code. The array cancels a steady `vcm` exactly, so whatever moves
  is the comparator: every threshold shifts together by its offset's change,
  the curve M5 predicts. Thresholds that move by different amounts are not the
  comparator -- something on the top plate is not a clean capacitor.
- **Where the top plate starts to leak.** At full scale the top plate sits near
  ground at the first trial. Lowering `vcm` pushes it below ground, and the
  codes that go wrong mark where the top switch's junction starts to conduct.
  The same knob, raised a little above half the reference, is a fix for it
  on silicon.

## Why single-ended

A differential converter (two arrays, the comparator seeing one top plate
against the other) doubles the swing, rejects noise that reaches both arrays
alike, and cancels even-order distortion and matched charge injection. None of
those is what limits this design:

- **Noise** has margin: the unit capacitor is set by the smallest geometry the
  process draws, not by kT/C (`docs/model.md`).
- **Charge injection** is already handled. The top switch passes a constant
  level, so its injection is an offset; bottom-plate sampling keeps the input
  switches' injection off the sample (DD-11).
- **What does limit it** is time: how fast the switches and the pins settle
  the array, at the slow corner, which sets the clock. A differential array has
  twice as many switches to size and settle, and twice the capacitance on
  the shared reference pin.

What differential would cost:

- **A fourth analog pin**, and TinyTapeout charges more for each pin past the
  second.
- **A differential source on the bench.** Signal generators and DACs are
  single-ended; a balun or a driver amplifier is one more thing that can be
  wrong at bring-up, in front of the thing being characterised.
- **Most of M3 again**: the model, the settling laws, the generator, the
  acceptance runs and the interface.

**Area is not the argument.** `docs/floorplan.md` sizes the array well inside
the analog strip, and a second one would still fit. Single-ended is chosen for
risk and schedule, not because differential cannot be built here. It is the
natural upgrade for a second tapeout, once one array has been measured in
silicon: the comparator does not change, and the interface gains a second
bottom-plate bus.

## Why conventional switching, not Vcm-based

Vcm-based switching rests every bottom plate at `vcm` and moves one branch to
VREF or ground per trial. It halves the array, decides the first bit without
switching, and spends far less energy per conversion. Here:

1. **It turns `vcm` into a reference.** A step up is VREF − Vcm, a step down is
   Vcm. Unless `vcm` is exactly half the reference the two differ, which is
   INL. The pin that tolerates being wrong today would have to be accurate,
   and it would carry charge on every trial, not only at sampling.
2. **It adds the hardest switch sky130 has.** A switch passing mid-rail is where
   both the NMOS and the PMOS are weakest: the NMOS's source is high enough for
   body effect to raise its threshold, and the PMOS's gate drive is only the
   level it passes.
3. **It changes the contract.** `dac_b` becomes three levels per branch, so the
   protocol, the model, the RTL and the frozen interface all move.

The halved array is its one real gain, and area does not bind. Revisit if the
floorplan stops fitting, and only then.

## The 3.3 V supply

TinyTapeout offers an analog supply at 3.3 V to a project that asks for it
(the `_3v3` template). Switches built from the thick-oxide devices and driven
from it have far more gate overdrive than the core devices have from the core
supply, at the cost of level shifters on `dac_b` and larger devices.

The core devices are enough: measured with the sky130 models, the reference
switch settles the first trial inside a clock at the slow corner, as the
thick-oxide NMOS and the low-threshold PMOS do. The 3.3 V supply is kept as
the answer if a switch at some corner turns out short of gate drive, not as a
plan.

---

## Protection

A differential design gets rejection of shared disturbances for free, from
symmetry. A single-ended one has to get it from layout, supplies and timing.
There is one node that matters: the top plate, which floats between sampling
and the result and turns any charge coupled onto it into a threshold shift.
`vcm`, the comparator's other input, is the second: it is stiff at low
frequency (the pin, the off-chip capacitor) but only as quiet on-chip as its
routing.

Coupling onto the top plate is a parasitic capacitance to something that
moves. A parasitic to something that does *not* move costs no threshold (M3
Step 1): it only divides the comparator's swing, a comparator-budget item. So
the pattern throughout is **shield to something steady**, and pay for it in
comparator margin, never in linearity.

### Below: the substrate

- **The top plate is the MiM capacitor's upper plate.** The lower plate, on
  met3, is a driven bottom plate and sits between the top plate and the
  substrate, so the substrate couples to a node that is driven, not to the one
  that floats.
- **The comparator's NMOS devices sit in deep n-well**, isolating their body
  from the digital half's substrate current.
- **Substrate ties under and around the array**, to the analog ground.

### Around: guard rings and distance

- **A double guard ring** around the array and the comparator together: p+
  substrate tap to ground inside, n-well tied to the supply outside. The inner
  ring collects majority-carrier noise, the outer one minority carriers.
- **The dummy ring** around the array, already needed for matching, grounded,
  shields the edge units laterally.
- **Distance from the digital macro.** The floorplan already puts the halves at
  opposite edges; the gap between them is where the rings go.

### Above: routing

- **Nothing crosses the array** except its own wiring. No digital line, no
  clock. Metal 5 is not ours to use, so there is no shield above; keeping the
  space clear is the only protection.
- **Power stripes** are vertical met4 across the whole tile. Place them to
  avoid the array and the comparator, not over them.
- **The comparator's two inputs are routed as a pair**: same layers, same
  length, side by side, shielded together. A disturbance that reaches both is
  common mode to the StrongARM, which rejects it. This is the part of a
  differential design's symmetry a single-ended one can keep.
- **`dac_b` buffer chains sit at the array's edge**, each next to the branch it
  drives, so the fast edges travel the shortest distance near the array.

### Supplies

- **One ground, star-routed.** The tile has a single ground; the analog half's
  ground connects to it at one point, and the comparator's and the array's
  returns do not share a conductor with the digital half's.
- **Decoupling on the comparator's supply**, a MOS capacitor next to it: the
  strobe draws a current spike exactly at the decision.
- **On-chip capacitance on `vref` and `vcm`** only where the settling laws say
  it helps. A capacitor on a pin shrinks each kick but slows its recovery
  through the pin resistance; `drift_within_conversion` and the reference
  settling law size it. It is not assumed to help.

### Time: the cheapest protection

A disturbance that has died away before the strobe costs nothing, because the
comparator decides once, on the edge (the latched comparator of M3 Step 4a).
That holds for bounce, where the aggressor returns to where it was: supply,
ground and substrate. It does not hold for a line that switches and stays
switched -- the charge it coupled stays on the top plate -- which is why
nothing crosses the array. So the rule is **no digital activity near the
strobe**:

- One clock domain (already decided): every digital edge lands at a known time
  relative to the strobe, never on it.
- **An external SPI clock is asynchronous.** Synchronise it into the system
  clock, and hold register writes that reach the analog half until a
  conversion is over.
- **Output pads switch large currents.** In normal operation the result pins
  change only when a conversion ends. The DFT modes that stream the
  comparator or the SAR state to the pads toggle them mid-conversion; they are
  for observing the digital half and the comparator's decisions, and their
  codes are not accuracy measurements.

### Pins

- **`vin` stays inside ground..VREF.** Beyond it, the top plate at the first
  trial leaves the supply range and the top switch's junction conducts. The
  board provides the limit: a series resistor and clamp diodes to the
  reference and ground, outside the chip.
- **No large on-chip protection structure on `vin`.** Its junction capacitance
  loads the input and its leakage depends on the input's level. The analog
  path's own ESD provision is TinyTapeout's; confirm it against the spec
  before relying on the board alone.

### Considered, not taken

- **A replica node on the comparator's `vcm` input**: `vcm` sampled onto a
  scaled capacitor at the same instant, so both inputs see coupling in the same
  ratio. It cancels only as well as the layout matches, and the paired routing
  above gets most of the benefit for none of the area. Revisit if silicon shows
  coupling the pair does not reject.

---

## When to re-derive this

- The floorplan stops fitting: Vcm-based switching becomes worth its costs.
- A switch moves to the 3.3 V supply: the level shifters join the protection
  list as a new source of edges.
- Silicon shows threshold noise that correlates with the digital half's
  activity: the paired routing was not enough, and the replica is next.
- A second tapeout: differential, starting from this array.
