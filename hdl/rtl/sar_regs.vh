// The register map, generated from the layout that declares it.
//
// Do not edit. Regenerate with `make regmap`.
//
// Declarations, not macros: these are included inside the module that needs
// them, so they are scoped to it. A macro would outlive the file that set it
// and reach every file compiled after.
//
// The scalars are untyped on purpose. Declared as integers they would be
// thirty-two bits wide, which widens every comparison against an address bus
// and every part-select that uses one, and the lint warning for it would be
// raised in the module rather than here.
//
// The packed words carry one register per byte, the lowest address in the
// lowest byte, so a part-select at an address times a register's width
// lands on that register's byte. A bit set in them means, in turn: the host
// may write it, that write waits for a conversion to end, and what it comes
// up as out of reset. A bit no writable field claims is not stored, so it is
// clear in all three.

localparam SAR_REGISTER_WIDTH = 8;
localparam SAR_REGISTER_COUNT = 8;

// What reading the identity register must return. A host checks it to know
// it means the same map, and because the value is never what an undriven
// line reads as, the same read catches a bus that is not answering.
localparam [SAR_REGISTER_WIDTH-1:0] SAR_IDENTITY_VALUE = 8'h68;

localparam [SAR_REGISTER_COUNT*SAR_REGISTER_WIDTH-1:0] SAR_WRITABLE = {
    8'h00,  // 0x07 search
    8'h00,  // 0x06 status
    8'h03,  // 0x05 view
    8'h03,  // 0x04 dac
    8'hff,  // 0x03 dac
    8'hff,  // 0x02 clk_div
    8'h07,  // 0x01 control
    8'h00  // 0x00 identity
};

localparam [SAR_REGISTER_COUNT*SAR_REGISTER_WIDTH-1:0] SAR_HELD = {
    8'h00,  // 0x07 search
    8'h00,  // 0x06 status
    8'h00,  // 0x05 view
    8'h03,  // 0x04 dac
    8'hff,  // 0x03 dac
    8'hff,  // 0x02 clk_div
    8'h07,  // 0x01 control
    8'h00  // 0x00 identity
};

localparam [SAR_REGISTER_COUNT*SAR_REGISTER_WIDTH-1:0] SAR_RESET = {
    8'h00,  // 0x07 search
    8'h00,  // 0x06 status
    8'h00,  // 0x05 view
    8'h00,  // 0x04 dac
    8'h00,  // 0x03 dac
    8'hff,  // 0x02 clk_div
    8'h00,  // 0x01 control
    8'h00  // 0x00 identity
};

// identity
localparam SAR_IDENTITY_ADDR = 0;
localparam SAR_IDENTITY_SHIFT = 0;
localparam SAR_IDENTITY_WIDTH = 8;
localparam SAR_IDENTITY_REGISTERS = 1;
// raw_dac
localparam SAR_RAW_DAC_ADDR = 1;
localparam SAR_RAW_DAC_SHIFT = 0;
localparam SAR_RAW_DAC_WIDTH = 1;
localparam SAR_RAW_DAC_REGISTERS = 1;
// force_en
localparam SAR_FORCE_EN_ADDR = 1;
localparam SAR_FORCE_EN_SHIFT = 1;
localparam SAR_FORCE_EN_WIDTH = 1;
localparam SAR_FORCE_EN_REGISTERS = 1;
// force_hi
localparam SAR_FORCE_HI_ADDR = 1;
localparam SAR_FORCE_HI_SHIFT = 2;
localparam SAR_FORCE_HI_WIDTH = 1;
localparam SAR_FORCE_HI_REGISTERS = 1;
// clk_div
localparam SAR_CLK_DIV_ADDR = 2;
localparam SAR_CLK_DIV_SHIFT = 0;
localparam SAR_CLK_DIV_WIDTH = 8;
localparam SAR_CLK_DIV_REGISTERS = 1;
// dac
localparam SAR_DAC_ADDR = 3;
localparam SAR_DAC_SHIFT = 0;
localparam SAR_DAC_WIDTH = 10;
localparam SAR_DAC_REGISTERS = 2;
// view
localparam SAR_VIEW_ADDR = 5;
localparam SAR_VIEW_SHIFT = 0;
localparam SAR_VIEW_WIDTH = 2;
localparam SAR_VIEW_REGISTERS = 1;
// ready
localparam SAR_READY_ADDR = 6;
localparam SAR_READY_SHIFT = 0;
localparam SAR_READY_WIDTH = 1;
localparam SAR_READY_REGISTERS = 1;
// done
localparam SAR_DONE_ADDR = 6;
localparam SAR_DONE_SHIFT = 1;
localparam SAR_DONE_WIDTH = 1;
localparam SAR_DONE_REGISTERS = 1;
// metastable
localparam SAR_METASTABLE_ADDR = 6;
localparam SAR_METASTABLE_SHIFT = 2;
localparam SAR_METASTABLE_WIDTH = 1;
localparam SAR_METASTABLE_REGISTERS = 1;
// cmp_out
localparam SAR_CMP_OUT_ADDR = 6;
localparam SAR_CMP_OUT_SHIFT = 3;
localparam SAR_CMP_OUT_WIDTH = 1;
localparam SAR_CMP_OUT_REGISTERS = 1;
// bit_index
localparam SAR_BIT_INDEX_ADDR = 7;
localparam SAR_BIT_INDEX_SHIFT = 0;
localparam SAR_BIT_INDEX_WIDTH = 4;
localparam SAR_BIT_INDEX_REGISTERS = 1;
