# The numbers under the analog half

Derivations, and the constraints they impose. `docs/model.md` covers the
capacitor array's matching; this covers the *switches* around it, which is a
different failure mode and a tighter one.

Every device number here is read out of the PDK rather than quoted from a
datasheet. Refresh them with:

```bash
F=$PDK_ROOT/$PDK/libs.ref/sky130_fd_pr/spice/sky130_fd_pr__nfet_01v8.pm3.spice
grep -oiE "\+ *c(js|jsws|jswgs|gdo|gso|f) *= *\{?[0-9.eE+-]+" $F | sort -u
grep -oiE "\+ *toxe *= *\{?[0-9.eE+-]+" $F | head -1
```

---

## The budget everything is measured against

Resolution sets one number and every constraint below is a fraction of it:

    LSB = VREF / 2^N

A sampling error that moves the held voltage by more than half an LSB is a
wrong code. That is the ceiling: **total sampling error < LSB/2**.

The array's total capacitance is the other anchor. It is set by the smallest
unit the process will draw, not by matching or noise -- see `docs/model.md` --
so it is a fixed input here rather than a free parameter.

---

## Junction capacitance: the "Cdu" around source and drain

Every source and drain diffusion sits in a reverse-biased well junction. Its
capacitance has an area term and two perimeter terms:

    Cj = AD * CJ + P_gate * CJSWG + P_field * CJSW

`AD` and the perimeters are exactly the `ad`/`as`/`pd`/`ps` instance
parameters. They are derived from width by `sandbox/tools/sky130.py`, which is
why a resized device must have them recomputed rather than carried over: stale
junction geometry puts the previous width's capacitance into every transient.

**The gate-side sidewall dominates.** `CJSWG` is several times `CJSW` in this
process, so at the widths a switch uses, junction capacitance is
perimeter-driven and specifically *gate-edge*-driven. Lumping the perimeter
into one term underestimates it.

### Why it is worse than its size suggests

The junction is a diode, so its capacitance varies with the voltage across it:

    Cj(V) = Cj0 / (1 + V/PB)^MJ

A *linear* parasitic on the summing node is an attenuation:

    gain = C_array / (C_array + C_par)

which is a gain error, and gain errors calibrate out. The voltage-dependent
part does not: the attenuation changes with the signal, and a signal-dependent
gain is **INL**, which one constant cannot correct. So the quantity to bound is
not `Cj` but its *variation across the input range*.

Budget: that variation under one LSB of effect, i.e. under `C_array / 2^N`.

---

## Which plate the parasitic lands on decides whether it matters

This asymmetry is most of the analysis.

| Node | During conversion | A parasitic there |
|---|---|---|
| Top plate | high-impedance, holds the residue | attenuates signal, adds kT/C, and its nonlinearity is INL |
| Bottom plates | driven hard to VREF or GND | loads the driver: costs settling time, not accuracy |

So a large diffusion on a bottom-plate switch is nearly free, and the same
diffusion on the sampling switch is a direct attack on the LSB. Size the two
switch families against different criteria.

The exception is mismatch: a bottom-plate parasitic that differs *between
branches* perturbs the weights and does show up as DNL. Identical switches,
laid out identically, is what makes it common-mode.

---

## Gate-to-channel: charge injection

An on transistor holds an inversion channel:

    Q_ch = W * L * Cox * (VGS - Vth)          Cox = eps_ox / toxe

When the switch turns off that charge leaves through both terminals. The split
depends on the impedances either side and on how fast the gate falls; half to
each is the usual first estimate and the one to design against:

    dV_inject = Q_ch / (2 * C_total)

`VGS` depends on the sampled signal, so `Q_ch` does too. **Signal-dependent
injection is distortion, not offset** -- it is the part that cannot be trimmed
away, and it is the larger of the two gate effects.

---

## Gate-drain overlap: clock feedthrough

The overlap capacitance couples the gate edge straight onto the node:

    Cgd = CGDO * W
    dV_feedthrough = Cgd / (Cgd + C_total) * dV_gate

Nearly signal-independent, so it lands as **offset**. That makes it the most
benign of the three, and the one the forced-input mode can measure directly on
silicon: force the input to a rail, sweep the code, find where the comparator
flips.

---

## The switch-width window

The two constraints pull opposite ways, and this is the real design problem.

**Small W, from sampling error.** Both gate effects scale with width:

    dV_total(W) = Q_ch/(2*C_array) + Cgd/(Cgd + C_array) * VDD    < LSB/2

**Large W, from settling.** The array must settle to half an LSB within a bit
trial, through the switch resistance:

    tau = Ron * C_array,    Ron ~ 1 / (mu*Cox * (W/L) * (VGS - Vth))
    e^(-t/tau) < 2^-(N+1)   =>   t > (N+1) * ln2 * tau

So the trial length in time constants grows with resolution, while `Ron` falls
with width. Raising resolution tightens both ends at once: the LSB halves and
the required settling grows.

**There is no guarantee the window is open.** If it closes, the exits are a
longer trial (slower conversion), a larger array (more area, and `tau` grows
with it too), or bottom-plate sampling below.

---

## Bottom-plate sampling

The fix for injection is sequencing, not sizing.

Open the **top-plate** switch first, while the bottom plates are still held at
a fixed level; open the bottom switches after. The top switch then sees a
constant `VGS` regardless of the input, so its injected charge is constant:
distortion collapses into a fixed offset, and offset is correctable.

The cost is a second sampling phase. The two must be **non-overlapping**, which
makes this a timing contract at the digital boundary rather than an analog
choice -- one `sample` wire cannot express it.

---

## How each number is obtained

Three levels, in rising fidelity, all of which this repo can already run:

1. **Analytic**, from the formulas above and the PDK values. Enough to size a
   switch and to know whether the window is open at all.
2. **Schematic**, with real switch devices rather than ideal ones. Junction and
   overlap capacitance come along automatically once `ad`/`as`/`pd`/`ps` are
   set. This is what M3 is for.
3. **Extracted**, from a drawn layout. The interconnect's share appears only
   here; the device models already carry the intrinsic terms, so the difference
   between levels 2 and 3 is routing.

Level 1 says whether to proceed, level 2 says whether the architecture works,
level 3 says what the layout cost.
