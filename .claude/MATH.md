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

On the **top plate**, in this architecture, neither the linear nor the
voltage-dependent part moves a threshold. Write the parasitic's charge as any
function of the node voltage, q_p(V), its other terminal fixed:

    sample:    Q = C_array*(Vcm - Vin)       + q_p(Vcm)
    decision:  Q = C_array*V_x - VREF*C_S    + q_p(V_x)

A threshold is where V_x = Vcm. There q_p(V_x) = q_p(Vcm), it cancels, and
Vin = VREF * C_S / C_array exactly. The comparison happens at the voltage the
node was sampled at, so the parasitic ends every decision holding the charge
it started with. A comparator offset moves the decision point to Vcm + Vos for
every code alike, so even then the parasitic contributes a constant, not INL.

What it does cost is swing. Between decisions

    V_x - Vcm  ~  (VREF*C_S - Vin*C_array) / (C_array + C_par)

so the comparator resolves a residue divided by (C_array + C_par)/C_array, and
its offset and noise, referred to the input, grow by that factor. `sar.py`'s
`top_plate_voltage` carries the linear case; `test_top_plate.py` pins both
claims.

Where Cj(V) *does* cost linearity is off the top plate: a bottom-plate
parasitic that differs between branches perturbs the weights (below), and the
input switch's junctions load `Vin` nonlinearly while tracking -- a dynamic
effect, gone once sampling settles fully. (This section previously claimed
top-plate C(V) is INL; the charge argument above is why it is not.)

---

## Which plate the parasitic lands on decides whether it matters

This asymmetry is most of the analysis.

| Node | During conversion | A parasitic there |
|---|---|---|
| Top plate | high-impedance, holds the residue | divides the comparator's swing (input-referred offset/noise grow); no threshold moves |
| Bottom plates | driven hard to VREF or GND | loads the driver: costs settling time, not accuracy |

So a large diffusion on a bottom-plate switch costs settling time, and on the
top plate it costs comparator swing; neither moves a threshold on its own. What
does reach the LSB from the top-plate switch is the charge it injects when it
opens (next sections). Size the two switch families against different criteria.

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

The cost is a second sampling phase. It is made inside the analog block from
the one `sample` wire (DD-11), so the interface is unchanged and the timing
lives next to the switches it orders.

Measured (M3 Step 4c, realistic 8 fF unit, generic devices): top first leaves
a signal-dependent residue of ~0.1 LSB; together ~0.9 LSB; bottoms first
~1.7 LSB. The top-first offset doubles with the top switch's width -- it is
that switch's channel, exactly as W*L*Cox*(Vgs-Vth) says.

---

## Top plate at Vcm

The model samples the top plate to ground, which makes the conversion read

    V_top = -Vin + VREF * C_S / C_total

Correct algebra, unrealisable voltages: V_top runs from about -VREF to 0. Below
roughly -0.5 V the top-plate switch's junctions forward-bias and leak the held
charge away, and a StrongARM with an NMOS input pair cannot resolve an input
near 0 V. Sample the top plate to Vcm instead (usually VREF/2):

    V_top - Vcm = -Vin + VREF * C_S / C_total

Same ratios, so every matching and yield result carries over unchanged. What
changes is that Vcm has to exist: it is its own pin (DD-10).

---

## Thermal noise on the array: kT/C

Opening the sampling switch freezes a snapshot of the thermal noise on the
array. Its rms is independent of the switch resistance:

    v_n = sqrt(k*T / C_total)

Compare it with quantisation noise, LSB/sqrt(12), and require it well under:

    sqrt(kT / C_total)  <<  VREF / (2^N * sqrt(12))

C_total = 2^N * C_u, with C_u = unit area * density. Density per flavour and
corner is the `camimc` grep in docs/model.md. With MiM at minimum unit size this
comes out tens of microvolts against hundreds for quantisation — not binding.
The fraction grows with N and shrinks with C_u, so re-check it if the unit
shrinks (VPP) or the resolution rises.

---

## Settling through the pin

Each bit trial must settle to half an LSB:

    e^(-t/tau) < 2^-(N+1)   =>   t_settle > (N+1) * ln2 * tau

For Vin sampling and for Vref recovery, tau is not just the switch:

    tau = (R_pin + R_switch) * C_seen

R_pin is the TT analog pin's series resistance (TT analog spec). C_seen is the
array for Vin sampling; for Vref it is the capacitance switched in that trial,
worst at the MSB. t_settle has to fit in the SETTLE cycle, which is what sets
the conversion clock from the analog side. M3 measures it; this bounds it.

---

## Comparator noise and ENOB

Comparator noise sigma_n (in LSB), redrawn every trial, is input-referred
noise ahead of the quantiser. Below the gross-error onset it adds to
quantisation noise the way dither does:

    sigma_total = sqrt(1/12 + sigma_n^2)        [LSB]
    ENOB        = N - log2(sigma_total * sqrt(12))

The tempting alternative — take the code error (noisy code minus clean code)
and add *its* power to 1/12 — double-counts. A flip only happens when Vin sits
next to a threshold, which is exactly where the quantisation error was already
near +-LSB/2, so the code error is anti-correlated with the quantisation
error, not independent of it. Measure error against the true input.

Above the onset an early bit decides wrongly, a binary-weighted SAR never
revisits it, and the error costs 2^k LSB: the heavy tail `p_gross` counts.

---

## Measuring C(V) on a node

The hand formula for Cj(V) above says whether to worry. To get the number with
every junction and overlap the models carry, measure it the way the
cap-matching deck measures a capacitor:

    DC-bias the node at V, add a 1 V AC source, C = |I| / (2*pi*f*1 V)

Sweep the DC bias across the input range and the variation of C over that
range is what a *bottom-plate* branch mismatch or the input-switch loading
depends on; on the top plate it only sets the swing division. `.op` also reports
per-device terms, e.g. `@m.xm1.msky130_fd_pr__nfet_01v8[cgd]`.

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
