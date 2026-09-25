# Floorplan budget

How the tile is divided between the two halves, decided before either is drawn.

The digital macro's size is not discovered, it is *assigned*: LibreLane is given
a hard `DIE_AREA` and has to fit. The alternative is finding out at M8 how large
it grew, by which point the analog layout it has to share a tile with has been
hand-drawn for weeks. That is the whole reason this is an M2 artifact and not an
M8 one.

---

## What the tile actually is

From the vendored template, `layout/tt_analog_2x2.def`:

    DIEAREA ( 0 0 ) ( 334880 225760 )        units: 1/1000 um

so **334.88 x 225.76 um**, and every pin in it sits on one of two edges:

| Edge | Pins | Layer |
|---|---|---|
| top | `clk`, `ena`, `rst_n`, `ui_in`, `uio_in`, `uio_out`, `uio_oe`, `uo_out` | met4 |
| bottom | `ua[0..7]`, of which the first six are usable | met4 |

That decides the orientation before any area is counted: **digital at the top,
analog at the bottom**, because each half's pins are on its own edge and routing
one half's signals across the other is how both halves get worse.

Power is not in the template. It is ours to draw, as vertical met4 stripes at
least 1.2 um wide running from 10 um above the bottom to 10 um below the top, so
the stripes cross *both* regions and neither half may treat met4 as its own.
Analog may not use met5 at all.

---

## The split

    digital   334.88 x 130  at the top
    analog    334.88 x  95.76  at the bottom

`DIE_AREA` for the digital macro is therefore `0 0 334.88 130.00`.

### Why 130

| Digital height | Digital used | Analog left | Analog used |
|---|---|---|---|
| 110 um | 91% | 115.8 um | 17% |
| **130 um** | **77%** | **95.8 um** | **21%** |
| 140 um | 72% | 85.8 um | array no longer clears its keep-out |

The headroom belongs on the digital side because that is the side whose
requirement is a guess. The analog requirement is arithmetic -- the unit
capacitor is the smallest the process will draw, and the count is fixed by
resolution -- so it cannot drift far. The digital requirement is an estimate
built on an estimate, and it is the one that will move.

---

## Where the numbers come from

Everything below is either **measured** or **assumed**, and the difference
matters when re-checking this.

**Measured.** The synthesized cell area of the one module that exists:

```bash
LIB=$PDK_ROOT/$PDK/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
yosys -p "read_verilog hdl/rtl/sar_fsm.v; synth -top sar_fsm; \
          dfflibmap -liberty $LIB; abc -liberty $LIB; stat -liberty $LIB"
```

Over half of it is sequential, which is the part that will not shrink: the
conversion result, the settled word and the index counter all have to be held.

**Assumed, and the three to re-check:**

- *The whole digital half costs several times the FSM.* Still to come are the
  register file, the clock divider, the DFT multiplexing and the TinyTapeout
  wrapper. The multiplier used here is deliberately pessimistic.
- *Place-and-route reaches slightly under half utilisation.* Small macros
  usually do worse than large ones; this is the number to replace first with a
  real LibreLane run.
- *The drawn array is over half again its raw capacitor area.* Dummy ring,
  inter-cell spacing, top-plate shielding and routing. `docs/model.md` has the
  raw figure.

The array's *shape* is the constraint that actually binds, not its area: a
square array of the unit capacitor plus a dummy ring comes to roughly 76 um on a
side, which is what stops the analog strip getting much below 90 um however
little total area it needs.

---

## When to re-derive this

- LibreLane reports a utilisation far from the assumption above
- A digital block lands that is not small next to the FSM
- The resolution changes, which moves both the array's area and its side
- The vendored template moves, which is visible as a diff in `layout/`

Re-deriving is cheap. Discovering at M8 that the macro does not fit is not.
