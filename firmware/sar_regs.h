/* The register map, generated from the layout that declares it.
 *
 * Do not edit. Regenerate with `make regmap`.
 *
 * A frame is one assertion of the select line: a command byte saying which
 * way and where, then one byte per register, the address stepping on by one
 * for each. A field wider than one register is carried least significant
 * register first, and one frame is what makes those writes one change.
 *
 * A register is written whole, so setting one field of an address means
 * reading the others back and writing them with what they hold. Writing a
 * value nobody asked for is what leaving one out does.
 */
#ifndef SAR_REGS_H
#define SAR_REGS_H

#include <stdint.h>

#define SAR_REGISTER_WIDTH 8u
#define SAR_REGISTER_COUNT 7u

/* The map both ends have to agree on. Firmware states the map it was written
 * against once, and SAR_REQUIRE_MAP refuses to compile against another. */
#define SAR_MAP_HASH 0x3b6f8834u
#define SAR_REQUIRE_MAP(hash) \
  _Static_assert((hash) == SAR_MAP_HASH, "the register map has moved")

/* The command byte. The direction bit means write when it is set, so a line
 * nobody drives reads the first register and changes nothing. */
#define SAR_FRAME_WRITE 0x80u
#define SAR_FRAME_ADDRESS_MASK 0x7fu
#define SAR_FRAME_IDLE_BYTE 0x00u

static inline uint8_t sar_command(uint8_t address, int write)
{
  return (uint8_t)((write ? SAR_FRAME_WRITE : 0u) | (address & SAR_FRAME_ADDRESS_MASK));
}

/* One register's worth of a field, least significant register first: the bytes
 * a frame carries, in the order it carries them. */
static inline uint8_t sar_field_byte(uint32_t value, unsigned index)
{
  return (uint8_t)(value >> (index * SAR_REGISTER_WIDTH));
}

#define SAR_FIELD_GET(reg, shift, mask) (((reg) >> (shift)) & (mask))
#define SAR_FIELD_SET(reg, shift, mask, value) \
  (((reg) & ~((mask) << (shift))) | (((value) & (mask)) << (shift)))

/* control @ 0x00 */
#define SAR_ADDR_CONTROL 0x00u
/* raw_dac: 1 bit, rw, held */
#define SAR_RAW_DAC_ADDR 0x00u
#define SAR_RAW_DAC_REGISTERS 1u
#define SAR_RAW_DAC_WIDTH 1u
#define SAR_RAW_DAC_SHIFT 0u
#define SAR_RAW_DAC_MASK 0x1u
#define SAR_RAW_DAC_WRITABLE 1
#define SAR_RAW_DAC_HELD 1
#define SAR_RAW_DAC_RESET 0x0u
/* force_en: 1 bit, rw, held */
#define SAR_FORCE_EN_ADDR 0x00u
#define SAR_FORCE_EN_REGISTERS 1u
#define SAR_FORCE_EN_WIDTH 1u
#define SAR_FORCE_EN_SHIFT 1u
#define SAR_FORCE_EN_MASK 0x1u
#define SAR_FORCE_EN_WRITABLE 1
#define SAR_FORCE_EN_HELD 1
#define SAR_FORCE_EN_RESET 0x0u
/* force_hi: 1 bit, rw, held */
#define SAR_FORCE_HI_ADDR 0x00u
#define SAR_FORCE_HI_REGISTERS 1u
#define SAR_FORCE_HI_WIDTH 1u
#define SAR_FORCE_HI_SHIFT 2u
#define SAR_FORCE_HI_MASK 0x1u
#define SAR_FORCE_HI_WRITABLE 1
#define SAR_FORCE_HI_HELD 1
#define SAR_FORCE_HI_RESET 0x0u

/* clk_div @ 0x01 */
#define SAR_ADDR_CLK_DIV 0x01u
/* clk_div: 8 bit, rw, held */
#define SAR_CLK_DIV_ADDR 0x01u
#define SAR_CLK_DIV_REGISTERS 1u
#define SAR_CLK_DIV_WIDTH 8u
#define SAR_CLK_DIV_SHIFT 0u
#define SAR_CLK_DIV_MASK 0xffu
#define SAR_CLK_DIV_WRITABLE 1
#define SAR_CLK_DIV_HELD 1
#define SAR_CLK_DIV_RESET 0xffu

/* dac @ 0x02..0x03 */
#define SAR_ADDR_DAC 0x02u
/* dac: 10 bit, rw, held */
#define SAR_DAC_ADDR 0x02u
#define SAR_DAC_REGISTERS 2u
#define SAR_DAC_WIDTH 10u
#define SAR_DAC_SHIFT 0u
#define SAR_DAC_MASK 0x3ffu
#define SAR_DAC_WRITABLE 1
#define SAR_DAC_HELD 1
#define SAR_DAC_RESET 0x0u

/* view @ 0x04 */
#define SAR_ADDR_VIEW 0x04u
/* view: 2 bit, rw */
#define SAR_VIEW_ADDR 0x04u
#define SAR_VIEW_REGISTERS 1u
#define SAR_VIEW_WIDTH 2u
#define SAR_VIEW_SHIFT 0u
#define SAR_VIEW_MASK 0x3u
#define SAR_VIEW_WRITABLE 1
#define SAR_VIEW_HELD 0
#define SAR_VIEW_RESET 0x0u

/* status @ 0x05 */
#define SAR_ADDR_STATUS 0x05u
/* ready: 1 bit, ro */
#define SAR_READY_ADDR 0x05u
#define SAR_READY_REGISTERS 1u
#define SAR_READY_WIDTH 1u
#define SAR_READY_SHIFT 0u
#define SAR_READY_MASK 0x1u
#define SAR_READY_WRITABLE 0
#define SAR_READY_HELD 0
#define SAR_READY_RESET 0x0u
/* done: 1 bit, ro */
#define SAR_DONE_ADDR 0x05u
#define SAR_DONE_REGISTERS 1u
#define SAR_DONE_WIDTH 1u
#define SAR_DONE_SHIFT 1u
#define SAR_DONE_MASK 0x1u
#define SAR_DONE_WRITABLE 0
#define SAR_DONE_HELD 0
#define SAR_DONE_RESET 0x0u
/* metastable: 1 bit, ro */
#define SAR_METASTABLE_ADDR 0x05u
#define SAR_METASTABLE_REGISTERS 1u
#define SAR_METASTABLE_WIDTH 1u
#define SAR_METASTABLE_SHIFT 2u
#define SAR_METASTABLE_MASK 0x1u
#define SAR_METASTABLE_WRITABLE 0
#define SAR_METASTABLE_HELD 0
#define SAR_METASTABLE_RESET 0x0u
/* cmp_out: 1 bit, ro */
#define SAR_CMP_OUT_ADDR 0x05u
#define SAR_CMP_OUT_REGISTERS 1u
#define SAR_CMP_OUT_WIDTH 1u
#define SAR_CMP_OUT_SHIFT 3u
#define SAR_CMP_OUT_MASK 0x1u
#define SAR_CMP_OUT_WRITABLE 0
#define SAR_CMP_OUT_HELD 0
#define SAR_CMP_OUT_RESET 0x0u

/* search @ 0x06 */
#define SAR_ADDR_SEARCH 0x06u
/* bit_index: 4 bit, ro */
#define SAR_BIT_INDEX_ADDR 0x06u
#define SAR_BIT_INDEX_REGISTERS 1u
#define SAR_BIT_INDEX_WIDTH 4u
#define SAR_BIT_INDEX_SHIFT 0u
#define SAR_BIT_INDEX_MASK 0xfu
#define SAR_BIT_INDEX_WRITABLE 0
#define SAR_BIT_INDEX_HELD 0
#define SAR_BIT_INDEX_RESET 0x0u

#endif /* SAR_REGS_H */
