"""Test-session policy shared by every suite in the repository.

Contract: with `SAR_REQUIRE_TOOLS` set, a test that skips fails instead. The
analog and closed-loop tests skip when a simulator or the PDK is missing,
which is right on a machine that lacks them and wrong in the environment that
is supposed to have everything: there a skip reads as a pass that tested
nothing.

An expected failure is exempt, and the exemption is the whole subtlety here.
pytest reports an `xfail` as skipped -- the same outcome, distinguished only
by a `wasxfail` attribute on the report -- so a policy written against
`report.skipped` turns every triaged known failure into a red job. The two
are opposites of each other: a skip is a test that did not run and should
have, an xfail is a test that ran, failed in the way it was documented to
fail, and is being watched. Marking one `strict` and watching the suite go
red for a reason it does not name is how this was found.
"""

from __future__ import annotations

import os

import pytest

REQUIRE_TOOLS = "SAR_REQUIRE_TOOLS"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    expected_failure = hasattr(report, "wasxfail")
    if os.environ.get(REQUIRE_TOOLS) and report.skipped and not expected_failure:
        reason = report.longrepr[-1] if isinstance(report.longrepr, tuple) else report.longrepr
        report.outcome = "failed"
        report.longrepr = f"skipped where every tool is required ({REQUIRE_TOOLS}): {reason}"
