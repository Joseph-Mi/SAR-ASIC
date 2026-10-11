// The configuration the host writes, and when each write reaches the half that
// acts on it.
//
// Contract: address_i, wdata_i and write_i are one register access, as a frame
// delivers it -- write_i high for one cycle with the other two valid alongside.
// rdata_o answers whatever address_i presents, combinationally, so a frame that
// steps its address gets the next register with no turnaround cycle. An address
// the map does not have takes no write and reads as nothing: hardware cannot
// refuse one, having no way to tell the host, and a decoder that wrapped
// instead would land the write on a register that does exist.
//
// selected_i is high while a frame is open, converting_i while a search runs. A
// held write waits for both to clear. Both earn their place, for different
// reasons: a conversion must not have the array's drive change under it, and a
// field wider than one register takes more than one write, so the frame is what
// makes those writes one change rather than several.
//
// Reading a writable field returns what was last written to it, not what is in
// effect. The two differ only while a write is waiting, and a host that needs to
// know one has landed waits for the conversion to end.
//
// What the converter reports arrives here as wires and is stored nowhere, so a
// read of it sees the cycle it was asked in.
//
// Every address, offset and width below comes from the generated declarations,
// which are written out by the same model the tests grade this against.

module sar_regfile #(
    parameter integer REGISTER_WIDTH = 8,
    parameter integer N_BITS = 10,
    parameter integer VIEW_WIDTH = 2
) (
    input wire clk_i,
    input wire rst_ni,

    input  wire [REGISTER_WIDTH-2:0] address_i,
    input  wire [REGISTER_WIDTH-1:0] wdata_i,
    input  wire                      write_i,
    input  wire                      selected_i,
    output wire [REGISTER_WIDTH-1:0] rdata_o,

    input wire                      converting_i,
    input wire                      ready_i,
    input wire                      done_i,
    input wire                      metastable_i,
    input wire                      cmp_out_i,
    input wire [$clog2(N_BITS)-1:0] bit_index_i,

    output wire                      raw_dac_o,
    output wire                      force_en_o,
    output wire                      force_hi_o,
    output wire [REGISTER_WIDTH-1:0] clk_div_o,
    output wire [        N_BITS-1:0] dac_o,
    output wire [    VIEW_WIDTH-1:0] view_o
);

  `include "sar_regs.vh"

  localparam integer MAP_WIDTH = SAR_REGISTER_COUNT * SAR_REGISTER_WIDTH;

  // A frame can present a wider address than the map has registers. Selecting
  // inside the word needs only the map's own width, and narrowing first is what
  // keeps the index from being wider than anything it can address.
  localparam integer MAP_ADDRESS_WIDTH = $clog2(SAR_REGISTER_COUNT);
  localparam integer INDEX_WIDTH = $clog2(MAP_WIDTH);

  // What the host wrote, and what is in effect. One packed word each rather
  // than a register apiece: a whole-word copy is how a frame's writes take
  // effect together, and an unpacked array cannot be copied whole in this
  // dialect.
  reg [MAP_WIDTH-1:0] written;
  reg [MAP_WIDTH-1:0] live;

  // An address past the end of the map reads as nothing and takes no write, so
  // the index is pinned inside the word rather than selecting past its end.
  wire in_map = address_i < SAR_REGISTER_COUNT;
  wire [MAP_ADDRESS_WIDTH-1:0] address =
      in_map ? address_i[MAP_ADDRESS_WIDTH-1:0] : {MAP_ADDRESS_WIDTH{1'b0}};
  wire [INDEX_WIDTH-1:0] base = address * SAR_REGISTER_WIDTH;

  wire taking = write_i & in_map;
  wire settling = ~converting_i & ~selected_i;

  // Which bits of the addressed register the host may write, and which of those
  // reach the analog half the moment they are written.
  wire [SAR_REGISTER_WIDTH-1:0] writable = SAR_WRITABLE[base+:SAR_REGISTER_WIDTH];
  wire [SAR_REGISTER_WIDTH-1:0] waits = SAR_HELD[base+:SAR_REGISTER_WIDTH];
  wire [SAR_REGISTER_WIDTH-1:0] at_once = writable & ~waits;

  wire [SAR_REGISTER_WIDTH-1:0] was_written = written[base+:SAR_REGISTER_WIDTH];
  wire [SAR_REGISTER_WIDTH-1:0] was_live = live[base+:SAR_REGISTER_WIDTH];

  // A register is written whole, so a bit the host may not write keeps what it
  // had rather than taking what arrived with the bits beside it.
  wire [SAR_REGISTER_WIDTH-1:0] writes = (was_written & ~writable) | (wdata_i & writable);
  wire [SAR_REGISTER_WIDTH-1:0] lands = (was_live & ~at_once) | (wdata_i & at_once);

  // Everything the converter reports, placed where the map puts it. Cleared
  // first and then overridden, so a bit no field claims stays clear -- which is
  // what makes the writable mask enough to tell a reported bit from one that
  // reads as nothing.
  reg [MAP_WIDTH-1:0] reported;

  always @(*) begin
    reported = {MAP_WIDTH{1'b0}};
    reported[SAR_IDENTITY_ADDR*SAR_REGISTER_WIDTH+:SAR_IDENTITY_WIDTH] = SAR_IDENTITY_VALUE;
    reported[SAR_READY_ADDR*SAR_REGISTER_WIDTH+SAR_READY_SHIFT] = ready_i;
    reported[SAR_DONE_ADDR*SAR_REGISTER_WIDTH+SAR_DONE_SHIFT] = done_i;
    reported[SAR_METASTABLE_ADDR*SAR_REGISTER_WIDTH+SAR_METASTABLE_SHIFT] = metastable_i;
    reported[SAR_CMP_OUT_ADDR*SAR_REGISTER_WIDTH+SAR_CMP_OUT_SHIFT] = cmp_out_i;
    reported[SAR_BIT_INDEX_ADDR*SAR_REGISTER_WIDTH+SAR_BIT_INDEX_SHIFT+:SAR_BIT_INDEX_WIDTH] =
        bit_index_i;
  end

  wire [SAR_REGISTER_WIDTH-1:0] reports = reported[base+:SAR_REGISTER_WIDTH];

  assign rdata_o = in_map ? ((was_written & writable) | (reports & ~writable))
      : {SAR_REGISTER_WIDTH{1'b0}};

  // A field wider than one register is one part-select: its registers are
  // consecutive, least significant first, and that is the order the word packs
  // them in.
  assign raw_dac_o = live[SAR_RAW_DAC_ADDR*SAR_REGISTER_WIDTH+SAR_RAW_DAC_SHIFT];
  assign force_en_o = live[SAR_FORCE_EN_ADDR*SAR_REGISTER_WIDTH+SAR_FORCE_EN_SHIFT];
  assign force_hi_o = live[SAR_FORCE_HI_ADDR*SAR_REGISTER_WIDTH+SAR_FORCE_HI_SHIFT];
  assign clk_div_o = live[SAR_CLK_DIV_ADDR*SAR_REGISTER_WIDTH+SAR_CLK_DIV_SHIFT+:SAR_CLK_DIV_WIDTH];
  assign dac_o = live[SAR_DAC_ADDR*SAR_REGISTER_WIDTH+SAR_DAC_SHIFT+:SAR_DAC_WIDTH];
  assign view_o = live[SAR_VIEW_ADDR*SAR_REGISTER_WIDTH+SAR_VIEW_SHIFT+:SAR_VIEW_WIDTH];

  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      written <= SAR_RESET;
      live    <= SAR_RESET;
    end else begin
      if (taking) written[base+:SAR_REGISTER_WIDTH] <= writes;

      if (settling) begin
        // The waiting writes go together, and a write arriving on a cycle with
        // nothing in its way goes with them rather than a cycle later.
        live <= written;
        if (taking) live[base+:SAR_REGISTER_WIDTH] <= writes;
      end else if (taking) begin
        live[base+:SAR_REGISTER_WIDTH] <= lands;
      end
    end
  end

endmodule
