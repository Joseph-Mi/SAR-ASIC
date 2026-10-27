# What the comparator is, and what its noise costs

The comparator is a StrongARM latch: a clocked differential pair whose drains
are capacitors, followed by a cross-coupled pair that regenerates whatever
difference the first stage built. It compares the array's top plate against
`vcm` and drives the two wires the controller reads.

The circuit is `sim/strongarm.py`, which every bench here builds from, and
`xschem/strongarm.sch`, which is that netlist drawn: generated from it to
begin with, arranged by hand since, and held to it by a test that netlists
the sheet back and compares every device. The drawing a reviewer reads and
the circuit the numbers below were measured on are therefore the same one,
and the sheet is what LVS will be handed. Holding the two together by
netlisting rather than by generating is what lets the drawing be drawn: a
sheet is read by a person, so its arrangement is a design artifact of its
own, and the only thing that has to be mechanical about it is that it is the
right circuit.

The two halves do different jobs and only one of them is a design problem.
Regeneration sets how long a decision takes and nothing else -- it is positive
feedback on a difference that already exists, so it adds no noise worth
counting and no offset the first stage has not already made. Everything this
page is about happens in the first stage.

## The two phases

While the strobe is low the tail is off and four devices clamp both
integration nodes and both outputs to the same rail. Nothing is remembered:
a latch that kept charge between trials would be hysteresis inside a binary
search, which walks the code rather than adding noise to it.

While the strobe is high the tail turns on and its current splits between the
two input devices, charging the integration nodes as capacitors. That is the
integration, and it ends not on a clock edge but when the cross-coupled pair
takes over -- from then on the circuit is amplifying its own output and the
input is no longer being listened to. The length of that first window is the
whole of the input stage's story.

## Why the noise is a capacitance

The pair converts an input difference into a current difference through its
transconductance, and that current integrates onto the nodes for the length
of the window, so the signal is a charge: `gm * dV_in * t_int`.

Each input device's channel is a noisy resistor whose current noise
integrates onto the same node over the same window. Dividing the noise charge
by the signal charge per volt refers it to the input, and what comes out is

    sigma_in = sqrt(4kT*gamma / (gm * t_int))

A transconductance times a time is a capacitance, so this is kT/C noise on a
capacitor the latch builds out of gain and time. `model/latch.py` carries the
law and `sim/strongarm.py` measures the two quantities it needs; the test
asserts on their product rather than on the volts, because the product is
what a simulator yields and the volts appear only once an excess noise factor
is assumed.

## What a designer can actually move

Substituting the time the node takes to swing, `t_int = C_node*dV/I`, removes
the current from the law entirely:

    sigma_in = sqrt(4kT*gamma / (efficiency * C_node * dV))

where efficiency is `gm/I`. Current buys speed and never quiet. Measured on
this circuit, eight times less tail width improves the noise by a quarter --
and only because the pair moves toward weak inversion on the way, which
raises the efficiency. Fifty femtofarads on the integration node improves it
twice over.

So the levers are the efficiency, the charge swung on the node, and nothing
else. Two of them are nearly free here: the node's capacitance sits on the
input devices' drains, so growing it costs energy and integration time but no
input capacitance, while growing the input pair would feed straight back into
the top plate's parasitic and divide the array's own swing. Integration time
is the one thing this converter has in excess at the corners it is specified
over, because the latch decides in tens of nanoseconds inside a strobe of well
over a hundred. Slow cold silicon is where that stops being true, and the last
section of this page is what buying it back would cost.

## Why the tail is not a switch

The tail's gate could be the strobe, and in the latch this topology is named
for it is. That is what makes a StrongARM draw no static current: it is idle
between trials, and a biased tail would not be. The comparison with an
amplifier does not carry over either -- an amplifier needs a defined
small-signal gain in steady state, so its tail current must come from a
reference, while a comparator has neither a steady state nor a gain to hold,
only a sign to get right.

What a strobed tail costs is a current set by the overdrive of a whole
supply, which is the supply's number rather than the design's. Measured
across the process window it varies by more than an order of magnitude, and
both ends are a problem: too much current drives the pair into strong
inversion where the efficiency collapses, and too little stretches the
integration until the latch no longer resolves inside the conversion clock.
No amount of capacitance on the integration node settles both, because the
two pull opposite ways.

So the tail is a mirror instead, and the strobe hands it its gate: held at
the rail while the latch precharges, handed the mirror to evaluate on. One
device remains in the current path, because the tail node has to sit well
above the common mode for the pair to conduct at all and a stacked cascode
would take the headroom that leaves.

## What the mirror is referenced to, and why it is the array's own

The current comes from a device gated at the converter's reference. A gate
draws no current, so reading a voltage off that pin costs the array nothing
-- which is what makes it safe to hang on the pin the array's own charge
comes from, and why this is not the static draw that an on-chip divider was
rejected for.

The reason it is that reference rather than a self-contained one is the
figure of merit. What the noise depends on is a transconductance times a
time, and the two carry the process's mobility in opposite directions. From
a device gated at a fixed voltage, the current carries mobility, the
transconductance carries it once more, and the integration time carries it
inversely, so in the product it cancels:

    gm * t_int  proportional to  C_node * dV / (V_ref - V_t)

Only the threshold is left. A constant-transconductance reference -- the
textbook circuit for biasing a pair, four devices and a resistor -- holds the
transconductance itself constant instead, which leaves the integration time
carrying mobility alone and so the product with it. It is the right circuit
when transconductance sets a bandwidth or a gain; here it stabilises the
wrong quantity. It also has two stable operating points, one of them at zero
current, so it needs a startup device and a proof that it comes up.

What referencing the array's voltage costs is a coupling that did not exist
before: that pin now sets the tail's current as well as the full scale, so an
error in it moves the comparator's noise and not only the converter's gain.
The sensitivity is measured rather than argued, and it runs the opposite way
to the one the currents suggest. A lower reference gives the pair *more*
charge: the drive it took away lengthens the integration by more than it
lowered the transconductance, so the product rises -- 2.748 pF at 0.9 V
against 2.431 pF at 1.1 V. But the margin the comparator has to fit inside is
half an LSB, which that same reference sets, so the requirement tightens as
the square of it. The requirement moves faster than the supply of charge
does, and the net margin falls toward a low reference: 2.00 at 0.9 V, 2.29 at
nominal, 2.65 at 1.1 V. A low reference is the dangerous direction, and a
design judged against a target computed at nominal reads that backwards --
it sees the charge rise and calls it margin.

What is left to bound it is that a reference wrong enough to matter here is
already a gain error far larger than anything the comparator contributes.

## Which corner is worst is not one question

The comparator's worst corner is fast silicon at high supply and high
temperature, where the tail delivers the most current and the efficiency is
lowest. Sampling's worst corner is slow silicon at low supply and high
temperature, where the top switch's resistance peaks. They are at opposite
ends of the process window, and a design checked at one "worst case" would
have been checked at neither.

Skewed corners, where the two device flavours move in opposite directions,
sit between the two symmetric ones for this circuit. They are worth running
anyway: the latch is a pair of one flavour loaded by the other, so what it
does depends on a ratio that the symmetric corners leave untested.

Measured on the design as sized, each corner given a strobe long enough that
the integration ends where the circuit ends it rather than where the window
does:

| corner | tail | gm/id | t_int | gm*t_int | excess noise carried |
|---|---|---|---|---|---|
| tt 1.80 V 27 C | 5.49 uA | 11.9 | 39 ns | 2.551 pF | 2.29 |
| ss 1.62 V 125 C | 4.26 uA | 10.6 | 46 ns | 2.063 pF | 1.86 |
| ss 1.62 V -40 C | 0.75 uA | 21.1 | 288 ns | 4.556 pF | 4.10 |
| ff 1.98 V -40 C | 7.91 uA | 12.3 | 28 ns | 2.763 pF | 2.49 |
| ff 1.98 V 125 C | 8.18 uA | 9.0 | 22 ns | 1.647 pF | 1.48 |

The last column is the one to read, and it is not a safety factor in the usual
sense. The noise goes as the root of the excess noise factor over the charge,
so a corner carrying twice the charge its target asks for is a corner whose
answer survives an excess noise factor of two -- and that factor is the single
quantity in the law that was assumed rather than measured. The column is the
sweep of it this page asked for, taken at five corners instead of by hand, and
what it says is that the assumption of unity has between a half and three
times its own value in hand depending on where the part lands.

Everything else in the table is the tail's current read twice. It spans eleven
times across the set, for the reason the law above gives: the mirror's
reference device is gated at the converter's reference, so its drive is that
reference less a threshold, and a cold slow threshold takes most of it. At
0.75 uA the pair slides toward weak inversion, the efficiency rises by half,
and the noise product comes out the best of the five -- while the integration
stretches to 288 ns and the decision stops arriving inside the phase a
conversion allows. At the other end the current is eleven times larger, the
decision lands in a fifth of the time, and the efficiency collapse leaves the
thinnest margin in the set.

So the two corners that bound this design sit at opposite ends of the process
window and they run out of different things: slow cold silicon runs out of
time, fast hot silicon runs out of margin. A single-axis corner run reports
each of them as the other's best case, which is what makes two measurements
necessary rather than one.

And the noise figure on its own is not the budget. Four sigma of the fast hot
corner's noise is four fifths of the half-LSB it has to fit inside, which
leaves under a fifth of it for everything static -- the latch's own offset,
the array's, and whatever the top plate's parasitic multiplies both by. (A
ratio rather than volts, because the volts follow from the resolution and the
reference and would go stale with either.) That is the sense in which that corner leaves nothing. What fills it is not
the offset, though: the spread of offset across parts is several LSB, which is
many times the room any margin argument has to offer, and no sizing brings it
inside one. A constant displaces every threshold alike and moves no code
against its neighbour, so it was never a margin item -- it is a calibration
range, measured per part through the forced-input mode, and what has to fit
the room above is only whatever a calibration leaves behind.

Two things the measurement adds. Its spread is worst at this same corner, for
the reason the offset law gives: the faster a latch resolves, the less
integration gain stands between its own mismatch and its input, so the corner
with the least noise margin has the widest offset as well -- one corner
binding on both. And the spread is a property of the strobe it is measured
at, not of the circuit alone, because a strobe too short to finish
regenerating is decided by which node got ahead rather than by where the
circuit ties. A calibration is therefore only valid at the conversion rate it
was taken at, which matters because that rate is a register field.

`sim/offset_baseline.txt` carries the spread and the corners it was drawn at;
`model/latch.py` carries the law it follows.

## What widening the specification would cost, cheapest first

The part is specified at room temperature, and what makes saying otherwise
expensive is one corner: slow cold silicon, where the decision does not arrive
inside the conversion clock. Four ways out, in the order they cost:

1. **A slower conversion clock.** The clock is programmable already, so this
   is a register write and some conversion rate: the decision wants about two
   and a half times the phase at that corner and nothing on the die changes.
   It is the answer unless the rate is the point.
2. **A higher reference.** The mirror's drive is the reference less a
   threshold, so raising the reference buys back exactly what the threshold
   took, and it buys margin as well as speed -- the sensitivity above runs
   that way. What it costs is the full scale, which is the converter's own
   specification rather than the comparator's, and the input pair's headroom
   at the top of the array's excursion.
3. **A wider mirror.** More current everywhere, and the supply spread flattens
   with it. It is paid for at the far end of the window, because current is
   what the fast hot corner already has too much of: this trades the corner
   that runs out of time against the one that runs out of margin, and it is
   only worth doing if the first is bounding and the second has room.
4. **Gain ahead of the latch.** A preamplifier relaxes both axes at once and
   is the only one of the four that does. It is also a new small-signal design
   carrying its own stability and its own static current, which is why it is
   the last entry and not the first.
