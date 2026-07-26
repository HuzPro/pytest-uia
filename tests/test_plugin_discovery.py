"""Spec for the one thing a plugin has to do before anything else works.

Runs pytest as a subprocess in an empty directory, so what it observes is the
installed distribution's own entry point rather than this repo's conftest.
Requires the package to be installed in the current environment
(``uv pip install -e ".[dev]"``).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Enough for two full pytest startups on a cold import cache.
_STARTUP_BUDGET_SECONDS = 120


def _run_pytest_in(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_STARTUP_BUDGET_SECONDS,
        check=False,
    )


def test_an_installed_pytest_sees_the_uia_plugin_and_its_gui_fixture(
    tmp_path: Path,
) -> None:
    # Given a project that has never heard of this repo
    # When pytest starts there and is asked what it loaded and what it offers
    loaded = _run_pytest_in(tmp_path, "--trace-config", "--collect-only")
    offered = _run_pytest_in(tmp_path, "--fixtures")

    # Then the plugin loaded itself through its entry point
    assert "pytest_uia.plugin" in loaded.stdout, (
        "pytest did not load the plugin; the pytest11 entry point is missing or "
        f"the package is not installed:\n{loaded.stdout}{loaded.stderr}"
    )
    # and the fixture a user writes their first test against is available
    assert re.search(r"^gui\b", offered.stdout, re.MULTILINE), (
        f"the gui fixture is not offered to plugin users:\n{offered.stdout}"
    )
