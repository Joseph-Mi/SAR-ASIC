// smoke_dut.v
//
// Toolchain smoke test only. Not part of the design. Exists so that pytest
// proves Verilator and cocotb are wired up before any real RTL lands.
//
// Contract: none. Delete this directory once hdl/rtl/ has a module with its
//           own testbench.

module smoke_dut #(
    parameter N_BITS = 8
) (
    input  wire              clk_i,
    input  wire              rst_ni,
    input  wire              en_i,
    output wire [N_BITS-1:0] count_o
);

    localparam [N_BITS-1:0] COUNT_RESET = {N_BITS{1'b0}};
    localparam [N_BITS-1:0] COUNT_STEP  = {{(N_BITS-1){1'b0}}, 1'b1};

    reg [N_BITS-1:0] count_q;

    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            count_q <= COUNT_RESET;
        end else if (en_i) begin
            count_q <= count_q + COUNT_STEP;
        end
    end

    assign count_o = count_q;

endmodule
