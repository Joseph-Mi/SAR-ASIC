"""Test-session policy shared by every suite in the repository.

Contract: with `SAR_REQUIRE_TOOLS` set, a test that skips fails instead. The
analog and closed-loop tests skip when a simulator or the PDK is missing,
which is right on a machine that lacks them and wrong in the environment that
is supposed to have everything: there a skip reads as a pass that tested
nothing.
"""

from __future__ import annotations

import os

import pytest

REQUIRE_TOOLS = "SAR_REQUIRE_TOOLS"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if os.environ.get(REQUIRE_TOOLS) and report.skipped:
        reason = report.longrepr[-1] if isinstance(report.longrepr, tuple) else report.longrepr
        report.outcome = "failed"
        report.longrepr = f"skipped where every tool is required ({REQUIRE_TOOLS}): {reason}"
