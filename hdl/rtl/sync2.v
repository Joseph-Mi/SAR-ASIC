// Two-flop synchroniser for one asynchronous input.
//
// Contract: d_i may change at any time relative to clk_i. q_o changes only on a
// clock edge and holds for the whole of it. The first stage is where
// metastability is resolved, so nothing may read that stage.

module sync2 (
    input  wire clk_i,
    input  wire rst_ni,
    input  wire d_i,
    output wire q_o
);

  localparam integer STAGES = 2;

  reg [STAGES-1:0] stage;

  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) stage <= {STAGES{1'b0}};
    else stage <= {stage[STAGES-2:0], d_i};
  end

  assign q_o = stage[STAGES-1];

endmodule
