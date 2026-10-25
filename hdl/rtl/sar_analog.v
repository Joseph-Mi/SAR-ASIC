// The analog half, as the rest of the chip sees it: a port list with nothing
// behind it.
//
// Contract: this is the Verilog face of the boundary declared in
// `reference/interface.py` -- every name, width and direction -- and a test
// fails when the two disagree, the same way the Xschem symbol is held against
// it. There is no body and there will never be one: the block is hand-drawn
// custom layout. What makes the declaration worth having anyway is that the
// tile top cannot be elaborated, linted or structurally checked without one,
// and a boundary that only exists in a schematic is a boundary the digital
// flow cannot check.
//
// Marked a blackbox so yosys stops looking for logic that was never written,
// and treats the cell's outputs as driven. Every port is therefore unread or
// undriven, which is the declaration doing its job; `hdl/lint/waivers.vlt`
// says so once rather than this file saying it twelve times.
//
// Directions are the contract's, read from the digital half outward: the
// array's controls arrive, the latch's two outputs leave, and the three analog
// pins and the two supplies are terminals rather than signals.

(* blackbox *)
module sar_analog #(
    parameter integer N_BITS = 10
) (
    input  wire [N_BITS-1:0] dac_b,
    input  wire              sample,
    input  wire              cmp_clk,
    input  wire              force_en,
    input  wire              force_hi,
    output wire              cmp_out,
    output wire              cmp_out_n,
    input  wire              vin,
    input  wire              vref,
    input  wire              vcm,
    inout  wire              vdd,
    inout  wire              vss
);

endmodule
