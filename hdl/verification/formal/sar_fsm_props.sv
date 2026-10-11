// Properties of the successive-approximation control FSM, proved rather than
// sampled.
//
// Contract: this is a formal harness and not a testbench. It drives nothing --
// the solver chooses the comparator's answers, the request, the enable and the
// reset, so every assertion below holds for every sequence of them. That is
// the one claim a simulation cannot make: the hostile-comparator tests pick
// all-ones, all-zeros and a few random sequences out of a space of 2**N, and
// the contract with the analog half has to hold over all of it.
//
// Bound as a wrapper rather than with `bind` so the device under test stays
// Verilog-2005 and this file stays outside it.

`default_nettype none

module sar_fsm_props #(
    parameter integer N_BITS = 10
) (
    input wire clk_i,
    input wire rst_ni,
    input wire en_i,
    input wire start_i,
    input wire cmp_out_i,
    input wire cmp_out_n_i
);

  // Enabled steps a conversion takes, from the one that accepts the request to
  // the one that raises the flag: the sample, two for every bit trial, and the
  // handover. The protocol model owns this shape; a test fails if the two
  // stop agreeing.
  localparam integer CONVERSION_STEPS = 2 * N_BITS + 2;

  localparam integer COUNT_W = $clog2(CONVERSION_STEPS + 2);
  localparam integer IDX_W = (N_BITS > 1) ? $clog2(N_BITS) : 1;
  localparam [N_BITS-1:0] ALL_GROUND = {N_BITS{1'b0}};

  wire [N_BITS-1:0] dac_b;
  wire [N_BITS-1:0] code;
  wire sample;
  wire cmp_clk;
  wire ready;
  wire done;
  wire metastable;
  wire [IDX_W-1:0] bit_index;

  sar_fsm #(
      .N_BITS(N_BITS)
  ) dut (
      .clk_i       (clk_i),
      .rst_ni      (rst_ni),
      .en_i        (en_i),
      .start_i     (start_i),
      .cmp_out_i   (cmp_out_i),
      .cmp_out_n_i (cmp_out_n_i),
      .dac_b_o     (dac_b),
      .sample_o    (sample),
      .cmp_clk_o   (cmp_clk),
      .code_o      (code),
      .ready_o     (ready),
      .done_o      (done),
      .metastable_o(metastable),
      .bit_index_o (bit_index)
  );

  // Reset is held for the first cycle and released for good. Letting the
  // solver reassert it would make every property conditional on a reset that
  // never comes, which proves nothing about a running part.
  reg started = 1'b0;
  always @(posedge clk_i) started <= 1'b1;
  always @(*) assume (rst_ni == started);

`ifdef STEPPING
  // The bound is counted in steps, not cycles, so proving it needs the search
  // to be stepping. That the search stands still otherwise is the separate
  // property below, proved without this assumption.
  always @(*) assume (en_i);
`endif

  wire converting = !ready && !done;
  wire unresolved = (cmp_out_i == cmp_out_n_i);
  wire accepting = ready && start_i;

  reg [COUNT_W-1:0] steps;
  reg running;
  reg unresolved_seen;

  reg stepped;
  reg was_cmp_clk;
  reg was_done;

  reg [N_BITS-1:0] was_dac_b;
  reg [N_BITS-1:0] was_code;
  reg was_sample;
  reg was_ready;
  reg was_metastable;
  reg [IDX_W-1:0] was_bit_index;
  reg was_cmp_clk_any;
  reg was_done_any;

  always @(posedge clk_i) begin
    if (!rst_ni) begin
      steps           <= {COUNT_W{1'b0}};
      running         <= 1'b0;
      unresolved_seen <= 1'b0;
      was_cmp_clk     <= 1'b0;
      was_done        <= 1'b0;
    end else if (en_i) begin
      if (done) begin
        running <= 1'b0;
        steps   <= {COUNT_W{1'b0}};
      end else if (running) begin
        steps <= steps + {{(COUNT_W - 1) {1'b0}}, 1'b1};
      end else if (accepting) begin
        running <= 1'b1;
        steps   <= {{(COUNT_W - 1) {1'b0}}, 1'b1};
      end

      if (accepting) unresolved_seen <= 1'b0;
      else if (cmp_clk && unresolved) unresolved_seen <= 1'b1;

      was_cmp_clk <= cmp_clk;
      was_done    <= done;
    end
  end

  always @(posedge clk_i) begin
    stepped         <= en_i;
    was_dac_b       <= dac_b;
    was_code        <= code;
    was_sample      <= sample;
    was_ready       <= ready;
    was_metastable  <= metastable;
    was_bit_index   <= bit_index;
    was_cmp_clk_any <= cmp_clk;
    was_done_any    <= done;
  end

  // Two kinds of claim, proved two ways. Everything about a conversion is an
  // invariant of the states a conversion reaches, so it is proved by bounded
  // model checking from reset, where reachability is given. That a step which
  // is not enabled changes nothing is local to one cycle, so it is proved by
  // induction and therefore holds for a stall of any length -- which bounded
  // checking from reset could never say.
  always @(posedge clk_i) begin
    if (started && rst_ni) begin
`ifdef STEPPING
      // The contract with the analog half. All-ground while a sample is held
      // pulls the sealed top plate below ground, where the top switch's
      // junction conducts and the held charge drains -- so the word carries
      // the first trial from the moment the request is accepted, and every
      // trial word has a bit set by construction.
      if (converting) assert (dac_b != ALL_GROUND);

      // Termination, over every answer the comparator can give. The search
      // advances on its own and the answers only choose the word, so the step
      // count is the same for all of them.
      assert (steps <= CONVERSION_STEPS[COUNT_W-1:0]);
      if (running && steps == CONVERSION_STEPS[COUNT_W-1:0]) assert (done);

      // The latch precharges between trials. A strobe held across two steps
      // takes one decision and reports it twice, which is a conversion whose
      // every bit after the first is a copy.
      if (was_cmp_clk) assert (!cmp_clk);

      // The flag is up for exactly one step, in every mode, so a reader waits
      // for it once per conversion.
      if (was_done) assert (!done);

      // The index addresses a bit that exists. Its width holds values past
      // the top of the array, and an index that ran off the end would trial a
      // branch that is not there.
      if (converting) assert (bit_index < N_BITS[IDX_W-1:0]);

      // Never two phases at once. The analog half reads these as the phase it
      // is in, and a combination claiming two would have it sampling while the
      // comparator strobes -- sealing the top plate in the middle of a
      // decision. It also settles what the state encoding's unused values can
      // do: nothing, because no reachable state presents such a combination.
      assert (!(ready && sample));
      assert (!(ready && cmp_clk));
      assert (!(ready && done));
      assert (!(sample && cmp_clk));
      assert (!(sample && done));
      assert (!(cmp_clk && done));

      // The flag means what it says, both ways: it is never raised without an
      // unresolved latch, and never withheld once there has been one.
      if (metastable) assert (unresolved_seen || !running);
      if (running && unresolved_seen) assert (metastable);
`else
      // The enable gates the state and not the clock, so a step that is not
      // enabled changes nothing a reader or the array can see.
      if (!stepped) begin
        assert (dac_b == was_dac_b);
        assert (code == was_code);
        assert (sample == was_sample);
        assert (cmp_clk == was_cmp_clk_any);
        assert (ready == was_ready);
        assert (done == was_done_any);
        assert (metastable == was_metastable);
        assert (bit_index == was_bit_index);
      end
`endif
    end
  end

endmodule

`default_nettype wire
