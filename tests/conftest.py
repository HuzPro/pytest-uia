"""Fixtures for the specs that drive real applications on the real desktop.

The `gui` fixture a user gets comes from the installed plugin
(:mod:`pytest_uia.hooks`) and is deliberately not redefined here. What this
adds is one launched fixture app, built on the same session the plugin hands
out, so the specs below exercise the shipped wiring rather than a copy of it.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from pytest_uia.application.driver import App

FIXTURE_APPS = Path(__file__).parent / "fixture_apps"

# WinForms JITs most of System.Windows.Forms before it paints anything the
# accessibility tree can see. A five-second wait failed here on a cold run;
# thirty has always been enough.
_READY_TIMEOUT_SECONDS = 30.0


def winforms_command() -> list[str]:
    """How the rich-accessibility-tree fixture app is started.

    -Sta is not optional (WinForms refuses any other apartment) and the hidden
    window style keeps the console host from being a second window owned by
    the same pid.
    """
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


@pytest.fixture
def winforms_app() -> Iterator[App]:
    # Imported inside the fixture, not at module scope: conftest is imported on
    # every platform, including the lane where uiautomation is not installed.
    from pytest_uia.application.session import session_on_this_desktop

    session = session_on_this_desktop()
    try:
        yield session.launch(winforms_command(), ready_timeout=_READY_TIMEOUT_SECONDS)
    finally:
        session.shutdown_all()
