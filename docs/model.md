# The model

Why there are four Python modules describing one ADC, what each is for, and the
physics they all descend from.

---

## One equation

A charge-redistribution SAR has no resistors and no amplifiers in the signal
path. It is a capacitor array, a comparator, and a state machine, working in
three moves.

**Sample.** Every unit capacitor's bottom plate connects to the input; the top
plate is held at ground. The charge sitting on the top plate is `-C_total * Vin`.

**Hold.** The top-plate switch opens. That node is now *floating* -- no DC path
anywhere -- so its charge is trapped for the rest of the conversion. With the
bottom plates returned to ground, the top plate sits at `-Vin`.

**Redistribute.** Switch some subset S of the bottom plates to VREF. Charge is
conserved, because the node floats, so the top plate moves to

```
V_top  =  -Vin  +  VREF * C_S / C_total
```

and the comparator asks whether that is above zero -- which is exactly asking
whether `VREF * C_S/C_total` is above `Vin`. Binary search on S, MSB branch
first, N trials, done.

That is the whole converter. The second term is `dac_voltage`, and everything
else in the repo is bookkeeping around it.

### The consequence everything else follows from

`V_top` depends on a **ratio** of capacitances. Absolute farads cancel. So the
converter's accuracy has nothing to do with how large the capacitors are and
everything to do with how equal they are. Absolute size enters only through
thermal noise and settling time, and at 8 bits neither is what binds.

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

Two more bits double that amplification *and* halve the LSB, which is why 10
bits is not a small step up from 8.

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
  hdl/reference/sar.py       what the converter DOES      the authority
  hdl/reference/protocol.py  WHEN it does it              the wire contract
        |
  model/metrics.py           what the array IS            the fast path
  model/dynamic.py           what the array is WORTH      effective bits
        |
  model/mismatch.py          what goes WRONG              all randomness
        |
  model/yield_study.py       the QUESTION                 the sweep
```

Imports run one way only. Nothing in `hdl/reference/` imports from `model/`.

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
effective bits. This is the number "8-bit" actually claims. An array whose
mismatch costs it a bit is a 7-bit converter no matter how correct the FSM is,
and no amount of DNL and INL inspection says that in one number.

**`mismatch.py`** is where every random draw in the project happens, so results
are reproducible from a seed. Three physically distinct effects are kept
separate because you will want them independently: uncorrelated unit variation,
a systematic die gradient, and placement. Placement is a permutation of the unit
array, which is what makes a layout scheme a value to pass in rather than a
rewrite. This module also holds the Pelgrom functions, the bridge from a
statistical sigma to silicon area.

**`yield_study.py`** sweeps matching across resolutions and writes
`model/yield_baseline.txt`. That file is committed, so a change to the model
shows up as a reviewable diff rather than as a number nobody compared.

---

## Two things are computed twice on purpose

The transfer curve exists as a matmul in `metrics.py` and as a loop in
`sar.py`; the conversion result exists as a binary search in `sar.py` and as a
lookup in `dynamic.py`. Both duplications are deliberate -- the fast forms are
what make sweeps interactive -- and both are exactly the shape that silently
drifts apart. Each is therefore pinned by a test that runs the two against each
other on a mismatched array. If you add a third route to the same number, add
the third cross-check with it.

---

## What the model does not include

Named here because an unnamed assumption is indistinguishable from an oversight.

- **Top-plate parasitic.** A real array has capacitance from the floating node
  to substrate and routing. It does not distort, being common to every code,
  but it attenuates full scale. Gain error, currently taken as zero.
- **kT/C sampling noise.** `cmp_noise_rms` covers the comparator only. Nothing
  models the noise trapped on the array at the instant of sampling. At 8 bits
  this is not what binds, but that is a conclusion the model should eventually
  reproduce rather than assume.
- **The switching scheme.** `dac_voltage` encodes conventional binary-weighted
  switching. Monotonic and split-capacitor schemes have different equations and
  far better switching energy. One choice is embodied here without being argued.
- **Single-ended only.** The comparator interface is differential. If the array
  follows, `dac_voltage` changes.
- **A matching coefficient.** `sigma_from_area` deliberately has no default for
  `A_C`, because sky130's open PDK does not publish one worth sizing silicon on.
  Until a defensible value exists for MiM and for VPP, the sweep answers "what
  matching do I need" and cannot yet answer "what capacitor do I draw". This is
  the last thing standing between the study and an M1 decision, and it is a
  literature task rather than a coding one.

---

## Running it

```bash
make model    # every test above, a few seconds
make study    # regenerate model/yield_baseline.txt, commit the diff
```

The baseline's columns are documented at the top of `yield_study.py`. Read
`p_missing` as yield and `enob` as what the resolution is worth; the two fail
independently, and an array can be scrap-free while quietly costing you half a
bit.
