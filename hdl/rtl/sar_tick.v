// The conversion clock: how often the search is allowed to take a step.
//
// Contract: tick_o is high for exactly the cycles the search advances on, and
// the intervals between them are all the same length -- the first one after
// reset included. The sample phase is one such interval and it is the slowest
// path in the design, charging the whole array through the input pin where a
// bit trial charges a quarter of it, so an interval short by even a cycle is
// wrong there before anywhere else.
//
// divisor_i may move at any time. It takes effect from the next interval and
// never shortens the one in flight: cutting short the interval the array is
// already settling in is how a rate changed by hand decides a bit the array had
// not finished moving for. The field carrying it is held until no conversion is
// running, so a search never sees its own rate move at all.
//
// This is a clock enable, never a divided clock. A second clock is a second
// domain, and everything crossing between two of them needs a reason to be
// trusted; one domain means the configuration side, the result pins and the
// search all sample the same edge.
//
// The counter runs whether a conversion does or not, so a request to start
// waits up to one interval to be seen and has to outlive that wait: at the
// slowest rate the field can ask for, a request one cycle long is missed on all
// but one cycle in two hundred and fifty six.

module sar_tick #(
    parameter integer DIVISOR_WIDTH = 8
) (
    input  wire                     clk_i,
    input  wire                     rst_ni,
    input  wire [DIVISOR_WIDTH-1:0] divisor_i,
    output wire                     tick_o
);

  `include "sar_regs.vh"

  localparam [DIVISOR_WIDTH-1:0] ONE = {{(DIVISOR_WIDTH - 1) {1'b0}}, 1'b1};

  // Cycles left of the interval in progress.
  reg [DIVISOR_WIDTH-1:0] remaining;

  // Counting down rather than up makes the comparison zero whatever the
  // divisor, and the divisor is read only where the count reloads -- which is
  // what keeps a change out of the interval it arrived in.
  assign tick_o = (remaining == {DIVISOR_WIDTH{1'b0}});

  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      // The field's own reset value, so the interval reset leaves behind is as
      // long as every other one and no number is written down twice.
      remaining <= SAR_CLK_DIV_RESET[DIVISOR_WIDTH-1:0];
    end else if (tick_o) begin
      remaining <= divisor_i;
    end else begin
      remaining <= remaining - ONE;
    end
  end

endmodule
