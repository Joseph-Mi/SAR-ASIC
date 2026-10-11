// The digital half, wired up: the pins on one side, the analog block on the
// other.
//
// Contract: this is the macro the place-and-route flow hardens. Its three pin
// groups are the platform's, and which signal each pin carries is the pin map's
// to say -- nothing is chosen here, and a test fails if the positions below
// stop matching it. Its remaining ports are the frozen analog boundary. The
// tile top the platform requires wraps this together with the analog block and
// attaches the analog pins; the platform's enable is read there rather than
// here, being the one signal a project is told it may ignore.
//
// One clock domain, and every asynchronous pin goes through two flops before
// anything reads it: the four dedicated inputs here, and the three
// configuration pins inside the slave that oversamples them, where they belong.
//
// A conversion is never disturbed from outside. Configuration the analog half
// acts on is held until the search ends, a request to start is read only while
// the search is idle, and holding a result does not hold the converter.
//
// Two design-for-test modes put a stream on the result pins instead of a
// result: the latch's two outputs, or which bit the search is trialling. Both
// sit in the bits the dedicated outputs carry, because those pins cannot
// contend with anything on the board.
//
// Raw DAC mode replaces only the word driven at the array. The search keeps
// running, so the array is still sampled and the comparator still strobed --
// which is what makes the mode a measurement: hold the array at a chosen word
// and the comparator says which side of the common mode the top plate came out.

module sar_top #(
    parameter integer N_BITS = 10,
    parameter integer REGISTER_WIDTH = 8,
    parameter integer VIEW_WIDTH = 2,
    parameter integer VIEW_COMPARATOR = 1,
    parameter integer VIEW_SEARCH = 2,
    parameter integer PINS = 8
) (
    input  wire            clk,
    input  wire            rst_n,
    input  wire [PINS-1:0] ui_in,
    output wire [PINS-1:0] uo_out,
    input  wire [PINS-1:0] uio_in,
    output wire [PINS-1:0] uio_out,
    output wire [PINS-1:0] uio_oe,

    output wire [N_BITS-1:0] dac_b_o,
    output wire              sample_o,
    output wire              cmp_clk_o,
    output wire              force_en_o,
    output wire              force_hi_o,
    input  wire              cmp_out_i,
    input  wire              cmp_out_n_i
);

  // Where the pin map puts each signal. A result bit is placed by the
  // arithmetic below rather than named: there is one of them per bit.
  localparam integer UI_IN_HOLD = 0;
  localparam integer UI_IN_START = 1;
  localparam integer UI_IN_SINGLE_SHOT = 2;
  localparam integer UI_IN_EDGE_CAPTURE = 3;
  localparam integer UIO_SPI_CS_N = 0;
  localparam integer UIO_SPI_MOSI = 1;
  localparam integer UIO_SPI_MISO = 2;
  localparam integer UIO_SPI_SCK = 3;
  localparam integer UIO_SPILL = 4;
  localparam integer UIO_DONE = 6;

  // A bit set where the design drives a bidirectional pin. A pin it does not
  // drive -- an input, or one it does not use -- then never contends with
  // whatever is on the other side of it.
  localparam [PINS-1:0] UIO_OE = 8'b0111_0100;

  // Bits of the result the dedicated outputs cannot hold, and the bits they
  // can. The same arithmetic the pin map does, which is why neither count is
  // a parameter to be set wrong.
  localparam integer SPILLED = (N_BITS > PINS) ? (N_BITS - PINS) : 0;
  localparam integer PROBED = N_BITS - SPILLED;

  localparam integer INDEX_WIDTH = $clog2(N_BITS);

  localparam [VIEW_WIDTH-1:0] SHOW_COMPARATOR = VIEW_COMPARATOR[VIEW_WIDTH-1:0];
  localparam [VIEW_WIDTH-1:0] SHOW_SEARCH = VIEW_SEARCH[VIEW_WIDTH-1:0];

  wire hold_s, request_s, single_shot_s, edge_capture_s;

  sync2 u_hold (
      .clk_i (clk),
      .rst_ni(rst_n),
      .d_i   (ui_in[UI_IN_HOLD]),
      .q_o   (hold_s)
  );
  sync2 u_request (
      .clk_i (clk),
      .rst_ni(rst_n),
      .d_i   (ui_in[UI_IN_START]),
      .q_o   (request_s)
  );
  sync2 u_single_shot (
      .clk_i (clk),
      .rst_ni(rst_n),
      .d_i   (ui_in[UI_IN_SINGLE_SHOT]),
      .q_o   (single_shot_s)
  );
  sync2 u_edge_capture (
      .clk_i (clk),
      .rst_ni(rst_n),
      .d_i   (ui_in[UI_IN_EDGE_CAPTURE]),
      .q_o   (edge_capture_s)
  );

  wire                      miso;
  wire [REGISTER_WIDTH-2:0] address;
  wire [REGISTER_WIDTH-1:0] wdata;
  wire [REGISTER_WIDTH-1:0] rdata;
  wire                      write;
  wire                      selected;

  sar_spi #(
      .REGISTER_WIDTH(REGISTER_WIDTH)
  ) u_spi (
      .clk_i     (clk),
      .rst_ni    (rst_n),
      .sck_i     (uio_in[UIO_SPI_SCK]),
      .cs_ni     (uio_in[UIO_SPI_CS_N]),
      .mosi_i    (uio_in[UIO_SPI_MOSI]),
      .miso_o    (miso),
      .address_o (address),
      .wdata_o   (wdata),
      .write_o   (write),
      .selected_o(selected),
      .rdata_i   (rdata)
  );

  wire                      raw_dac;
  wire                      force_en;
  wire                      force_hi;
  wire [REGISTER_WIDTH-1:0] clk_div;
  wire [        N_BITS-1:0] dac;
  wire [    VIEW_WIDTH-1:0] view;

  wire                      tick;
  wire                      start;
  wire [        N_BITS-1:0] trial;
  wire [        N_BITS-1:0] code;
  wire                      sample;
  wire                      cmp_clk;
  wire                      ready;
  wire                      finished;
  wire                      metastable;
  wire [   INDEX_WIDTH-1:0] bit_index;

  wire [        N_BITS-1:0] result;
  wire                      flag;

  sar_regfile #(
      .REGISTER_WIDTH(REGISTER_WIDTH),
      .N_BITS(N_BITS),
      .VIEW_WIDTH(VIEW_WIDTH)
  ) u_regfile (
      .clk_i       (clk),
      .rst_ni      (rst_n),
      .address_i   (address),
      .wdata_i     (wdata),
      .write_i     (write),
      .selected_i  (selected),
      .rdata_o     (rdata),
      .converting_i(~ready),
      .ready_i     (ready),
      // The flag the pins carry, so the word means the same thing read either
      // way: the result pins just changed.
      .done_i      (flag),
      .metastable_i(metastable),
      // The wire itself, not a decision taken from it. Read between trials it
      // shows the latch precharged, which is what the wire is doing; what a
      // decision came to is read from the code.
      .cmp_out_i   (cmp_out_i),
      .bit_index_i (bit_index),
      .raw_dac_o   (raw_dac),
      .force_en_o  (force_en),
      .force_hi_o  (force_hi),
      .clk_div_o   (clk_div),
      .dac_o       (dac),
      .view_o      (view)
  );

  sar_tick #(
      .DIVISOR_WIDTH(REGISTER_WIDTH)
  ) u_tick (
      .clk_i    (clk),
      .rst_ni   (rst_n),
      .divisor_i(clk_div),
      .tick_o   (tick)
  );

  sar_start u_start (
      .clk_i        (clk),
      .rst_ni       (rst_n),
      .request_i    (request_s),
      .single_shot_i(single_shot_s),
      .ready_i      (ready),
      .tick_i       (tick),
      .start_o      (start)
  );

  sar_fsm #(
      .N_BITS(N_BITS)
  ) u_fsm (
      .clk_i       (clk),
      .rst_ni      (rst_n),
      .en_i        (tick),
      .start_i     (start),
      .cmp_out_i   (cmp_out_i),
      .cmp_out_n_i (cmp_out_n_i),
      .dac_b_o     (trial),
      .sample_o    (sample),
      .cmp_clk_o   (cmp_clk),
      .code_o      (code),
      .ready_o     (ready),
      .done_o      (finished),
      .metastable_o(metastable),
      .bit_index_o (bit_index)
  );

  // The search holds done for the whole interval between two steps, and the
  // holding register must take a result once, not once per cycle of it. The
  // step that ends the interval is that one cycle, and the code has been
  // settled since the interval began.
  wire load = finished & tick;

  sar_readout #(
      .N_BITS(N_BITS)
  ) u_readout (
      .clk_i         (clk),
      .rst_ni        (rst_n),
      .load_i        (load),
      .code_i        (code),
      .hold_i        (hold_s),
      .edge_capture_i(edge_capture_s),
      .code_o        (result),
      .done_o        (flag)
  );

  // What the result pins carry. The result unless asked otherwise, so a part
  // nobody has configured reads as a converter.
  reg [N_BITS-1:0] shown;

  always @(*) begin
    shown = result;
    if (view == SHOW_COMPARATOR) begin
      shown = {N_BITS{1'b0}};
      shown[SPILLED+0] = cmp_out_i;
      shown[SPILLED+1] = cmp_out_n_i;
    end else if (view == SHOW_SEARCH) begin
      shown = {N_BITS{1'b0}};
      shown[SPILLED+:INDEX_WIDTH] = bit_index;
    end
  end

  reg [PINS-1:0] driving;

  always @(*) begin
    driving = {PINS{1'b0}};
    driving[UIO_SPI_MISO] = miso;
    driving[UIO_SPILL+:SPILLED] = shown[0+:SPILLED];
    driving[UIO_DONE] = flag;
  end

  assign uo_out = shown[SPILLED+:PROBED];
  assign uio_out = driving;
  assign uio_oe = UIO_OE;

  // Raw DAC mode replaces the word the search would have driven, and nothing
  // else: the array is still sampled and the comparator still strobed.
  assign dac_b_o = raw_dac ? dac : trial;
  assign sample_o = sample;
  assign cmp_clk_o = cmp_clk;
  assign force_en_o = force_en;
  assign force_hi_o = force_hi;

endmodule
