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

| Digital height | Digital used | Analog left | Array rows it holds | Width they need |
|---|---|---|---|---|
| 110 um | 91% | 115.8 um | 39 grouped / 32 interleaved | 88 / 130 um |
| **130 um** | **77%** | **95.8 um** | **32 grouped / 27 interleaved** | **108 / 151 um** |
| 140 um | 72% | 85.8 um | 29 grouped / 24 interleaved | 117 / 172 um |

The analog column is rows rather than a percentage of area, because area was
never what bound: the strip is three times as wide as it is tall, so the height
decides how many rows the array gets and the width then has room to spare at
every split in the table. Grouped and interleaved are the two placements, and
they differ because the pitch does -- see the array's shape below.

The headroom belongs on the digital side because that is the side whose
requirement is a guess. The analog requirement is arithmetic once the unit's
size is settled: the count is fixed by resolution and the pitch by the
process. The digital requirement is an estimate built on an estimate, and it
is the one that will move.

The unit's size is the caveat, and it is not settled. It was written down as
the smallest the process would draw and it is not that: no rule either DRC
deck runs states a minimum *area* for the MiM, the only size rule is a
minimum width, and the device's own model defaults to a micrometre each way.
A smaller unit matches worse, so it is a matching decision with an area
consequence rather than the other way round, and until it is made
deliberately this table's analog column moves with it.

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
- ~~*The drawn array is over half again its raw capacitor area.*~~ Measured
  instead, and it was optimistic by a wide margin: what the array asks the
  floorplan for is 2.43 times the plate area with each branch grouped and
  3.49 times with the branches interleaved. Dummy ring, inter-cell spacing
  and the keep-away a power stripe needs -- all three, which is why these are
  quoted off the keep-out and not off the block. `docs/model.md` has the raw
  figure.

## The array's shape, which is what binds

Not its area. And the number here was an estimate until the process's own rules
were read: it said a square array plus a dummy ring came to roughly 76 um on a
side, and the rules say **97.00 um**, or 99.68 um once unrelated metal is held
off the plates. Against a 95.8 um strip that does not fit, so the estimate was
wrong by twenty-three micrometres in the direction that does not announce
itself.

What fits is the same array not drawn square -- 30 rows of 35 columns inside
its ring rather than 32 of 32, 108 um wide in a strip with 334.88 um of width
to give. The cost is not area. It is that a gradient across the die is no
longer the same length in both directions, so a placement scheme cancelling it
has a long axis and a short one to treat differently.

Both figures above are bounds on the compact side, not layouts. The narrow
pitch is what two units of one branch get, so claiming it for a whole row
claims that no branch boundary falls on that row -- which no placement of ten
branches manages. The dummy ring never gets it at all: a dummy carries no
charge, so it is tied off on its own, its bottom plate is a separate polygon,
and the step across it is the wider one however the branches inside are
placed. That ring is the whole of the 3.9 um by which the compact square
array misses.

Two numbers rather than one throughout, because the pitch depends on something
that is not a property of the capacitors: units of one branch sit on a single
bottom plate and step at the plate-to-plate spacing, 2.84 um; units of
different branches are different nets, so the metal under them is two polygons
that must be apart *as metal*, and the step is 3.48 um. Grouping each branch is
therefore the compact array and interleaving them is the matched one. A
common-centroid scheme interleaves on purpose -- so the gradient it cancels is
paid for in rows, and at this split it costs six of them.

`tech/sky130.py` declares the rules and the arithmetic, `tech/tests/test_drc.py`
holds them to the two decks the DRC script runs, and
`model/tests/test_footprint.py` holds the array to this strip. Nothing above is
restated in either.

---

## When to re-derive this

- LibreLane reports a utilisation far from the assumption above
- A digital block lands that is not small next to the FSM
- The resolution changes, which moves both the array's area and its side
- A capacitor rule changes under a PDK bump, which the rule tests report as a
  disagreement with what `tech/` declares rather than as a DRC failure weeks later
- The vendored template moves, which is visible as a diff in `layout/`

Re-deriving is cheap. Discovering at M8 that the macro does not fit is not.
