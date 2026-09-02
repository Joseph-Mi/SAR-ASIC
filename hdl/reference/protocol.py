"""One conversion as the pins see it, cycle by cycle.

`sar_convert` says what the answers are. This says when they happen, which is
what cocotb needs: a testbench compares waveforms, not return values.

The sequence is 1 sample cycle + N bit trials + 1 done cycle = N + 2, which is
the termination bound the FSM is held to. Fixing that shape here rather than in
the testbench means the model, not the test, owns the contract -- a test that
defines its own expectation cannot catch the RTL disagreeing with the model.

No comparator logic lives here. The decisions come from `sar_convert` and the
trial codes are reconstructed from its trace, so there is exactly one place a
bit decision is ever made.
"""

from __future__ import annotations

from dataclasses import dataclass

from sar import n_bits_of, sar_convert

SAMPLE = "sample"
TRIAL = "trial"
DONE = "done"


@dataclass(frozen=True)
class Step:
    """The pin state for one clock cycle, plus what the comparator answered.

    `dac_b` is the bottom-plate select word driven at the array: bit k high
    puts branch k on VREF. `decision` and `bit_index` are None outside a trial.
    """

    phase: str
    sample: int
    dac_b: int
    cmp_clk: int
    decision: int | None = None
    bit_index: int | None = None


def conversion_sequence(vin, unit_caps, vref: float = 1.0, **comparator) -> list[Step]:
    """Expand one conversion into the cycles that produce it.

    Extra keyword arguments are passed to `sar_convert`, so comparator offset
    and noise perturb the sequence exactly as they perturb the conversion.
    """
    n_bits = n_bits_of(unit_caps)
    code, trace = sar_convert(vin, unit_caps, vref, **comparator)

    steps = [Step(phase=SAMPLE, sample=1, dac_b=0, cmp_clk=0)]
    settled = 0
    for i, decision in enumerate(trace):
        bit_index = n_bits - 1 - i
        trial = settled | (1 << bit_index)
        steps.append(
            Step(
                phase=TRIAL,
                sample=0,
                dac_b=trial,
                cmp_clk=1,
                decision=decision,
                bit_index=bit_index,
            )
        )
        if decision:
            settled = trial
    steps.append(Step(phase=DONE, sample=0, dac_b=code, cmp_clk=0))
    return steps


def trace_of(steps: list[Step]) -> list[int]:
    """The bit decisions, MSB first, as `sar_convert` would return them."""
    return [s.decision for s in steps if s.phase == TRIAL]


def code_of(steps: list[Step]) -> int:
    """The result the FSM presents once it is done."""
    return steps[-1].dac_b
