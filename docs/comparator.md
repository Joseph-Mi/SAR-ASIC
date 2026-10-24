# What the comparator is, and what its noise costs

The comparator is a StrongARM latch: a clocked differential pair whose drains
are capacitors, followed by a cross-coupled pair that regenerates whatever
difference the first stage built. It compares the array's top plate against
`vcm` and drives the two wires the controller reads.

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
is the one thing this converter has in excess, because the latch decides in
tens of nanoseconds inside a strobe of well over a hundred.

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
The sensitivity is measured rather than argued. It is bounded by the fact
that a reference wrong enough to matter here is already a gain error far
larger than anything the comparator contributes.

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
