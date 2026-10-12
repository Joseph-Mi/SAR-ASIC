# The model

Why there are four Python modules describing one ADC, what each is for, and the
physics they all descend from.

---

## One equation

A charge-redistribution SAR has no resistors and no amplifiers in the signal
path. It is a capacitor array, a comparator, and a state machine, working in
three moves.

**Sample.** Every unit capacitor's bottom plate connects to the input; the top
plate is held at the common mode `Vcm`. The charge sitting on the top plate is
`C_total * (Vcm - Vin)`.

**Hold.** The top-plate switch opens. That node is now *floating* -- no DC path
anywhere -- so its charge is trapped for the rest of the conversion.

**Redistribute.** Switch some subset S of the bottom plates to VREF and the rest
to ground. Charge is conserved, because the node floats, so the top plate moves
to

```
V_top  =  Vcm  -  Vin  +  VREF * C_S / C_total
```

and the comparator asks whether that is below `Vcm` -- which is exactly asking
whether `Vin` is above `VREF * C_S/C_total`. Binary search on S, MSB branch
first, N trials, done.

That is the whole converter. The last term is `dac_voltage`; the whole
expression is `top_plate_voltage`; everything else in the repo is bookkeeping
around it.

`Vcm` cancels out of the comparison, so any constant would decide the same
codes. It is chosen for where it puts the node: `VCM_FRACTION` of the reference
keeps every trial between the rails. [sar-primer.md](sar-primer.md) walks
through why, with numbers.

### The consequence everything else follows from

`V_top` depends on a **ratio** of capacitances. Absolute farads cancel. So the
converter's accuracy has nothing to do with how large the capacitors are and
everything to do with how equal they are. Absolute size enters only through
thermal noise and settling time, neither of which this model computes.

### Why mismatch becomes DNL

Each branch is a sum of nominally identical units; branch k owns 2^k of them.
If the units are identical the branch weights are exactly binary and every code
step is exactly one LSB. If the units vary, the weights are not binary, the
steps are not one LSB, and that error *is* DNL. In an otherwise ideal SAR there
is no other source of it.

### Why the MSB transition is the worst case

At the middle of the range every lower branch switches off and the MSB branch
switches on. The two groups share no devices, so their variances add over all
`2^N - 1` participating units. One LSB is one unit, so in LSB terms

```
sigma_DNL_MSB  =  sqrt(2^N - 1) * sigma_u/C_u
```

Two more bits double that amplification *and* halve the LSB, which is why a
step up in resolution is never a small one.

### Why a missing code is the failure criterion

`DNL <= -1 LSB` means a step of zero or less: the transfer curve goes flat or
backwards and that code can never be produced. Such a part is scrap however
good its other codes are, which is what makes missing-code probability the
yield number rather than an average error.

### Why area buys matching

A capacitor's value is an integral over its area of microscopic randomness --
edge roughness, dielectric thickness, dopant. Independent contributions average
out over a larger area, with variance falling as `1/area`. Hence Pelgrom:
`sigma(dC/C) = A_C / sqrt(area)`. Quadruple the area, halve the mismatch. That
square root is the exchange rate the entire sizing decision pays, and it is why
two more bits cost far more than two more branches.

---

## The layers

```
  reference/sar.py           what the converter DOES      the authority
  reference/protocol.py      WHEN it does it              the wire contract
        |
  model/metrics.py           what the array IS            the fast path
  model/dynamic.py           what the array is WORTH      effective bits
        |
  model/mismatch.py          what goes WRONG              all randomness
        |
  studies/yield_study.py     the QUESTION                 the sweep
```

Imports run one way only. Nothing in `reference/` imports from `model/`, and
nothing in `model/` from `studies/`. [architecture.md](architecture.md) has
the whole repository's layers.

**`sar.py`** runs one conversion on one array and returns the code together with
the bit decisions that produced it. It is the definition of correct: the RTL is
judged against it, and never the other way round. The trace matters as much as
the code, because an FSM that reaches the right answer by the wrong path is
still broken.

**`protocol.py`** expands one conversion into the cycles that produce it --
one sample cycle, N bit trials, one done cycle. cocotb compares waveforms, not
return values, so the model rather than the testbench has to own the shape of
those waveforms. It makes no comparator decisions of its own; it reconstructs
the trial words from the trace, so a bit decision is still made in exactly one
place.

**`metrics.py`** never runs a conversion. It computes the whole transfer curve
straight from the branch weights as one matrix multiply, then differentiates it
for DNL and endpoint-fits it for INL. This exists for speed: pushing thousands
of arrays through the conversion loop takes hours, and as a matmul it takes
milliseconds. That is the difference between a study you rerun while thinking
and one you start and walk away from.

**`dynamic.py`** measures the array the way a bench does -- drive a coherent
sine, take an FFT, compare the tone against everything else -- and reports
effective bits. This is the number a stated resolution actually claims. An
array whose mismatch costs it a bit is a converter one bit short of its name no
matter how correct the FSM is, and no amount of DNL and INL inspection says that
in one number.

**`mismatch.py`** is where every random draw in the project happens, so results
are reproducible from a seed. Three physically distinct effects are kept
separate because you will want them independently: uncorrelated unit variation,
a systematic die gradient, and placement. Placement is a permutation of the unit
array, which is what makes a layout scheme a value to pass in rather than a
rewrite. This module also holds the Pelgrom functions, the bridge from a
statistical sigma to silicon area.

**`yield_study.py`** sweeps matching across resolutions and writes
`studies/yield_baseline.txt`. That file is committed, so a change to the model
shows up as a reviewable diff rather than as a number nobody compared.

---

## Two things are computed twice on purpose

The transfer curve exists as a matmul in `metrics.py` and as a loop in
`sar.py`; the conversion result exists as a binary search in `sar.py` and as a
lookup in `dynamic.py`; the top-plate voltage exists as a rearranged closed
form in `sar.py` and as a numerical charge balance in `junction.py`. All three
duplications are deliberate -- the fast forms are what make sweeps
interactive, and the slow form is what extends to a parasitic the closed form
cannot hold -- and all three are exactly the shape that silently drifts apart.
Each is therefore pinned by a test that runs the two against each other. If
you add a fourth route to the same number, add the cross-check with it.

---

## What the model does not include

Named here because an unnamed assumption is indistinguishable from an oversight.

- **A noisy comparator is not an independent error source.** Its cost was
  once computed by adding its code displacement to quantisation noise in
  power. The two are not independent: noise moves a code only near a
  threshold, which is where the quantisation error was already largest, so
  the sum counted the same volts twice and charged the comparator about
  double. The error is now measured against the true input, where the
  correlation takes care of itself.
- **Comparator noise and sampling noise are separate terms.** `cmp_noise_rms`
  covers the comparator, redrawn at every trial, where it can cost an early
  bit and with it a power of two. What the switch traps on the array is drawn
  once per conversion and held, so it behaves as an offset that changes
  between conversions. They are not interchangeable and are not added.
- **The switching scheme.** `dac_voltage` encodes conventional binary-weighted
  switching, and `power.py` says what that costs the reference. Monotonic,
  Vcm-based and split-capacitor schemes have different equations and cost
  less; `docs/topology.md` argues the choice.
- **Comparator and digital power.** `power.py` accounts for the reference pin
  only. The comparator's bias and the digital macro's switching are a measured
  circuit and a synthesised netlist respectively, and neither exists yet.
- **Single-ended only.** Decided, not assumed: `docs/topology.md` argues it. A
  differential array would change `dac_voltage`.

---

## What a nonlinear top-plate parasitic costs

A switch drain on the floating node is a reverse-biased junction, so the
parasitic it adds falls as the node moves away from its body. `junction.py`
carries the depletion law in general -- any built-in potential, any grading --
and solves charge conservation with it; `DIFFUSION_POTENTIAL` and
`DIFFUSION_GRADING` in `tech/sky130.py` are the values this process gives,
fitted to the device rather than assumed from silicon's textbook ones, which
are both wrong here.

**It moves no threshold, however nonlinear it is, and adds no INL.** The
argument is one line once the right quantity is named: a decision is taken
when the top plate reaches the comparator's own switching point, and that
point is the same voltage at every threshold. The parasitic therefore holds
exactly the charge it held at sampling -- the two voltages are equal -- and
its term cancels out of the balance. A capacitance that varies with voltage
stores a definite charge at a definite voltage like any other, so the
cancellation never used linearity. `input_at_decision` is the closed form that
shows it: the parasitic appears only as a difference of stored charge between
two *fixed* voltages.

With a comparator offset those two voltages differ, the term survives, and it
is the same number for every threshold -- so an offset is amplified by
`1 + C_j/C_total` and stays an offset. Still not a nonlinearity.

**And in this design it is 7.3 fF against an array of 9.5 pF** -- a part in a
thousand of the node it sits on. That number is measured, not assumed: the
diffusion of the switch that holds the top plate at the common mode, read off
the device the simulator builds and fitted to a depletion law that follows it
to half a percent over the whole range the plate visits. So the costs below
are real but immeasurable here, and the figure that draws them draws ten and a
hundred times the real parasitic beside it to say how far wrong it would have
to be before any of it reached a code.

What it does cost, each with a figure in the module:

| Cost | Why it is not the one above |
|---|---|
| `swing_gain` | the comparator resolves a divided swing, and the divider is tightest where the node comes closest to the body -- the bottom of the input range for a grounded body, which is where the comparator is already hardest to bias |
| `tau_multiplier` | charge conservation does not care how long the node took to arrive; a settling budget does, and the capacitance being charged is not the same at every trial. This is the one route by which the nonlinearity reaches the codes |
| `leakage_droop_lsb` | the junction also passes a reverse current, and the node is floating while the sample is held. Charge that left does not come back |

The solve refuses to report a voltage below the junction's body, because there
it conducts rather than storing charge -- so the sampling contract that keeps
the node out of that region is enforced by the model rather than merely
documented beside it.

---

## What a moving input costs

Every other part of the model converts one voltage at a time, which assumes
the input stood still. `sampling.py` drops that: sampling pushes charge
proportional to the input's change between conversions into the common-mode
node, and whatever is still recovering when sampling ends recovers during the
conversion, as a threshold shift.

**That mechanism is a first difference of the input, and a first difference is
a filter.** By itself it costs gain and phase against frequency and produces
no harmonics at all, however large it is. Budgeting it as distortion would buy
decoupling that does nothing.

Distortion needs the coefficient to depend on the signal, which it does as
soon as anything in the recovery path does -- a switch resistance that varies
with the voltage across it, a decoupling capacitance that varies with bias.
Then the error is a product of the step and the level, and the harmonics
appear and grow with input frequency. `sweep` separates the two cases;
`step_coefficient` is the settling law, not a second one, so a circuit
measurement of how curved that path is enters at one point.

A sweep refuses to report a record the memory has pushed into the rail: the
amplitude the converter sees is not the amplitude offered, and a clipped
record measures saturation rather than sampling.

`spectrum.py` is what reads a record. SNDR alone cannot say whether the energy
that is not the tone is spread over every bin or sitting in one, and those
have different causes, so SNR, THD and SFDR are reported beside it. The record
length and cycle count are coprime by construction and a harmonic that folds
onto the tone or onto DC is refused, because reported against, every
distortion figure would read as perfect.

---

## What a conversion costs the reference

`power.py` walks a conversion transition by transition and sums the charge the
reference supplies. The reference pin is where this architecture spends: the
same number bounds the energy, the average pin current, and the sag that
current leaves while the comparator is deciding.

**The cost falls as the input rises, by about two and a half times across the
range at eight bits.** This is the opposite of the textbook mid-code peak, and
the reason is the architecture: with the input sampled onto the bottom plates
the first trial costs the same whatever the input, so what varies is how many
*later* trials are undone -- and a trial that fails is charge taken from the
reference and handed to ground. A low code is a conversion whose trials mostly
fail.

The bookkeeping is checked against the one invariant the circuit cannot
violate: the top plate is floating, so its charge does not change from the end
of sampling to the last decision. That check includes the terminating unit,
which is sampled with the rest and grounded afterwards -- its charge comes
from ground and never from the reference.

**The pin's current limit is not what bounds the converter.** Settling through
the pin's resistance is slower than its current limit by more than two orders
of magnitude, taking every resistance in the sampling loop at the pin's own
bound. So the reference pin is budgeted for sag during a trial, not for
average current.

`walden_fom` and `schreier_fom` are the figures converters are compared by.
Both need a power number the design does not have yet, which is why they take
one rather than compute it.

---

## What the converter asks of its comparator

Half a comparator specification belongs to the converter, not to the
comparator, and can be written before one exists. `comparator.py` writes it.

**The margin.** A binary search halves its own question, so the hardest
decision is the last one, and it is half an LSB -- 488 uV here. Every
comparator figure is a fraction of that, which is what makes it the number a
specification starts from. The array divides it before the comparator sees
it, so the specification is written at the comparator's terminals and
converted once, through `swing_division`, rather than carried divided through
every expression.

**The noise.** This is the binding constraint. Below the onset of gross errors
a noisy comparator in front of a quantiser is a dithered quantiser, so the
cost is `sqrt(q^2 + sigma^2)` -- a quarter-LSB comparator gives up four tenths of a bit.
Read the other way, a 488 uV margin carries 122 uV rms at four sigma.

**The time.** Not a constraint. Regeneration is exponential, so the time a
latch needs grows only as the logarithm of how small the difference is: a few
time constants, nanoseconds at worst. Settling sets the conversion clock at
two orders above that, which means the strobe is hundreds of time constants
long and `resolution` -- the difference a latch could fail to separate --
underflows a double. Metastability here is a thing to detect, not a thing to
budget for, and the flag the interface carries is cheap insurance rather than
a live hazard.

**The offset.** Not a budget item either. A bare latch's offset is several
LSB, far outside any margin, but a constant offset shifts every threshold
equally and so moves no code relative to its neighbours. It is calibrated, in
the field rather than at the factory because it moves with the corner, and
`margin_after` takes the residue calibration leaves rather than the raw
figure.

---

## Where each number comes from

A model is only as good as its worst-sourced constant, and the four kinds do
not fail the same way.

| Kind | How it fails | What keeps it honest |
|---|---|---|
| **Read from the PDK** -- capacitance density, plate bias, matching coefficient | the PDK ships it twice and a grep finds the orphan | a test reads it back out of the tree the simulator includes |
| **Measured from a device** -- the diffusion on the top plate, the top switch's resistance | measured at the wrong bias, or from a device written out by hand without the fingers the models need | a test re-measures through the same netlister the benches use |
| **Chosen by the design** -- resolution, reference, common mode, switch widths | drifts between the module that chose it and the one that uses it | one declaration, and a test where a copy is unavoidable |
| **Assumed** -- board decoupling, comparator offset and noise | nothing catches it, because nothing knows | named as an assumption at the point of use, and swept rather than fixed |

The traps are not exotic. Three of them bit during this work: the matching
coefficient lives in a tree most paths do not lead to; a MiM written from the
superseded models is a sixth too small because it misses a plate bias of a
tenth of a micrometre; and a switch measured passing the supply's midpoint
reads six times the resistance of the same switch passing this design's common
mode, because the gate drive left over and the body effect against it both
follow from the level.

**Neither the process floor nor sampling noise is what limits this
converter.** The smallest unit the process will draw matches to 0.235%, and an
array built from it loses no codes and gives up under a tenth of a bit at the
target resolution -- and still carries twelve. The same array traps 21 uV when
it samples, which is a fiftieth of an LSB here, though it is a third of one at
fourteen bits. Area is spent on settling and on charge off the reference, not
on matching and not on noise.

---

## Where the matching coefficient comes from

sky130 does state capacitor matching, but not anywhere a datasheet would put
it. It is inside the device subcircuits, as a term proportional to
`1/sqrt(area)` added to the nominal capacitance and gated by `MC_MM_SWITCH`.
Read the current value straight out of the PDK rather than from here:

```bash
grep -n sw_mm_cmim \
  $PDK_ROOT/$PDK/libs.tech/combined/continuous/models_global.spice
grep -n carea \
  $PDK_ROOT/$PDK/libs.tech/combined/continuous/models_capacitors.spice
```

The coefficient is the constant multiplying `1/sqrt(wc*lc*mult)` in the
capacitance expression, in percent-micrometres. VPP states its own in the same shape, close enough to
MiM's that one value serves both. What the model uses is `CAP_A_C` in
`tech/sky130.py`; this
document deliberately does not repeat the number, because then there would be
two of them.

**Read it from the continuous models, not the originals.** The process ships two
sets. The originals are micro-binned -- characterised at particular widths and
lengths, and by SkyWater's own note able to "diverge considerably" at other
sizes, which is every size an array picks for itself. The continuous set was
recharacterised to be valid across geometry and replaces them; the PDK's own
xschem configuration selects it, and the originals are left orphaned. The two
state matching coefficients that differ by roughly six times, so which tree the
number came from matters more than the digits do.

Three things make it easy to miss, all of which cost me time:

- The tree that ships it is not the one most paths lead to. `libs.tech/ngspice/`
  only `.include`s the superseded originals, so grepping either that directory
  or the continuous models for the other's spelling finds nothing and looks
  like proof that no matching data exists.
- `mc_mm_switch` defaults to **0**. Without setting it, every device is
  nominal, a Monte Carlo shows exactly zero spread, and the obvious conclusion
  is wrong.
- Reading an expression is not the same as trusting it. The deck in
  `sandbox/cap-matching/` measures the spread in ngspice so the number in
  `mismatch.py` is checked rather than assumed.

**The same rule governs the density, and the same trap.** The superseded tree
models a MiM as an area term plus a fringe term on a plate biased *inward*
from the drawn shape; the continuous tree models it as area alone on a plate
biased *outward* by more than a tenth of a micrometre. They disagree about the
smallest unit the process draws by about a part in twenty, and only the second
is what a simulation builds. `tech/sky130.py` declares the continuous tree's
parameters and `mim_unit()` evaluates the device's own expression from them;
a test reads both back out of the PDK and checks the expression against the
capacitor ngspice actually instantiates, at two sizes and three corners.

Nothing else may name a unit capacitance. The smallest MiM is not a round
number, it is not its drawn area times a density, and it spans half as much
again from one capacitance corner to the other -- so every absolute figure the
project quotes carries that band.

The consequence is worth stating plainly, because it is not the obvious one.
Matching depends on area alone and both flavours share a coefficient, so
hitting a matching target costs the same area either way. MiM does not buy
better matching -- it buys more capacitance in that area. For an array that is
matching-limited and not noise-limited, that extra capacitance is not a
benefit: it is slower settling and a larger charge kick on VREF.

---

## Running it

```bash
make model    # every test above, a few seconds
make study    # regenerate studies/yield_baseline.txt, commit the diff
```

The baseline's columns are documented at the top of `yield_study.py`. Read
`p_missing` as yield and `enob` as what the resolution is worth; the two fail
independently, and an array can be scrap-free while quietly costing you half a
bit.
