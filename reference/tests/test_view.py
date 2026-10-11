"""What the result pins carry in each of the modes that drive them.

What matters about a stream is that an instrument clipped to the dedicated
outputs sees it, so these check where each one lands as well as what it says.
"""

from __future__ import annotations

import pytest

from interface import N_BITS
from pins import GROUP_WIDTH, GROUPS, UO_OUT, code_pins
from registers import VIEW_CODE, VIEW_COMPARATOR, VIEW_SEARCH, VIEWS
from view import COMPARATOR_WIDTH, PROBE_SHIFT, PROBE_WIDTH, SEARCH_WIDTH, shown

#: A code with bits at both ends, so a word shifted or truncated shows.
CODE = (1 << (N_BITS - 1)) | 1

#: Indices covering every bit of the search.
INDICES = tuple(range(N_BITS))

#: What the map calls the group of dedicated outputs, read off the map rather
#: than written down again.
DEDICATED = next(name for name, group in GROUPS.items() if group is UO_OUT)


def probe_pins(word: int) -> list[int]:
    """The bits of `word` that reach a dedicated output, lowest bit first."""
    return [word >> k & 1 for k, (group, _) in enumerate(code_pins()) if group == DEDICATED]


def test_the_default_view_is_the_result():
    """A part nobody has configured has to read as a converter."""
    assert shown(VIEW_CODE, CODE, False, False, 0) == CODE


def test_a_view_it_cannot_be_in_is_refused():
    with pytest.raises(ValueError):
        shown(max(VIEWS) + 1, 0, False, False, 0)


@pytest.mark.parametrize("view", VIEWS)
def test_a_code_too_wide_for_the_pins_is_refused(view):
    with pytest.raises(ValueError):
        shown(view, 1 << N_BITS, False, False, 0)


@pytest.mark.parametrize("view", VIEWS)
def test_an_index_too_wide_for_the_search_is_refused(view):
    with pytest.raises(ValueError):
        shown(view, 0, False, False, 1 << SEARCH_WIDTH)


def test_the_comparator_view_carries_both_latch_outputs():
    """Their being equal is the metastability flag, so a view that showed only
    the decision would hide the one thing a stream is watched for."""
    seen = {
        (out, out_n): shown(VIEW_COMPARATOR, CODE, out, out_n, 0)
        for out in (False, True)
        for out_n in (False, True)
    }
    assert len(set(seen.values())) == len(seen)


def test_the_comparator_view_shows_nothing_of_the_code():
    """It is a stream, not a result: a code bleeding through would read as a
    conversion that happened."""
    for code in (0, CODE, (1 << N_BITS) - 1):
        assert shown(VIEW_COMPARATOR, code, True, False, 0) == shown(
            VIEW_COMPARATOR, 0, True, False, 0
        )


@pytest.mark.parametrize("index", INDICES)
def test_the_search_view_carries_the_index(index):
    assert shown(VIEW_SEARCH, CODE, False, False, index) >> PROBE_SHIFT == index


@pytest.mark.parametrize("view", (VIEW_COMPARATOR, VIEW_SEARCH))
def test_every_stream_reaches_the_dedicated_outputs(view):
    """Those pins cannot contend with anything on the board, which is what
    makes them the ones worth clipping a probe to."""
    word = shown(view, 0, True, True, max(INDICES))
    assert word, "the stream is empty"
    assert any(probe_pins(word)), "nothing of the stream reaches a dedicated output"
    assert word >> PROBE_SHIFT << PROBE_SHIFT == word, "part of the stream missed them"


@pytest.mark.parametrize("width", (COMPARATOR_WIDTH, SEARCH_WIDTH))
def test_every_stream_fits_the_pins_the_dedicated_outputs_give(width):
    """A stream wider than they are would be truncated into something that
    reads as a plausible smaller value."""
    assert width <= PROBE_WIDTH


def test_the_bits_the_dedicated_outputs_cannot_hold_are_the_overflow():
    """The RTL does the same subtraction rather than carrying the answer as a
    parameter, so there is no second value to keep in step."""
    assert PROBE_SHIFT == max(0, N_BITS - GROUP_WIDTH)


def test_the_dedicated_outputs_carry_a_result_bit_each():
    """The RTL drives them as one slice of the word, so a pin the map left
    empty among them would be driven with something that is not a result."""
    assert PROBE_WIDTH == GROUP_WIDTH
