"""The whole digital half, driven only through its pins.

Nothing internal is reached here. A test wires the board -- the jumpers, the
button, the configuration bus -- and reads the result pins, which is all a user
of the part has. The analog half is stood in for behaviourally: an ideal array
and a comparator that answers about the top plate the golden model says the
array puts there, so a code arriving on the pins is the model's code or a
defect.

Expectations come from the model, never from this file, and the pin map says
where every signal is: a bit index written here would be a second pin
assignment, and the one that drifts is always the copy.

Pins are read on the falling edge. Registered outputs settle on the rising one,
so reading there races the update being checked.
"""

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

from interface import N_BITS
from pins import (
    DIRECTIONS,
    DONE,
    HOLD,
    IN,
    SINGLE_SHOT,
    SPI_CS_N,
    SPI_MISO,
    SPI_MOSI,
    SPI_SCK,
    START,
    assignments,
    code_pins,
    uio_oe,
)
from protocol import conversion_sequence
from registers import (
    ADDRESS,
    BY_NAME,
    IDENTITY,
    IDENTITY_VALUE,
    REGISTER_WIDTH,
    VIEW_COMPARATOR,
    VIEW_SEARCH,
    VIEWS,
    bits_for,
)
from sar import VCM_FRACTION, ideal_units, sar_convert, top_plate_voltage
from spi import command
from tb_common import rtl, run
from tick import RESET_DIVISOR, period
from view import PROBE_SHIFT, SEARCH_WIDTH

DUT = "sar_top"

MODULES = (
    DUT,
    "sar_spi",
    "sar_regfile",
    "sar_tick",
    "sar_start",
    "sar_fsm",
    "sar_readout",
    "sync2",
)

CLK_PERIOD_NS = 10
RESET_CYCLES = 2
VREF = 1.0

FULL = (1 << REGISTER_WIDTH) - 1

#: The rate the tests run at unless they are about the rate. One step per
#: cycle, so a conversion is as short as it can be.
FAST = 0

#: A slower rate, to show the conversion stretches by exactly its period.
SLOW = 3

#: System clocks per phase of the configuration clock. The slave samples the
#: wire, so a phase has to last long enough to be seen.
SCK_PHASE_CYCLES = 4

#: Cycles to leave a pin alone for after moving it: two for the synchroniser,
#: and some either side.
PRESS_CYCLES = 4

#: Cycles for a held write to reach the analog half once its frame has closed.
#: The slave's select line is synchronised too, so the frame is not shut the
#: instant the wire says so.
SETTLE_CYCLES = 8

#: Steps the search stands idle between two conversions. The model's sequence
#: already ends with the step that announces a result; this is the one after it,
#: and it is the step a request to start is read on.
IDLE_STEPS = 1

UNITS = ideal_units(N_BITS)

#: Inputs covering both rails and the middle. Mid-scale is the tie the model
#: resolves upward, and resolving it the other way puts every code one low.
PROBE_INPUTS = (0.0, 0.5, 0.999, 0.123, 0.876)

#: An input whose code has bits at both ends of the word, so a result pin wired
#: to the wrong place shows.
MID = 0.5

#: Near the top of the range, where the most significant bits are all set.
TOP = 0.999

#: A raw word with bits in both registers the field spans, and nowhere near
#: all-zeros, which is the one word the array may never be left at.
RAW_WORD = 0b11_0000_0001

#: Which group of pins each direction of the platform's bus is on.
DRIVEN = {"ui_in": "ui_in", "uio": "uio_in"}
WATCHED = {"uo_out": "uo_out", "uio": "uio_out"}

#: Where the map puts every signal.
POSITION = {signal: place for place, signal in assignments().items()}


def steps_per_conversion() -> int:
    """Steps of the conversion clock one conversion takes, from the model."""
    return len(conversion_sequence(MID * VREF, UNITS, VREF)) + IDLE_STEPS


def conversion_cycles(divisor: int) -> int:
    """System clocks one conversion takes at this rate."""
    return steps_per_conversion() * period(divisor)


def pin(dut, signal: str) -> int:
    """One pin the design drives."""
    group, bit = POSITION[signal]
    return int(getattr(dut, WATCHED[group]).value) >> bit & 1


def result(dut) -> int:
    """The result word, read off whichever pin the map puts each bit on."""
    return sum(
        (int(getattr(dut, WATCHED[group]).value) >> bit & 1) << k
        for k, (group, bit) in enumerate(code_pins())
    )


class Board:
    """What is wired to the pins, so a test can move one line and leave the
    rest of them where they were."""

    def __init__(self, dut):
        self.dut = dut
        #: A pin nothing drives reads low, which is what the platform gives.
        self.levels = {SPI_CS_N: True}
        self.apply()

    def set(self, signal: str, level) -> None:
        self.levels[signal] = bool(level)
        self.apply()

    def apply(self) -> None:
        words = dict.fromkeys(DRIVEN, 0)
        for (group, bit), signal in assignments().items():
            if group in words and DIRECTIONS[signal] == IN and self.levels.get(signal):
                words[group] |= 1 << bit
        for group, port in DRIVEN.items():
            getattr(self.dut, port).value = words[group]


class Analog:
    """The analog half, behaviourally: an ideal array and an ideal comparator.

    The comparator answers whether the top plate came out at or below the
    common mode, which is the rule the golden converter decides by written in
    the physical form -- so this stands in for the half that is not built yet
    without becoming a second opinion about what a code should be.
    """

    def __init__(self, dut):
        self.dut = dut
        self.vin = MID * VREF

    @property
    def sampled(self) -> float:
        """What the array sees: the input pin, unless the part is forcing it."""
        if int(self.dut.force_en_o.value):
            return VREF if int(self.dut.force_hi_o.value) else 0.0
        return self.vin

    def code(self) -> int:
        """What the model converts what the array sees to."""
        return sar_convert(self.sampled, UNITS, VREF)[0]

    async def run(self) -> None:
        while True:
            await RisingEdge(self.dut.cmp_clk_o)
            top = top_plate_voltage(self.sampled, int(self.dut.dac_b_o.value), UNITS, VREF)
            answer = int(top <= VCM_FRACTION * VREF)
            self.dut.cmp_out_i.value = answer
            self.dut.cmp_out_n_i.value = 1 - answer


async def sck(dut, board: Board, level) -> None:
    board.set(SPI_SCK, level)
    await ClockCycles(dut.clk, SCK_PHASE_CYCLES)


async def transfer(dut, board: Board, byte: int) -> int:
    """One byte out and one byte in. The slave moves its line on the falling
    edge, so the master reads it at the end of the low phase."""
    got = 0
    for i in range(REGISTER_WIDTH - 1, -1, -1):
        board.set(SPI_MOSI, byte >> i & 1)
        await sck(dut, board, False)
        got = (got << 1) | pin(dut, SPI_MISO)
        await sck(dut, board, True)
    board.set(SPI_SCK, False)
    return got


async def frame(dut, board: Board, data) -> list[int]:
    board.set(SPI_CS_N, False)
    await ClockCycles(dut.clk, SCK_PHASE_CYCLES)
    out = [await transfer(dut, board, byte) for byte in data]
    board.set(SPI_CS_N, True)
    await ClockCycles(dut.clk, SCK_PHASE_CYCLES)
    return out


async def write_register(dut, board: Board, address: int, *values: int) -> None:
    await frame(dut, board, [command(address, write=True), *values])


async def read_register(dut, board: Board, address: int) -> int:
    return (await frame(dut, board, [command(address, write=False), 0]))[1]


async def control(dut, board: Board, **fields: int) -> None:
    """The control register, by field name, with everything else cleared."""
    word = 0
    for name, value in fields.items():
        word |= (value & BY_NAME[name].mask) << BY_NAME[name].offset
    await write_register(dut, board, ADDRESS["control"], word)
    await ClockCycles(dut.clk, SETTLE_CYCLES)


async def converted(dut, divisor: int) -> int:
    """Wait for the flag, and read the pins on the cycle it is up.

    The holding register takes the result and raises the flag on one edge, so
    the pins already belong to the conversion the flag is announcing."""
    for _ in range(2 * conversion_cycles(divisor) + SETTLE_CYCLES):
        await FallingEdge(dut.clk)
        if pin(dut, DONE):
            return result(dut)
    raise AssertionError(f"no conversion finished inside two at divisor {divisor}")


async def between_flags(dut, divisor: int) -> int:
    """Cycles from one conversion being announced to the next."""
    await converted(dut, divisor)
    for count in range(1, 2 * conversion_cycles(divisor) + SETTLE_CYCLES):
        await FallingEdge(dut.clk)
        if pin(dut, DONE):
            return count
    raise AssertionError("the second conversion never arrived")


async def power_up(dut) -> Analog:
    """The clock running, reset released, and the analog half answering."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    dut.cmp_out_i.value = 0
    dut.cmp_out_n_i.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, RESET_CYCLES)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    analog = Analog(dut)
    cocotb.start_soon(analog.run())
    await ClockCycles(dut.clk, RESET_CYCLES)
    return analog


async def start(dut, *, divisor: int = FAST, continuous: bool = False):
    """A configured part: single-shot while the rate is set, because a held
    write reaches the analog half only once no conversion is running."""
    board = Board(dut)
    board.set(SINGLE_SHOT, True)
    analog = await power_up(dut)
    if divisor != RESET_DIVISOR:
        await write_register(dut, board, ADDRESS["clk_div"], divisor)
        # A new rate takes effect from the next interval and never shortens the
        # one in flight, and reset leaves the counter part way through the
        # slowest interval there is -- so that is the wait, not a handful of
        # cycles.
        await ClockCycles(dut.clk, period(RESET_DIVISOR) + SETTLE_CYCLES)
    if continuous:
        board.set(SINGLE_SHOT, False)
        await ClockCycles(dut.clk, PRESS_CYCLES)
    return board, analog


async def press(dut, board: Board) -> None:
    """A button pressed and released."""
    board.set(START, True)
    await ClockCycles(dut.clk, PRESS_CYCLES)
    board.set(START, False)
    await ClockCycles(dut.clk, PRESS_CYCLES)


@cocotb.test()
async def it_converts_with_nothing_wired_to_it(dut):
    """Every input the platform leaves unconnected reads low, so this is the
    part as it arrives: converting continuously, at the slowest rate it has,
    showing every result. One that waited to be configured would read as dead
    on a bench, and the rate is the slow one because a converter too fast
    returns codes that are wrong and plausible."""
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    analog = await power_up(dut)
    assert await converted(dut, RESET_DIVISOR) == analog.code()


@cocotb.test()
async def the_identity_reads_back_over_the_pins(dut):
    """One read, over the bus, through the pin map: it says the part is
    answering and that it means the same register map the host was built
    against."""
    board, _ = await start(dut)
    assert await read_register(dut, board, ADDRESS[IDENTITY]) == IDENTITY_VALUE


@cocotb.test()
async def the_bidirectional_pins_are_enabled_only_where_the_design_drives(dut):
    """A pin the design does not drive but enables fights whatever the board
    has on the other side of it."""
    await start(dut)
    assert int(dut.uio_oe.value) == uio_oe()


@cocotb.test()
async def every_code_matches_the_model(dut):
    """The conversion, end to end: the array, the comparator, the search, the
    holding register and the pin map all have to be right for this to pass."""
    board, analog = await start(dut, continuous=True)
    for fraction in PROBE_INPUTS:
        analog.vin = fraction * VREF
        # The conversion in flight straddles the change, so it is discarded.
        await converted(dut, FAST)
        assert await converted(dut, FAST) == analog.code(), f"vin = {fraction} of full scale"


@cocotb.test()
async def the_most_significant_bits_sit_on_the_dedicated_outputs(dut):
    """Those pins alone have to read as a number across the whole input range.
    The low bits alone wrap, once per pin the result outgrows."""
    board, analog = await start(dut, continuous=True)
    analog.vin = TOP * VREF
    await converted(dut, FAST)
    got = await converted(dut, FAST)
    assert got == analog.code()
    assert int(dut.uo_out.value) == got >> PROBE_SHIFT


@cocotb.test()
async def holding_the_result_does_not_hold_the_converter(dut):
    """An asynchronous pin that gated the search is how a half-finished code
    gets latched, so the pin freezes the register and nothing else."""
    board, analog = await start(dut, continuous=True)
    analog.vin = MID * VREF
    await converted(dut, FAST)
    held = await converted(dut, FAST)

    board.set(HOLD, True)
    await ClockCycles(dut.clk, PRESS_CYCLES)
    analog.vin = TOP * VREF
    for _ in range(3 * conversion_cycles(FAST)):
        await FallingEdge(dut.clk)
        assert not pin(dut, DONE), "the flag went up while the pins were held"
        assert result(dut) == held, "the pins moved while they were held"

    # Released, a result arrives inside a conversion -- which it can only do if
    # the search never stopped.
    board.set(HOLD, False)
    assert await converted(dut, FAST) == analog.code()


@cocotb.test()
async def one_press_converts_once(dut):
    """The mode exists so a reading can be taken at a moment of someone's
    choosing, which means not before they ask and not twice when they do."""
    board, analog = await start(dut)
    for _ in range(2 * conversion_cycles(FAST)):
        await FallingEdge(dut.clk)
        assert not pin(dut, DONE), "it converted without being asked"

    await press(dut, board)
    assert await converted(dut, FAST) == analog.code()

    for _ in range(3 * conversion_cycles(FAST)):
        await FallingEdge(dut.clk)
        assert not pin(dut, DONE), "one press converted more than once"


@cocotb.test()
async def the_rate_the_register_asks_for_is_the_rate_it_converts_at(dut):
    """A conversion is a fixed number of steps, so its length is the period and
    nothing else -- which is what lets a board trade speed for settling time."""
    board, _ = await start(dut, continuous=True)
    fast = await between_flags(dut, FAST)
    assert fast == steps_per_conversion() * period(FAST), "the conversion is not the model's"

    await write_register(dut, board, ADDRESS["clk_div"], SLOW)
    await ClockCycles(dut.clk, conversion_cycles(FAST) + SETTLE_CYCLES)
    slow = await between_flags(dut, SLOW)
    assert slow == steps_per_conversion() * period(SLOW)
    # The same conversion, stretched: the rate buys settling time per step and
    # changes nothing about how many steps there are.
    assert slow * period(FAST) == fast * period(SLOW)


@cocotb.test()
async def the_comparator_view_streams_the_latch_to_the_pins(dut):
    """Both outputs, so the one thing worth watching live -- the two coming out
    equal, which is the latch failing to resolve -- is visible as it happens."""
    board, _ = await start(dut, continuous=True)
    await write_register(dut, board, ADDRESS["view"], VIEW_COMPARATOR)
    await ClockCycles(dut.clk, SETTLE_CYCLES)

    seen = set()
    for _ in range(2 * conversion_cycles(FAST)):
        await FallingEdge(dut.clk)
        word = int(dut.uo_out.value)
        want = (int(dut.cmp_out_i.value), int(dut.cmp_out_n_i.value))
        assert (word & 1, word >> 1 & 1) == want, "the pins do not carry the latch"
        seen.add(want)
    assert len(seen) > 1, "the stream never moved, so nothing was being watched"


@cocotb.test()
async def the_search_view_streams_the_bit_index_to_the_pins(dut):
    """Which bit is being trialled, so a search that stalls says where."""
    board, _ = await start(dut, continuous=True)
    await write_register(dut, board, ADDRESS["view"], VIEW_SEARCH)
    await ClockCycles(dut.clk, SETTLE_CYCLES)

    seen = set()
    for _ in range(2 * conversion_cycles(FAST)):
        await FallingEdge(dut.clk)
        word = int(dut.uo_out.value)
        assert word >> SEARCH_WIDTH == 0, "the stream is wider than the index"
        seen.add(word)
    assert seen == set(range(N_BITS)), f"the search reached {sorted(seen)}"


@cocotb.test()
async def raw_dac_mode_drives_the_array_from_the_register(dut):
    """The array is characterised by holding it at a chosen word and letting the
    comparator say which side of the common mode the top plate came out. So the
    word has to reach the array and stay there, and the search has to keep
    sampling and strobing around it.

    The word is written before the mode is turned on. The other order would put
    the array at the register's reset value for a moment, and all-zeros under a
    held sample is the one thing it may never be."""
    board, _ = await start(dut)
    await write_register(dut, board, ADDRESS["dac"], RAW_WORD & FULL, RAW_WORD >> REGISTER_WIDTH)
    await ClockCycles(dut.clk, SETTLE_CYCLES)
    await control(dut, board, raw_dac=1)
    assert int(dut.dac_b_o.value) == RAW_WORD

    board.set(START, True)
    sampled = strobed = 0
    for _ in range(2 * conversion_cycles(FAST)):
        await FallingEdge(dut.clk)
        assert int(dut.dac_b_o.value) == RAW_WORD, "the search moved the array in raw mode"
        sampled += int(dut.sample_o.value)
        strobed += int(dut.cmp_clk_o.value)
    assert sampled, "the array was never sampled, so its charge is undefined"
    assert strobed, "the comparator was never strobed, so nothing can be read"


@cocotb.test()
async def forcing_the_input_reaches_the_analog_half(dut):
    """Shorting the input to a rail on chip is how the converter is measured
    with nothing wired to the input pin at all."""
    board, analog = await start(dut)
    analog.vin = MID * VREF
    for hi in (0, 1):
        await control(dut, board, force_en=1, force_hi=hi)
        assert int(dut.force_en_o.value) == 1
        assert int(dut.force_hi_o.value) == hi
        await press(dut, board)
        assert await converted(dut, FAST) == analog.code(), f"forced {'high' if hi else 'low'}"


def test_sar_top():
    run(
        DUT,
        sources=rtl(*MODULES),
        parameters={
            "N_BITS": N_BITS,
            "REGISTER_WIDTH": REGISTER_WIDTH,
            "VIEW_WIDTH": bits_for(len(VIEWS)),
            "VIEW_COMPARATOR": VIEW_COMPARATOR,
            "VIEW_SEARCH": VIEW_SEARCH,
        },
        test_dir=Path(__file__).parent,
    )
