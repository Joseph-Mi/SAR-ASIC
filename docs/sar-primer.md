# How this SAR converts, at the level of charge

A walk-through for building intuition. The physics and its consequences for
matching live in [model.md](model.md); this document takes the same equation
apart by hand. Every number in the worked example is illustrative, chosen so
the arithmetic is easy -- none of them is a design value.

---

## The parts

**Capacitor.** Two plates and an insulator. Push charge onto one plate and an
equal charge leaves the other: `Q = C * (V_plateA - V_plateB)`. Think of a
spring -- charge is how far it is compressed, voltage how hard it pushes back.

**Switch.** A transistor used as a valve: on, it joins two wires through a small
resistance; off, nothing flows.

**Comparator.** Two inputs, one bit out: is input A above input B?

**The law everything rests on.** A node that touches only capacitor plates and
switches that are off has no path for charge to leave by, so its total charge
cannot change, however the voltages around it move. A sealed balloon: squeeze
it and its shape changes; the air inside does not.

---

## The array

Every capacitor's top plate is wired into one shared node, `top`, which feeds
the comparator. Each bottom plate has its own switches.

```
             top (one node) ─────────────► comparator (+)
              │                            comparator (-) ◄── Vcm
     ┌────────┼────────┬────────┐
    ═╪═ 4C   ═╪═ 2C   ═╪═ 1C   ═╪═ 1C dummy
     │        │        │        │
   each bottom plate switched to  Vin  or  VREF  or  ground

   top ──/── Vcm        closed only while sampling
```

Branch `k` is `2^k` units. One extra unit, the dummy, brings the total to
exactly `2^N` units, so each branch is exactly a power-of-two fraction of it.
Without the dummy the fractions are `4/7, 2/7, 1/7` -- not halves.

**What one branch does to the top plate.** Flip branch `k`'s bottom plate from
ground to VREF and the sealed top plate rises by

```
dV_top  =  VREF * C_k / C_total
```

-- not by VREF. Lifting that bottom plate tries to drag the top plate with it,
and every other capacitor, whose bottom did not move, holds it back. It is a
capacitive divider: `C_k` against the rest. So the largest branch moves the top
plate by half the reference, the next by a quarter, and so on down to one LSB.
**That is what the ratios give you: the step sizes of the binary search.**

---

## One conversion by hand

Illustrative values: three branches (4C, 2C, 1C, plus a 1C dummy, 8C total),
`VREF = 1.6 V` so one LSB is 0.2 V, `Vcm = 0.8 V`, `Vin = 1.1 V`. The right
answer is `1.1 / 0.2 = 5.5`, rounded down: code 5, binary `101`.

**Sample.** Bottom plates at `Vin`, top plate at `Vcm`. Charge on the top node:
`8C * (0.8 - 1.1) = -2.4C`.

**Hold.** The top switch opens. `-2.4C` is now trapped. The input is captured
as charge.

**Trials, largest branch first.** Each trial switches the branches under test
to VREF and the rest to ground, and the top plate settles wherever keeps its
charge at `-2.4C`. That is always

```
V_top  =  Vcm  -  (Vin - V_DAC)
```

where `V_DAC` is the sum of the branch steps currently at VREF -- the guess so
far. Below `Vcm` means the guess is still low: keep the bit.

| Trial | Try | Guess `V_DAC` | `V_top` | vs `Vcm` | Bit |
|---|---|---|---|---|---|
| 1 | 4C | 0.8 | 0.5 | below: guess low | keep, 1 |
| 2 | 4C + 2C | 1.2 | 0.9 | above: overshot | drop, 0 |
| 3 | 4C + 1C | 1.0 | 0.7 | below: guess low | keep, 1 |

Code `101`. The final guess, 1.0 V, is within one LSB below `Vin`.

```
V_top
 0.9 ┤          ●             trial 2: overshot, drop 2C
 0.8 ┤─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   Vcm, the comparator's line
 0.7 ┤                ●       trial 3: low, keep 1C
 0.5 ┤    ●                   trial 1: low, keep 4C
     └────┬─────┬─────┬──
          1     2     3
```

The top plate zig-zags inward toward `Vcm` because each step is half the one
before -- the guess crossing `Vin`, seen as the top plate crossing `Vcm`.

### Why the largest branch goes first

Each branch is larger than all the smaller ones together (`4C > 2C + 1C`), so
once the largest is decided nothing after it can overturn that: the rest only
refine inside the half already chosen. Starting from the smallest would learn
almost nothing per trial and let later, larger steps undo earlier decisions.
A balance with weights of 4, 2 and 1 kg is worked the same way: the 4 goes on
first.

---

## The loop with the FSM

```
   sar_fsm:  trial = settled | (1 << bit_index)       ◄─── cmp_out
                │                                            │
            dac_b (1 = VREF, 0 = ground)                     │
                ▼                                            │
      bottom-plate switches ──► top plate ──► comparator vs Vcm, on cmp_clk
```

Each trial is a SETTLE phase and an EVALUATE phase: first `dac_b` changes and
the charge redistributes; then `cmp_clk` rises and the comparator decides. A
kept bit is folded into `settled`; a dropped one returns that branch to ground
on the next trial. After the smallest branch, `settled` is the code. The
cycle-by-cycle shape is `protocol.py`'s, and the RTL is tested against it.

### Where the two halves meet

Every arrow in that loop is a wire. `dac_b[k]` leaves a flip-flop in the
synthesised FSM, runs as metal to the edge of the digital macro, and continues
as metal to the gate of branch `k`'s switch. A logic one is that wire pulled to
the supply by the flip-flop's output driver; the switch turns on because its
gate is high, nothing more. `cmp_out` runs the other way, from the latch to a
flip-flop's input, which reads it as one above its switching point. The
symbol names both ends of every such wire, which is what lets the two halves
be built apart and meet at the same metal; LVS checks that the drawn metal
joins them the way the schematic says.

`sim/loop.py` simulates exactly that: the RTL compiled into the circuit
simulation as one element, a driver on each wire it sends and a threshold gate
on each wire it reads. Nothing replays a decision -- every trial word is the
FSM's own response to the comparator. `hdl/verification/integration/` checks
the codes against the model, the handover from sampling straight to the first
trial word (the rule closing *Where the top plate is referenced*), and that
the clock the pin's settling law allows is the one the loop needs.

---

## Between conversions: there is no discharge step

Sampling *is* the reset. Closing the sampling switches forces every capacitor
to `Vcm - Vin` whatever it held before: bottom plates are dragged to `Vin`, the
top plate to `Vcm`, and the previous conversion's charge flows out through the
switches into the `Vin` and `Vcm` sources. Like overwriting a register rather
than clearing it first.

What that costs is time. The overwrite is an RC charge through the switch and
the pin, and it has to finish to within half an LSB:

```
t_sample  >  (N + 1) * ln 2 * tau,     tau = (R_pin + R_switch) * C_total
```

If sampling ends early, part of the last conversion's residue survives into
the next -- a memory effect that shows up as a code depending on the previous
input. The same charge flowing back out of the array is a kick on the `Vin`
source at the start of every sample; whatever drives the pin has to absorb it.

---

## Vin, VREF, Vcm, VDD

| | What it is | Where it comes from |
|---|---|---|
| `Vin` | the signal being measured; varies | an analog pin, from outside |
| `VREF` | full scale: the height of the ruler. `Vin` is converted over 0 to `VREF` | its own analog pin |
| `Vcm` | the top plate's reference: where the ruler's zero is placed. Fixed, never the signal | its own analog pin, driven and decoupled off-chip |
| `VDD` | the supply the transistors run from | the supply pin |

**`VREF` is not `VDD`**, even if the two end up at the same voltage. The array
draws a burst of charge from `VREF` at every bit trial, largest at the first,
and it has to be back to its final value before the comparator fires. A supply
shared with switching logic is not quiet enough, and the pin's series
resistance slows its recovery; a pin of its own is what makes it a reference.
`VREF` also has to be passable by its switch: an NMOS cannot pass a voltage
near its own gate drive, so a reference near the supply needs a PMOS or a
transmission gate.

---

## Where the top plate is referenced: ground or `Vcm`

The comparison is `V_top` against the same voltage the top plate was sampled
at, so that voltage cancels out: both choices decide identical codes. They
differ in *where the node travels*. The widest swing is the first trial,
plus or minus half the reference around the sampling reference:

| | Referenced to ground | Referenced to `Vcm = VREF/2` |
|---|---|---|
| Codes | same | same |
| Top plate range | `-VREF/2 ... +VREF/2` | `0 ... VREF` |
| Junction diodes on the node | every NMOS switch touching the node has an n+ region in the grounded substrate. Below roughly -0.5 V that diode conducts, and the sealed charge leaks: the conversion is wrong near full scale | stay reverse-biased |
| NMOS-input comparator | both inputs near 0 V, below threshold: nothing to amplify | both inputs mid-rail, biased on |
| Sampling switch | full gate drive | less gate drive: size it up, or use a transmission gate |
| Extra voltage | none | `Vcm` has to be supplied |

The design references to `Vcm` (`VCM_FRACTION` in `sar.py`): ground breaks the
two things the converter depends on -- sealed charge and a working comparator
-- on real inputs, and `Vcm`'s costs are ones that can be engineered.

One rule survives the choice: leaving the sample phase, the bottom plates must
go straight to the first trial word. Passing through "all bottom plates at
ground" on the way puts the top plate at `Vcm - Vin`, down to minus half the
reference, and the diodes conduct even with `Vcm`.

---

## Ending the sample: which switch lets go first

The switches are transistors, and an on transistor holds a thin layer of
charge under its gate. Turning it off, that charge has to go somewhere: about
half comes out of each end, onto whatever the switch was joined to. How much
depends on the voltage the switch was passing.

Two sets of switches let go when sampling ends: the top switch, which holds
the top plate at `Vcm`, and the input switches, which hold every bottom plate
at `Vin`. The order matters.

- **Top switch first.** The instant it opens, the top plate is sealed and its
  charge is fixed. It passed `Vcm`, the same voltage every time, so it leaves
  the same charge every time: an offset, which a measurement removes. The
  input switches let go afterwards; their charge lands on bottom plates that
  are about to be driven to `VREF` or ground anyway, and the sealed top plate
  never sees it.
- **Any other order.** The input switches' charge -- which depends on `Vin` --
  gets trapped with the sample. An error that varies with the input is
  distortion, and no single correction removes it.

This is bottom-plate sampling. The block makes the order itself from the one
`sample` wire, with a phase generator in which each switch's control line can
only move once the line it must follow has reached the level where its
switch is off: the order holds however slow any line is, because it waits for
the line rather than for a delay someone sized. `sim/tests/test_sampling_phases.py`
shows both halves -- the order deciding offset against distortion, and the
generator keeping the order when a line is slowed many times over.

---

## What the ratios decide

Every threshold is `VREF` times a ratio of capacitances. That is why absolute
capacitance cancels -- a process that makes every capacitor large makes none
of the ratios wrong -- and why unequal ratios are the converter's accuracy
error: uneven steps are DNL, worst at mid-scale where the largest branch
switches in and every other switches out. [model.md](model.md) and the yield
study take it from there.

A parasitic from the top plate to a fixed potential is a different matter. At
every decision the node is back at `Vcm`, exactly where it was sampled, so the
parasitic holds the charge it started with and moves no threshold. It divides
down the swing the comparator has to resolve, and that is its whole cost.

---

## Further reading

- Analog Devices technical article on SAR and flash ADCs --
  https://www.analog.com/en/resources/technical-articles/successive-approximation-registers-sar-and-flash-adcs.html.
  Textbook treatments usually draw the capacitive DAC referenced to ground --
  the left-hand column above -- because it makes the algebra shortest.
