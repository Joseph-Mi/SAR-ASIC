// SPI slave for the configuration registers, oversampled in the system clock
// domain rather than clocked by the wire.
//
// Contract: sck_i, cs_ni and mosi_i are asynchronous pins, sampled by clk_i.
// Each phase of sck_i must therefore last long enough to be seen -- two clk_i
// periods, so sck_i is at most a quarter of clk_i. A faster wire drops bits, and
// a frame corrupted that way can still land a write, so a host confirms a
// configuration by reading it back.
//
// A frame is one assertion of cs_ni. Its first byte is a direction bit and an
// address; every byte after it is data, and address_o steps on by one for each.
// write_o is high for one clk_i cycle per byte a write frame delivers, with
// address_o and wdata_o valid alongside it.
//
// miso_o is driven whenever the pin is an output, and the pin always is: there
// is one slave on this wire, so a constant output enable is one fewer thing for
// the pin map to make conditional. It reads zero while nothing is selected, and
// throughout a write.

module sar_spi #(
    parameter integer REGISTER_WIDTH = 8
) (
    input  wire                      clk_i,
    input  wire                      rst_ni,
    input  wire                      sck_i,
    input  wire                      cs_ni,
    input  wire                      mosi_i,
    output wire                      miso_o,
    output reg  [REGISTER_WIDTH-2:0] address_o,
    output reg  [REGISTER_WIDTH-1:0] wdata_o,
    output reg                       write_o,
    output wire                      selected_o,
    input  wire [REGISTER_WIDTH-1:0] rdata_i
);

  // The command byte's top bit says which way the frame goes; the rest is the
  // address, so that is how wide an address can be.
  localparam integer DIRECTION = REGISTER_WIDTH - 1;
  localparam integer ADDRESS_WIDTH = REGISTER_WIDTH - 1;
  localparam integer COUNT_WIDTH = $clog2(REGISTER_WIDTH);

  wire sck_s, cs_n_s, mosi_s;

  sync2 u_sck (
      .clk_i (clk_i),
      .rst_ni(rst_ni),
      .d_i   (sck_i),
      .q_o   (sck_s)
  );
  sync2 u_cs_n (
      .clk_i (clk_i),
      .rst_ni(rst_ni),
      .d_i   (cs_ni),
      .q_o   (cs_n_s)
  );
  // Synchronised like the others so it arrives with the same delay: a bit
  // sampled on an edge that has been through two flops has to have been through
  // two flops itself.
  sync2 u_mosi (
      .clk_i (clk_i),
      .rst_ni(rst_ni),
      .d_i   (mosi_i),
      .q_o   (mosi_s)
  );

  reg                       sck_q;
  // One bit narrower than a byte: it holds the bits already in, and the bit
  // arriving completes them. A full byte here would leave its top bit written
  // and never read.
  reg  [REGISTER_WIDTH-2:0] shift;
  reg  [REGISTER_WIDTH-1:0] out_shift;
  reg  [   COUNT_WIDTH-1:0] bit_count;
  reg                       expecting_command;
  reg                       writing;
  // The address moves on a cycle after the byte that filled it, so write_o and
  // address_o are valid together: a register file told to write would otherwise
  // be handed the address of the byte after the one it is writing.
  reg                       step_address;

  wire                      sck_rise = sck_s & ~sck_q;
  wire                      sck_fall = ~sck_s & sck_q;

  // The byte that is complete on this rising edge: what was shifted in before,
  // plus the bit arriving now.
  wire [REGISTER_WIDTH-1:0] byte_in = {shift, mosi_s};
  wire                      last_bit = bit_count == {COUNT_WIDTH{1'b1}};

  // Stops at the top of the address space instead of wrapping. Wrapping would
  // carry a long frame back round onto a register that exists, and land a write
  // the host never asked for; the top of the space reaches nothing.
  wire [ ADDRESS_WIDTH-1:0] next_address = address_o + {{(ADDRESS_WIDTH - 1) {1'b0}}, 1'b1};
  wire                      address_full = address_o == {ADDRESS_WIDTH{1'b1}};

  assign selected_o = ~cs_n_s;
  assign miso_o = out_shift[REGISTER_WIDTH-1];

  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      sck_q             <= 1'b0;
      step_address      <= 1'b0;
      shift             <= {(REGISTER_WIDTH - 1) {1'b0}};
      out_shift         <= {REGISTER_WIDTH{1'b0}};
      bit_count         <= {COUNT_WIDTH{1'b0}};
      expecting_command <= 1'b1;
      writing           <= 1'b0;
      address_o         <= {ADDRESS_WIDTH{1'b0}};
      wdata_o           <= {REGISTER_WIDTH{1'b0}};
      write_o           <= 1'b0;
    end else begin
      sck_q   <= sck_s;
      write_o <= 1'b0;

      if (!selected_o) begin
        // Nothing of a frame survives its select line. A frame cut short mid
        // byte leaves bits in the shifter, and carrying them into the next one
        // would turn two partial frames into one wrong write.
        bit_count         <= {COUNT_WIDTH{1'b0}};
        expecting_command <= 1'b1;
        writing           <= 1'b0;
        step_address      <= 1'b0;
        out_shift         <= {REGISTER_WIDTH{1'b0}};
      end else begin
        if (step_address) begin
          address_o    <= address_full ? address_o : next_address;
          step_address <= 1'b0;
        end

        if (sck_rise) begin
          shift     <= byte_in[REGISTER_WIDTH-2:0];
          bit_count <= bit_count + {{(COUNT_WIDTH - 1) {1'b0}}, 1'b1};
          if (last_bit) begin
            if (expecting_command) begin
              expecting_command <= 1'b0;
              writing           <= byte_in[DIRECTION];
              address_o         <= byte_in[ADDRESS_WIDTH-1:0];
            end else begin
              if (writing) begin
                wdata_o <= byte_in;
                write_o <= 1'b1;
              end
              step_address <= 1'b1;
            end
          end
        end

        if (sck_fall) begin
          // A byte boundary has just moved the address on, so the register it
          // now names is the one the next byte carries out. Within a byte the
          // word walks out most significant bit first.
          if (bit_count == {COUNT_WIDTH{1'b0}}) begin
            out_shift <= (writing || expecting_command) ? {REGISTER_WIDTH{1'b0}} : rdata_i;
          end else begin
            out_shift <= {out_shift[REGISTER_WIDTH-2:0], 1'b0};
          end
        end
      end
    end
  end

endmodule
