"""The analog job's policy: a skip is a failure, an expected failure is not.

`conftest.py` turns a skipped test into a failure when `SAR_REQUIRE_TOOLS` is
set, because in the environment that has every tool a skip reads as a pass
that tested nothing. The carve-out is what needs a test: pytest reports an
`xfail` as skipped too, so the policy as first written failed every triaged
known failure, and it did it without naming the reason -- the job went red
pointing at the test rather than at the policy.

Run as a subprocess against a copy of the real `conftest.py`, so what is
checked is the file the suites load and not a reimplementation of it. Needs
nothing but pytest, which the digital job has.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: One module holding the two outcomes the policy has to separate.
CASES = """
import pytest

def test_a_skip_is_a_tool_that_is_missing():
    pytest.skip("no simulator here")

@pytest.mark.xfail(strict=True, reason="documented, triaged, watched")
def test_an_expected_failure_is_a_known_defect():
    assert False
"""


def run(workdir: Path, require: bool) -> str:
    """The suite's own conftest, over the two cases, with the policy on or off."""
    env = {"PATH": "/usr/bin:/bin", "HOME": str(workdir)}
    if require:
        env["SAR_REQUIRE_TOOLS"] = "1"
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-rA", "cases.py"],
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
    )
    return done.stdout


@pytest.fixture
def suite(tmp_path: Path) -> Path:
    shutil.copy(ROOT / "conftest.py", tmp_path / "conftest.py")
    (tmp_path / "cases.py").write_text(CASES)
    return tmp_path


def test_a_skip_becomes_a_failure_where_every_tool_is_required(suite):
    out = run(suite, require=True)
    assert "1 failed" in out, out
    assert "skipped where every tool is required" in out, out


def test_an_expected_failure_survives_the_policy(suite):
    """The carve-out. An xfail is reported as skipped and must not be caught:
    it ran, it failed the way it says it fails, and `strict` is already
    watching for it to start passing."""
    out = run(suite, require=True)
    assert "1 xfailed" in out, out


def test_without_the_variable_a_skip_is_just_a_skip(suite):
    """Off the analog job the policy does nothing, which is what makes a
    machine without a simulator able to run the suite at all."""
    out = run(suite, require=False)
    assert "1 skipped" in out, out
    assert "1 xfailed" in out, out
    assert "1 failed" not in out, out
