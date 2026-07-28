"""Fixtures for the specs that drive real applications on the real desktop.

The `gui` fixture a user gets comes from the installed plugin
(:mod:`pytest_uia.hooks`) and is deliberately not redefined here. What this
adds is the three fixture apps, each launched through the same session the
plugin hands out, so the specs below exercise the shipped wiring rather than a
copy of it.

The set is the point. WinForms exposes a full accessibility tree and always
did; Tk exposes one because `tk_uia` annotates it; the canvas window exposes
nothing at all, and is the only one left that the pixel path has to carry. The
same journey has to run against all three, and it has to be visible which of
them was answered out of the tree.
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

# A `skipif` marks a test; it cannot stop pytest importing the module carrying
# it. The specs named after the UIA adapter reach `uiautomation` and `comtypes`
# at module scope, and both are declared `sys_platform == 'win32'`, so off
# Windows they are not collected at all, otherwise the lane that exists to
# prove the domain is platform-independent dies during collection instead.
# Every other spec either imports its adapter inside the test or asks for it
# with `pytest.importorskip`.
collect_ignore_glob = [] if sys.platform == "win32" else ["test_uia_*.py"]

# WinForms JITs most of System.Windows.Forms before it paints anything the
# accessibility tree can see. A five-second wait failed here on a cold run;
# thirty has always been enough.
_READY_TIMEOUT_SECONDS = 30.0

# `sys.executable` inside a venv is a launcher whose child owns the window; it
# is also exactly what a user writes, so the product has to cope with it.
_INTERPRETER = sys.executable


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
    """How the annotated-Tk fixture app is started."""
    return [_INTERPRETER, str(FIXTURE_APPS / "tk_app.py")]


def tk_notebook_command() -> list[str]:
    """How the fixture app whose pages sit behind a notebook is started."""
    return [_INTERPRETER, str(FIXTURE_APPS / "tk_notebook_app.py")]


def tk_gallery_command() -> list[str]:
    """How the fixture app holding one of every kind of control is started."""
    return [_INTERPRETER, str(FIXTURE_APPS / "tk_gallery_app.py")]


def tk_canvas_command() -> list[str]:
    """How the fixture app with no accessibility tree at all is started."""
    return [_INTERPRETER, str(FIXTURE_APPS / "tk_canvas_app.py")]


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


def tk_uia_is_installed() -> bool:
    """Whether the Tk fixture app's accessibility library is present.

    Same shape and same rationale as the check above. Without it a missing
    `tk_uia` kills the fixture app during its own imports, and the spec that
    wanted it reports a thirty-second "no visible top-level window" timeout:
    a failure that says nothing at all about what is actually missing.
    """
    try:
        return find_spec("tk_uia") is not None
    except ModuleNotFoundError:
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
    Windows' own answer that the event was never delivered, never on a click
    that landed and did nothing, which stays a failure. And it wraps only the
    interaction: everything the specs actually assert about still runs.
    """
    try:
        yield
    except InputRefused as refusal:
        pytest.skip(f"Windows is refusing synthetic mouse input -- {refusal}")


@pytest.fixture
def winforms_app() -> Iterator[App]:
    yield from _app_launched_by_its_own_session(winforms_command())


@pytest.fixture
def tk_app() -> Iterator[App]:
    yield from _app_launched_by_its_own_session(tk_command())


@pytest.fixture
def tk_notebook_app() -> Iterator[App]:
    yield from _app_launched_by_its_own_session(tk_notebook_command())


@pytest.fixture
def tk_gallery_app() -> Iterator[App]:
    yield from _app_launched_by_its_own_session(tk_gallery_command())


@pytest.fixture
def tk_canvas_app() -> Iterator[App]:
    yield from _app_launched_by_its_own_session(tk_canvas_command())


def _app_launched_by_its_own_session(command: Sequence[str]) -> Iterator[App]:
    # Imported inside the fixture, not at module scope: conftest is imported on
    # every platform, including the lane where uiautomation is not installed.
    from pytest_uia.application.session import session_on_this_desktop

    session = session_on_this_desktop()
    try:
        yield session.launch(command, ready_timeout=_READY_TIMEOUT_SECONDS)
    finally:
        session.shutdown_all()
