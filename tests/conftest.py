"""Fixtures for the specs that drive real applications on the real desktop.

The `gui` fixture a user gets comes from the installed plugin
(:mod:`pytest_uia.hooks`) and is deliberately not redefined here. What this
adds is the two fixture apps, each launched through the same session the plugin
hands out, so the specs below exercise the shipped wiring rather than a copy of
it. The pair is the point: one window exposes a full accessibility tree and one
exposes nothing usable, and the same journey has to run against both.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from importlib.util import find_spec
from pathlib import Path

import pytest

from pytest_uia.application.driver import App
from pytest_uia.domain.errors import InputRefused

FIXTURE_APPS = Path(__file__).parent / "fixture_apps"

# WinForms JITs most of System.Windows.Forms before it paints anything the
# accessibility tree can see. A five-second wait failed here on a cold run;
# thirty has always been enough.
_READY_TIMEOUT_SECONDS = 30.0

# Not sys.executable, which inside a virtual environment on Windows is a copy
# of CPython's venvlauncher.exe: it starts the real interpreter as a *child*
# process and waits for it. The pid a launch reports is then the launcher's,
# while the window belongs to the child, and no window is ever found for it.
_INTERPRETER = str(Path(sys.base_prefix) / "python.exe")


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


def tk_command() -> list[str]:
    """How the thin-accessibility-tree fixture app is started."""
    return [_INTERPRETER, str(FIXTURE_APPS / "tk_app.py")]


def windows_ocr_is_installed() -> bool:
    """Whether the `ocr` extra is present, asked in the one way that is safe.

    Deliberately not the adapter's own copy of this check: that lives behind an
    import of `uiautomation`, and every spec module here is imported on
    platforms where there is no such package to import.
    """
    try:
        return find_spec("winrt.windows.media.ocr") is not None
    except ModuleNotFoundError:
        # find_spec imports each parent package on the way down, so a missing
        # extra raises out of it rather than answering None.
        return False


@contextmanager
def skipped_when_windows_refuses_synthetic_input() -> Iterator[None]:
    """Treat a desktop that will not accept a click as an unrunnable environment.

    The same category as a missing `ocr` extra, and for the same reason: the
    specs it guards need something this machine is not currently offering.
    While a window owned by a higher-integrity process holds the foreground,
    User Interface Privilege Isolation drops every event this process injects,
    and no amount of retrying inside the driver changes that.

    Deliberately narrow. It catches only `InputRefused`, which is raised on
    Windows' own answer that the event was never delivered — never on a click
    that landed and did nothing, which stays a failure. And it wraps only the
    interaction: everything the specs actually assert about still runs.
    """
    try:
        yield
    except InputRefused as refusal:
        pytest.skip(f"Windows is refusing synthetic mouse input — {refusal}")


@pytest.fixture
def winforms_app() -> Iterator[App]:
    yield from _app_launched_by_its_own_session(winforms_command())


@pytest.fixture
def tk_app() -> Iterator[App]:
    yield from _app_launched_by_its_own_session(tk_command())


def _app_launched_by_its_own_session(command: Sequence[str]) -> Iterator[App]:
    # Imported inside the fixture, not at module scope: conftest is imported on
    # every platform, including the lane where uiautomation is not installed.
    from pytest_uia.application.session import session_on_this_desktop

    session = session_on_this_desktop()
    try:
        yield session.launch(command, ready_timeout=_READY_TIMEOUT_SECONDS)
    finally:
        session.shutdown_all()
