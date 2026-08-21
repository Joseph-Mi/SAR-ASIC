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

**Earn its place**

A comment must carry information that is *not derivable from the code*. That is
the whole test. In practice there are three kinds worth writing:

1. **Contract.** What a caller must guarantee, and what the module guarantees
   back. This cannot be read off the port list.
2. **Why, not what.** The reason a non-obvious choice was made, especially where
   the obvious alternative is wrong.
3. **Physical assumption.** Anything encoding settling time, charge injection,
   capacitor matching, comparator offset, or a timing budget must name its
   source — a spec section, a simulation, or a measurement. A number nobody can
   trace is a number nobody can change.

**File header.** Every file states what it is and the one contract a user must
honor. Nothing more.

```verilog
// sar_fsm.v
//
// Successive-approximation control FSM. One bit trial per cycle, MSB first.
//
// Contract: comp_i must be stable for the full cycle following dac_set_o.
//           Budget derived in docs/timing.md, verified in sim/comparator.sp.
```

If you cannot state the contract in a sentence, the module is doing too much.
