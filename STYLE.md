# SAR-ASIC Style Guide

## 1. Order of work

Nothing is written out of order. Every other rule in this file exists to serve
this one.

1. **Golden model first.** `hdl/reference/`, Python. Written and validated
   before any RTL exists. It defines correct behavior. The RTL is judged against
   the model; the model is never adjusted to match the RTL.
2. **Tests second.** cocotb for unit tests. SystemVerilog for larger
   testbenches. Written against the golden model and passing against it before
   the RTL exists.
3. **RTL last.** `hdl/rtl/`. Written to satisfy tests that already pass against
   the model.

If you are writing RTL and step 1 or 2 is missing for that block, stop and go
back.

## 2. Languages

| Where | Language |
|---|---|
| `hdl/reference/` | Python — golden model |
| `hdl/verification/` unit tests | Python + cocotb |
| `hdl/verification/` larger testbenches | SystemVerilog |
| `hdl/rtl/` | Verilog-2005 |

Simulator is Verilator. Python is linted with ruff.

RTL is Verilog-2005 because that is what goes to TinyTapeout. The testbench side
has no such constraint, which is why the larger benches are SystemVerilog.

The TinyTapeout top module signature is fixed and must match exactly:

```verilog
module tt_um_[username]_[project] (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable (0=input, 1=output)
    input  wire       ena,      // Enable signal
    input  wire       clk,      // Clock
    input  wire       rst_n     // Active-low reset
);
```

## 3. No hardcoded values

A bare literal in the source is a defect. Every value gets a name, in one place,
and every use derives from that name.

**Verilog**

- Any literal other than `0` or `1` is a `parameter` or `localparam`.
  `localparam` unless the value is meant to be overridden at instantiation.
- Widths are derived, never restated. `[N_BITS-1:0]`, not `[9:0]`.
  `$clog2(N_STATES)`, not `4`.
- Literals are width- and base-qualified: `N_BITS'd0`, `4'b1010`. Never a bare
  decimal in an assignment or comparison.
- Counter terminal values, bit-trial counts, settling delays, and thresholds are
  all named parameters. If a number encodes a physical quantity, its name says
  which quantity.

**Python**

- Module-level named constants. No literal appears inside a function body if it
  has meaning outside that line.
- Test expectations come from the golden model or from a named constant. A test
  that asserts against a literal it computed by hand is asserting against a typo
  waiting to happen.

**Across the boundary**

Constants shared between the golden model and the RTL are defined **once** and
imported or generated into the other. Retyping the same number in Python and in
Verilog creates two values that will silently diverge. If you catch yourself
copying a number between `hdl/reference/` and `hdl/rtl/`, that is the bug.

## 4. Comments

Be ruthless. Most comments people write should not exist.

**Delete on sight**

- Anything that restates the code. `// increment counter` above `count = count + 1`.
- Commented-out code. Git has it.
- Section banners and decorative rules that carry no information.
- Comments that name a value. `// wait 8 cycles` goes stale the moment the
  parameter changes. Name the parameter and let the code say `8`.
- Anything pointing at another file. Paths rename and lines shift; the comment
  does not follow.
- Anything with an expiration date — TODOs, "for now", status words, a
  measurement.

The last two are the ones that survive review by looking useful. They get their
own rules below.

**Earn its place**

A comment must carry information that is *not derivable from the code*. That is
the whole test. In practice there are three kinds worth writing:

1. **Contract.** What a caller must guarantee, and what the module guarantees
   back. This cannot be read off the port list.
2. **Why, not what.** The reason a non-obvious choice was made, especially where
   the obvious alternative is wrong.
3. **Physical assumption.** Anything encoding settling time, charge injection,
   capacitor matching, comparator offset, or a timing budget must be traceable
   to a derivation. A number nobody can trace is a number nobody can change.
   Traceability runs one way only — see *Reference points one way*. The comment
   names the physical quantity; the derivation lives in the docs, keyed by the
   parameter's name.

**Nothing with an expiration date**

If a statement can become false without anyone editing the line it sits on, it
does not go in a comment. Code is checked by the simulator; comments are checked
by nobody.

- **Values.** Any number, width, count, or threshold, restated in prose. Already
  banned by *No hardcoded values*; a comment does not get an exemption. This
  includes counts of things — "three states", "both callers", "all four
  channels". The fifth channel arrives and the comment does not notice.
- **Temporary decisions.** "for now", "temporary", "placeholder", "until we
  switch to X". Temporary things become permanent, and the comment ends up the
  only record that anyone intended otherwise — a record nobody schedules. Either
  the code is what we ship, or it does not get committed.
- **TODO, FIXME, HACK, XXX.** Not in committed source. A TODO in RTL is work
  with no owner and no date, in a place where work is not tracked. Track it
  where work is tracked, or do it.
- **Status and time words.** "new", "currently", "recently", "the old path",
  "was previously", "will be replaced". Each is dated relative to a moment
  nobody wrote down. Git records when; the comment should not try.
- **Performance and area claims.** "faster than the shift-register version",
  "fits in 200 cells". True at one measurement, on one toolchain version. If it
  matters, it belongs in a check that fails when it stops being true.
- **People and process.** Author names, dates, review notes, "per discussion
  with —", ticket titles. Git blame is authoritative and never stale.

Before writing a comment, ask: what change elsewhere makes this false, and would
that change drag me back to this line? If the answer to the second is no, the
comment is a liability, not documentation.

**Never point at another file**

A comment in one file must never point at another file. Files get renamed and
moved, modules get split, lines shift. None of that touches the comment, so the
pointer rots in silence and the next reader either chases a dead path or — worse
— finds something at that path and trusts it.

This covers all of:

- Paths and filenames. `see docs/timing.md`, `mirrors hdl/reference/sar.py`.
- Line numbers, always. They are stale before the commit lands.
- "See the comment in X", "same as Y does", "keep in sync with Z".
- Names this file does not declare — a module, parameter, signal, or function
  owned somewhere else. If this file does not declare or instantiate it, do not
  name it.

A comment asking two files to be kept in sync is a confession that a value was
copied. Fix the duplication — *No hardcoded values*, **Across the boundary** —
and then the comment has nothing left to say.

**Reference points one way.** Docs cite code; code never cites docs. A document
is read and reviewed as a document, so a stale reference in one gets caught. A
comment buried in RTL is read only by whoever is already editing that line. So
the derivation of a settling-time parameter lives in the design docs *under that
parameter's name*, and the RTL declares the parameter and says nothing about
where the math is. Grepping the name finds both ends.

The same rule applies inside this file: sections are cross-referenced by title,
never by number, because numbers renumber.

**Comments are part of the diff**

A comment sits above code and claims something about it. Change the code and the
comment is now a claim about code that no longer exists. Either update it in the
same commit or delete it. A wrong comment is worse than no comment, because it
is trusted.

Reviewers reject a diff whose comments were not read.

**File header.** Every file states what it is and the one contract a user must
honor. Nothing more — no filename banner (it goes stale on rename), no author,
no date, no change log.

```verilog
// Successive-approximation control FSM. One bit trial per cycle, MSB first.
//
// Contract: comp_i must be stable for the full cycle following dac_set_o.
```

If you cannot state the contract in a sentence, the module is doing too much.
