"""Fixtures for the specs that drive real applications on the real desktop.

Each app is launched per test and torn down in a finally, because a leaked
window is not merely a slow suite: it is the next test's ambiguous pid.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from pytest_uia.application.app_process import AppProcess
from pytest_uia.domain.waiting import RetryPolicy, poll

FIXTURE_APPS = Path(__file__).parent / "fixture_apps"

# WinForms JITs most of System.Windows.Forms before it paints anything the
# accessibility tree can see. A five-second wait failed here on a cold run;
# thirty has always been enough.
_READY_POLICY = RetryPolicy(timeout=30.0, interval=0.25)


@pytest.fixture
def winforms_app() -> Iterator[AppProcess]:
    app = AppProcess.launch(_winforms_command())
    try:
        _wait_until_its_window_is_on_screen(app)
        yield app
    finally:
        app.terminate()


def _winforms_command() -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-Sta",
        "-WindowStyle",
        "Hidden",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(FIXTURE_APPS / "winforms_app.ps1"),
    ]


def _wait_until_its_window_is_on_screen(app: AppProcess) -> None:
    # Imported inside the fixture, not at module scope: conftest is imported on
    # every platform, including the lane where uiautomation is not installed.
    from pytest_uia.adapters.uia import resolve_main_window
    from pytest_uia.domain.errors import WindowNotFound

    poll(lambda: resolve_main_window(app.pid), _READY_POLICY, retry_on=WindowNotFound)
