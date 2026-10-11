"""Run the formal proofs as part of the suite.

Contract: a proof that is only ever run by hand is a proof of whatever the RTL
looked like the last time somebody ran it. These entry points put the solver
in the same place every other check is, so a property that stops holding fails
a run rather than waiting to be noticed.

Skips where SymbiYosys is absent, which is how every other tool-dependent
suite here behaves; with SAR_REQUIRE_TOOLS set a skip is a failure.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
from dataclasses import dataclass

import pytest

from interface import N_BITS
from protocol import conversion_sequence
from sar import ideal_units

HERE = pathlib.Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
BUILD = REPO / "build" / "formal"

SBY = "sby"
CONFIG = "sar_fsm.sby"

#: Every task the configuration declares. Named here so a task added to the
#: configuration and not to the suite shows up as a missing test rather than
#: as a proof nobody runs.
TASKS = ("stepping", "stalling")

#: Seconds a proof may take. Generous: the point of the bound is to fail a
#: wedged solver rather than to hold the proofs to a time.
TIMEOUT = 900

#: The step bound the properties count against, as the harness declares it.
#: The model owns the shape of a conversion, so this is a copy, and the test
#: below is what keeps the two from drifting.
SBY_STEPS = re.compile(r"localparam\s+integer\s+CONVERSION_STEPS\s*=\s*([^;]+);")

#: The line in the configuration that reaches out of this directory for the
#: design, so a mutant copy can be put in its place.
SBY_RTL = re.compile(r"^.*/(sar_fsm\.v)$", re.M)

PROPS = "sar_fsm_props.sv"
RTL = "sar_fsm.v"

#: The shape of a conversion, which is what the bound counts. A bit trial
#: settles the array and then evaluates; a conversion adds the sample at the
#: front and the handover at the end.
STEPS_PER_TRIAL = 2
STEPS_AROUND = 2

#: How the harness has to spell the bound, since a solver cannot import the
#: model and the number therefore exists twice.
BOUND_EXPRESSION = f"{STEPS_PER_TRIAL} * N_BITS + {STEPS_AROUND}"


@dataclass(frozen=True)
class Mutation:
    """A defect to introduce, and the contract it breaks.

    A proof that passes is only as good as its ability to fail. Each of these
    is a defect the properties are supposed to catch, so the day one of them
    stops being caught is the day a property quietly stopped saying anything.
    """

    name: str
    find: str
    replace: str
    contract: str


MUTATIONS = (
    Mutation(
        name="all_ground_after_sampling",
        find="dac_b_o <= settled | ({{(N_BITS - 1) {1'b0}}, 1'b1} << bit_index);",
        replace="dac_b_o <= {N_BITS{1'b0}};",
        contract="the array is never at all-ground while a sample is held",
    ),
    Mutation(
        name="strobe_held_across_trials",
        find="cmp_clk_o <= (next_state == ST_EVAL);",
        replace="cmp_clk_o <= (next_state == ST_EVAL) || (state == ST_EVAL);",
        contract="the comparator precharges between trials",
    ),
    Mutation(
        name="search_never_finishes",
        find="ST_EVAL:   next_state = (bit_index == {IDX_W{1'b0}}) ? ST_DONE : ST_SETTLE;",
        replace="ST_EVAL:   next_state = ST_SETTLE;",
        contract="a conversion finishes within the bound the protocol declares",
    ),
    Mutation(
        name="flag_held_after_the_result",
        find="done_o    <= (next_state == ST_DONE);",
        replace="done_o    <= (next_state == ST_DONE) || (state == ST_DONE);",
        contract="the flag is up for exactly one step",
    ),
)


def run_task(task: str) -> subprocess.CompletedProcess:
    if shutil.which(SBY) is None:
        pytest.skip(f"{SBY} is not on the path")
    out = BUILD / task
    if out.exists():
        shutil.rmtree(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [SBY, "-f", "-d", str(out), CONFIG, task],
        cwd=HERE,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
    )


@pytest.mark.parametrize("task", TASKS)
def test_the_control_fsm_satisfies_its_properties(task):
    done = run_task(task)
    assert done.returncode == 0, done.stdout[-4000:]


def test_the_configuration_declares_no_task_the_suite_does_not_run():
    """A task in the configuration that nothing invokes is a proof that looks
    like it is being run and is not."""
    body = (HERE / CONFIG).read_text()
    block = body.split("[tasks]", 1)[1].split("[", 1)[0]
    declared = tuple(line.strip() for line in block.splitlines() if line.strip())
    assert declared == TASKS


def test_the_bound_the_properties_count_against_is_the_models():
    """The properties assert a conversion finishes in a declared number of
    steps. That number is the model's, restated in the harness because a
    solver cannot import Python -- so it is a copy, and a copy nobody compares
    is what lets a proof go on passing against the wrong bound."""
    found = SBY_STEPS.search((HERE / PROPS).read_text())
    assert found, f"{PROPS} declares no step bound"
    assert " ".join(found.group(1).split()) == BOUND_EXPRESSION
    steps = STEPS_PER_TRIAL * N_BITS + STEPS_AROUND
    assert len(conversion_sequence(0.3, ideal_units(N_BITS))) == steps


def mutant(tmp_path: pathlib.Path, change: Mutation) -> pathlib.Path:
    """A copy of the design with one defect in it, ready to prove against."""
    source = (REPO / "hdl" / "rtl" / RTL).read_text()
    assert change.find in source, f"{change.name}: nothing to replace"
    (tmp_path / RTL).write_text(source.replace(change.find, change.replace))
    shutil.copy(HERE / PROPS, tmp_path / PROPS)
    config = SBY_RTL.sub(RTL, (HERE / CONFIG).read_text())
    (tmp_path / CONFIG).write_text(config)
    return tmp_path


@pytest.mark.parametrize("change", MUTATIONS, ids=lambda c: c.name)
def test_a_design_that_breaks_a_contract_is_caught(change, tmp_path):
    """Every claim the proofs make, attacked. These are the tests that make the
    proofs worth running: a property can be weakened into something vacuous
    without any test noticing, and this is what notices."""
    if shutil.which(SBY) is None:
        pytest.skip(f"{SBY} is not on the path")
    where = mutant(tmp_path, change)
    done = subprocess.run(
        [SBY, "-f", "-d", str(where / "out"), CONFIG, "stepping"],
        cwd=where,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
    )
    assert done.returncode != 0, (
        f"{change.name} was not caught: the proofs no longer establish that {change.contract}"
    )
