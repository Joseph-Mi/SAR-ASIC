// The result as the pins show it: a holding register and the flag that says it
// just changed.
//
// Contract: load_i marks a conversion ending, with code_i valid that cycle. The
// register takes it only when the mode and hold_i permit, and done_o is high for
// exactly the cycle it did -- so a reader that waits for done_o always finds
// pins belonging to the conversion done_o announced. hold_i is the synchronised
// pin, never the asynchronous wire. With edge_capture_i low it freezes the
// register while it is high; with edge_capture_i high its rising edge asks for
// one result and the register is frozen otherwise.

module sar_readout #(
    parameter integer N_BITS = 10
) (
    input  wire              clk_i,
    input  wire              rst_ni,
    input  wire              load_i,
    input  wire [N_BITS-1:0] code_i,
    input  wire              hold_i,
    input  wire              edge_capture_i,
    output reg  [N_BITS-1:0] code_o,
    output reg               done_o
);

  // A request outlives the edge that made it: the edge lands on whatever cycle
  // the pin moves, which is almost never the cycle a conversion ends, and a
  // request dropped between the two is a press that did nothing.
  reg pending;
  reg hold_q;

  wire asked = edge_capture_i & hold_i & ~hold_q;
  wire permit = edge_capture_i ? (pending | asked) : ~hold_i;
  wire taking = load_i & permit;

  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      code_o  <= {N_BITS{1'b0}};
      done_o  <= 1'b0;
      pending <= 1'b0;
      // High, so a pin already high when reset lifts is not read as an edge.
      // There was no edge, and a request nobody made captures a result nobody
      // asked for.
      hold_q  <= 1'b1;
    end else begin
      hold_q <= hold_i;
      done_o <= taking;
      if (taking) begin
        code_o  <= code_i;
        pending <= 1'b0;
      end else if (asked) begin
        pending <= 1'b1;
      end
    end
  end

endmodule
