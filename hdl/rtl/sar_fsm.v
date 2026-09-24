// Successive-approximation control FSM. One bit trial per cycle, MSB first.
//
// Contract: the comparator answer must be stable for the whole cycle in which
// cmp_clk_o is high; it is captured on the rising edge that ends that cycle.
// Termination does not depend on the answers.
//
// code_o and metastable_o read together, and only while done_o is high. The
// code holds the previous result until the last trial replaces it, and the
// next start clears the flag, so a reader that samples either at another time
// gets the wrong conversion's answer.

module sar_fsm #(
    parameter integer N_BITS = 10
) (
    input  wire              clk_i,
    input  wire              rst_ni,
    input  wire              start_i,
    input  wire              cmp_out_i,
    input  wire              cmp_out_n_i,
    output reg  [N_BITS-1:0] dac_b_o,
    output reg               sample_o,
    output reg               cmp_clk_o,
    output reg  [N_BITS-1:0] code_o,
    output reg               ready_o,
    output reg               done_o,
    output reg               metastable_o
);

  localparam integer N_STATES = 5;
  localparam integer ST_W = $clog2(N_STATES);

  localparam [ST_W-1:0] ST_IDLE = 0;
  localparam [ST_W-1:0] ST_SAMPLE = 1;
  localparam [ST_W-1:0] ST_SETTLE = 2;
  localparam [ST_W-1:0] ST_EVAL = 3;
  localparam [ST_W-1:0] ST_DONE = 4;

  // $clog2 is zero at a width of one, which would declare a null vector.
  localparam integer IDX_W = (N_BITS > 1) ? $clog2(N_BITS) : 1;

  reg [ST_W-1:0] state, next_state;
  reg [IDX_W-1:0] bit_index;
  reg [N_BITS-1:0] settled;

  // Combinational, so the array holds it for the whole cycle the comparator
  // decides in rather than arriving a cycle late.
  wire [N_BITS-1:0] trial = settled | ({{(N_BITS - 1) {1'b0}}, 1'b1} << bit_index);

  // Equal outputs mean the latch never resolved.
  wire unresolved = (cmp_out_i == cmp_out_n_i);

  always @(*) begin
    next_state = state;
    case (state)
      ST_IDLE:   if (start_i) next_state = ST_SAMPLE;
      ST_SAMPLE: next_state = ST_SETTLE;
      ST_SETTLE: next_state = ST_EVAL;
      ST_EVAL:   next_state = (bit_index == {IDX_W{1'b0}}) ? ST_DONE : ST_SETTLE;
      ST_DONE:   next_state = ST_IDLE;
      default:   next_state = ST_IDLE;
    endcase
  end

  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state        <= ST_IDLE;
      bit_index    <= {IDX_W{1'b0}};
      settled      <= {N_BITS{1'b0}};
      dac_b_o      <= {N_BITS{1'b0}};
      code_o       <= {N_BITS{1'b0}};
      sample_o     <= 1'b0;
      cmp_clk_o    <= 1'b0;
      ready_o      <= 1'b1;
      done_o       <= 1'b0;
      metastable_o <= 1'b0;
    end else begin
      state     <= next_state;
      sample_o  <= (next_state == ST_SAMPLE);
      cmp_clk_o <= (next_state == ST_EVAL);
      ready_o   <= (next_state == ST_IDLE);
      done_o    <= (next_state == ST_DONE);

      case (state)
        ST_IDLE: begin
          if (start_i) begin
            settled      <= {N_BITS{1'b0}};
            dac_b_o      <= {N_BITS{1'b0}};
            bit_index    <= N_BITS[IDX_W-1:0] - {{(IDX_W - 1) {1'b0}}, 1'b1};
            metastable_o <= 1'b0;
          end
        end

        ST_SAMPLE: begin
          dac_b_o <= settled | ({{(N_BITS - 1) {1'b0}}, 1'b1} << bit_index);
        end

        ST_EVAL: begin
          // This cycle's decision, but the word driven out is the one the
          // next trial needs.
          if (cmp_out_i) settled <= trial;
          if (unresolved) metastable_o <= 1'b1;

          if (bit_index == {IDX_W{1'b0}}) begin
            dac_b_o <= cmp_out_i ? trial : settled;
            code_o  <= cmp_out_i ? trial : settled;
          end else begin
            dac_b_o <= (cmp_out_i ? trial : settled) |
                ({{(N_BITS - 1) {1'b0}}, 1'b1} << (bit_index - {{(IDX_W - 1) {1'b0}}, 1'b1}));
            bit_index <= bit_index - {{(IDX_W - 1) {1'b0}}, 1'b1};
          end
        end

        default: begin
          dac_b_o <= dac_b_o;
        end
      endcase
    end
  end

endmodule
