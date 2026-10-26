// The tile, as the platform takes delivery of it: the digital pin groups on
// one edge, the analog pins on the other, and the two halves of the converter
// between them.
//
// Contract: the port list is the platform's, copied from its template -- every
// name, width and direction, in that order. A test holds it against the
// vendored DEF in `layout/`, which is the file the shuttle places the pins
// from, because a port named wrongly here is a pin that is not connected and
// cannot be fixed after submission. The module name is the platform's too: it
// has to start with `tt_um_`, be unique on the shuttle, and match the names of
// the GDS and LEF handed in beside it.
//
// Nothing is chosen here. The pin map says which signal each pin carries,
// `reference/interface.py` says what crosses to the analog half, and this is
// where the two meet.
//
// What the tile top has that the digital macro does not is the analog
// attachment, the supplies and the platform's enable. The enable is left
// unread deliberately, being the one signal a project is told it may ignore:
// the platform holds it high whenever the design is powered, and the only way
// to use it would be to put a tile-select line into the reset or the clock of
// a converter that may be mid-conversion. The supplies are read, because the
// analog half's terminals are what they are for.
//
// The analog pins are taken from `ua[0]` upward with no gaps. That is the
// platform's rule rather than a preference -- pins are connected one at a time
// as the submission declares them, so a gap is a pin paid for and not bonded.
// Which of the three takes which index is still open: it follows the analog
// strip's own placement, and that is not drawn yet.
//
// `ua[3]` and above are left unconnected here. Tying off an unused analog pin
// is layout's job and not Verilog's -- there is nothing a digital driver
// should be doing on a pin that reaches a pad through an analog switch.

module tt_um_josephmi_sar_adc #(
    parameter integer N_BITS = 10
) (
    input  wire       VGND,
    input  wire       VDPWR,    // 1.8 V supply; the 3.3 V rail is not used
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    inout  wire [7:0] ua,       // Analog pins, only ua[5:0] can be used
    input  wire       ena,      // always 1 when the design is powered
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  // Where the pin map puts each analog signal. Provisional, as the header
  // says, and declared in one place: a test fails if these stop matching the
  // map.
  localparam integer UA_VIN = 0;
  localparam integer UA_VREF = 1;
  localparam integer UA_VCM = 2;

  // The supplies, handed on as the terminals the analog half declares them to
  // be. They arrive here as inputs because that is how the platform's template
  // declares them, and a port map cannot pass an input straight into a
  // terminal, so they are carried across by name.
  wire vdd = VDPWR;
  wire vss = VGND;

  // The frozen boundary between the halves.
  wire [N_BITS-1:0] dac_b;
  wire sample, cmp_clk, force_en, force_hi;
  wire cmp_out, cmp_out_n;

  sar_top #(
      .N_BITS(N_BITS)
  ) u_digital (
      .clk        (clk),
      .rst_n      (rst_n),
      .ui_in      (ui_in),
      .uo_out     (uo_out),
      .uio_in     (uio_in),
      .uio_out    (uio_out),
      .uio_oe     (uio_oe),
      .dac_b_o    (dac_b),
      .sample_o   (sample),
      .cmp_clk_o  (cmp_clk),
      .force_en_o (force_en),
      .force_hi_o (force_hi),
      .cmp_out_i  (cmp_out),
      .cmp_out_n_i(cmp_out_n)
  );

  sar_analog #(
      .N_BITS(N_BITS)
  ) u_analog (
      .dac_b    (dac_b),
      .sample   (sample),
      .cmp_clk  (cmp_clk),
      .force_en (force_en),
      .force_hi (force_hi),
      .cmp_out  (cmp_out),
      .cmp_out_n(cmp_out_n),
      .vin      (ua[UA_VIN]),
      .vref     (ua[UA_VREF]),
      .vcm      (ua[UA_VCM]),
      .vdd      (vdd),
      .vss      (vss)
  );

endmodule
