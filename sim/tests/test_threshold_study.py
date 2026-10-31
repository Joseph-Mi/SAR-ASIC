"""The instrument that locates thresholds, held to its own guards.

`locate` bisects the real controller running the real block, so every claim
it makes costs minutes of ngspice. These run against a stub converter
instead: the quantity under test is the search, not the circuit, and a search
can be handed a circuit whose answer is known. That is what lets the guards
be mutation-checked at all -- each one is given exactly the pathology it
exists to catch.

The last test is the one that matters. `locate` read one conversion per code
per round until a stub like `order_dependent` was written down: a converter
whose answer depends on the input before it, which is what the real loop is
(Step 4b's kick, measured at the loop level). Reading a single conversion
reports the kick layered on the threshold, and against the real block it put
one code 0.69 LSB from its neighbours where the settled answer is 0.38.
"""

from __future__ import annotations

import pytest

import loop
from bench import Block
from interface import N_BITS
from sweep import VREF, lsb
from threshold_study import RESOLUTION, SETTLE, WINDOW, locate

STEP = lsb(N_BITS, VREF)


def stub(answer):
    """A `loop.convert` that reports `answer(vin_in_lsb, previous_in_lsb)`."""

    def convert(inputs, library, workdir, block=None, clock=None):
        lsbs = [v / STEP for v in inputs]
        codes = [answer(v, p) for v, p in zip(lsbs, [None] + lsbs[:-1], strict=True)]
        return loop.Result(codes=codes, flags=[False] * len(codes), lows=[0.0] * len(codes))

    return convert


def planted(threshold_of):
    """A converter with no memory: code k above `threshold_of(k)`."""

    def answer(vin, _previous):
        return sum(1 for k in range(1, 1 << N_BITS) if vin >= threshold_of(k))

    return answer


def run(monkeypatch, answer, codes, centre=0.0):
    monkeypatch.setattr(loop, "convert", stub(answer))
    return locate(None, Block(), None, 1e-7, codes=codes, centre=centre)


def test_it_finds_a_planted_threshold(monkeypatch):
    # Offset every threshold by a quarter of an LSB and ask for it back.
    offset = 0.25
    found = run(monkeypatch, planted(lambda k: k + offset), (64, 512, 896))
    for k, v in found.items():
        assert abs(v - (k + offset)) <= RESOLUTION, f"code {k} located at {v}"


def test_it_refuses_an_answer_outside_its_window(monkeypatch):
    # Further off than the window reaches: the search can only walk to its
    # own edge, and the edge is not a measurement.
    with pytest.raises(ValueError, match="reached its own window"):
        run(monkeypatch, planted(lambda k: k + 2 * WINDOW), (512,))


def test_centring_the_window_reaches_what_the_window_alone_cannot(monkeypatch):
    # The same converter the previous test refuses, found once the search is
    # told roughly where to look. This is how a block whose offset exceeds
    # the window is measured at all.
    offset = 2 * WINDOW
    found = run(monkeypatch, planted(lambda k: k + offset), (512,), centre=offset)
    assert abs(found[512] - (512 + offset)) <= RESOLUTION


def test_it_refuses_a_batch_longer_than_one_run(monkeypatch):
    # `loop.convert` runs each batch from reset, so a round that does not fit
    # one batch puts a reset in the middle of itself.
    with pytest.raises(ValueError, match="against a batch of"):
        run(monkeypatch, planted(lambda k: k), tuple(range(1, 100)))


@pytest.mark.parametrize("settle", [1, 2])
def test_it_refuses_too_few_conversions_to_check_the_settling(monkeypatch, settle):
    # Two is not enough and the reason is not obvious: the first reading of
    # an input sits behind the *previous* code's input, so only the last two
    # share a predecessor and only their disagreement means anything.
    monkeypatch.setattr("threshold_study.SETTLE", settle)
    with pytest.raises(ValueError, match="settle check needs three"):
        run(monkeypatch, planted(lambda k: k), (512,))


def test_a_reading_that_straddles_its_own_code_is_the_transition(monkeypatch):
    """Readings of `k-1` and `k` from one input end that code's search.

    The real block flips within about two thousandths of an LSB of a
    transition and repeats everywhere else, which is finer than `RESOLUTION`,
    so a bisection that lands there cannot be rescued by another round. What
    it has found is the transition. The stub plants one at a known place and
    makes the input within a thousandth of it ambiguous, the way the circuit
    is.
    """
    # Wider than the bisection's final bracket (2 * WINDOW / 2**rounds), or
    # no midpoint ever lands in it and the test asserts nothing.
    threshold, blur = 512.4, 0.01
    seen = {"n": 0}

    def answer(vin, _previous):
        if abs(vin - threshold) < blur:
            seen["n"] += 1
            return 512 if seen["n"] % 2 else 511
        return 512 if vin >= threshold else 511

    found = run(monkeypatch, answer, (512,))
    assert seen["n"], "the stub was never asked an ambiguous input"
    assert abs(found[512] - threshold) <= RESOLUTION, f"located at {found[512]}"


def test_a_reading_that_straddles_something_else_still_raises(monkeypatch):
    # Two readings that disagree and are not this code's own pair are a
    # failure to settle, not a transition, and must not be read as one.
    flip = {"n": 0}

    def answer(vin, _previous):
        flip["n"] += 1
        return 500 if flip["n"] % 2 else 400

    with pytest.raises(ValueError, match="not settled"):
        run(monkeypatch, answer, (512,))


def test_it_reports_the_settled_threshold_and_not_the_previous_input(monkeypatch):
    """The fix, mutation-checked: `SETTLE` must be what defeats the memory.

    `order_dependent` is the real loop's defect in miniature -- a threshold
    0.25 LSB off, which drifts a further 0.5 LSB when the conversion before
    it came from far away, exactly the direction the measured block drifts.
    Reading the last of `SETTLE` conversions of the same input makes every
    reading its own predecessor, so the memory term is zero and the settled
    0.25 is what comes back. At `SETTLE = 1` the kick is what comes back
    instead, which is the bug this test exists to keep fixed.
    """
    settled, kicked = 0.25, 0.75

    def order_dependent(vin, previous):
        far = previous is not None and abs(vin - previous) > 1.0
        shift = kicked if far else settled
        return sum(1 for k in range(1, 1 << N_BITS) if vin >= k + shift)

    assert SETTLE >= 3, "the last two readings are the settle check"
    found = run(monkeypatch, order_dependent, (64, 512, 896))
    for k, v in found.items():
        assert abs(v - (k + settled)) <= RESOLUTION, (
            f"code {k} located at {v - k:+.4f} LSB, not the settled {settled}: "
            "the search is reporting the input before it"
        )
