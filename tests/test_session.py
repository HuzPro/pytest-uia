"""Behavioral spec for the session that owns every app a test launches.

The session is the thing standing between a suite and a desktop full of
orphaned windows, so its specs are about lifecycle rather than about clicking:
what it waits for before handing an app over, and what it guarantees to kill.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from pytest_uia.application.session import GuiSession
from pytest_uia.domain.errors import WindowNotFound
from pytest_uia.domain.query import Query
from pytest_uia.domain.waiting import RetryPolicy

WINFORMS_COMMAND = ["powershell.exe", "-File", "winforms_app.ps1"]

# No pause between looks: these specs are about what a session waits for,
# not about how long a real desktop takes to paint.
_NO_PAUSE = RetryPolicy(timeout=5.0, interval=0.0)

_FIRST_PID = 4242

# A window count no polling run will ever reach.
_NEVER = 10_000


class FakeLocator:
    """Test double: the search that would run inside a located window."""

    def find(self, query: Query) -> object:
        raise WindowNotFound("these specs never search inside the window")


class FakeWindow:
    """Test double: a located top-level window that counts its closures."""

    def __init__(self, title: str = "Fixture") -> None:
        self.title = title
        self.pid = _FIRST_PID
        self.closes = 0
        self.contents = FakeLocator()

    def close(self) -> None:
        self.closes += 1


class FakeProcess:
    """Test double: a launched process that counts how often it was ended."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.terminations = 0
        self._unkillable = False

    def refuse_to_die(self) -> None:
        self._unkillable = True

    def terminate(self) -> None:
        if self._unkillable:
            raise OSError(f"pid {self.pid} cannot be ended")
        self.terminations += 1


class DesktopPaintingLate:
    """Test double: a desktop whose window only appears on the Nth look.

    Launching is not the same as being on screen. A WinForms process exists
    for the better part of a second before it paints anything UIA can see.
    """

    def __init__(self, shows_window_on_attempt: int) -> None:
        self._shows_window_on_attempt = shows_window_on_attempt
        self.window = FakeWindow()
        self.lookups = 0

    def window_of_process(self, pid: int) -> FakeWindow:
        self.lookups += 1
        if self.lookups < self._shows_window_on_attempt:
            raise WindowNotFound(f"no visible top-level window for pid {pid}")
        return self.window


class DesktopShowingSomebodyElsesWindow:
    """Test double: a desktop with a window this session never launched."""

    def __init__(self, title: str) -> None:
        self.window = FakeWindow(title)
        self.titles_looked_up: list[str] = []

    def window_titled(self, title: str) -> FakeWindow:
        self.titles_looked_up.append(title)
        return self.window


class RecordingLauncher:
    """Test double: starts nothing, but remembers what it was asked to start."""

    def __init__(self) -> None:
        self.commands: list[Sequence[str]] = []
        self.started: list[FakeProcess] = []

    def __call__(self, command: Sequence[str]) -> FakeProcess:
        self.commands.append(command)
        process = FakeProcess(_FIRST_PID + len(self.started))
        self.started.append(process)
        return process


def test_launch_waits_for_the_process_to_own_a_window_before_handing_back_an_app() -> (
    None
):
    # Given a desktop that only shows the app's window on the third look
    desktop = DesktopPaintingLate(shows_window_on_attempt=3)
    launcher = RecordingLauncher()
    session = GuiSession(desktop=desktop, start_process=launcher, policy=_NO_PAUSE)

    # When a test launches the app
    app = session.launch(WINFORMS_COMMAND, ready_timeout=5.0)

    # Then it waited for the window, and the app it got back drives that window
    assert desktop.lookups == 3, (
        "an app handed over before it has painted fails on its first lookup"
    )
    assert app.title == "Fixture", "the app is not wired to the window that appeared"
    assert launcher.commands == [WINFORMS_COMMAND], (
        "the session must start the command it was given"
    )


def test_shutdown_all_closes_and_kills_every_app_the_session_launched() -> None:
    # Given a session that launched two apps
    desktop = DesktopPaintingLate(shows_window_on_attempt=1)
    launcher = RecordingLauncher()
    session = GuiSession(desktop=desktop, start_process=launcher, policy=_NO_PAUSE)
    session.launch(WINFORMS_COMMAND)
    session.launch(WINFORMS_COMMAND)

    # When the test that owned them ends
    session.shutdown_all()

    # Then both were asked to close and both processes were ended
    assert desktop.window.closes == 2, "every launched window must be asked to close"
    assert [process.terminations for process in launcher.started] == [1, 1], (
        "a window that is asked to close can still refuse; the pid cannot"
    )


def test_one_app_that_cannot_be_shut_down_does_not_strand_the_others() -> None:
    # Given a session whose first app is wedged past saving
    desktop = DesktopPaintingLate(shows_window_on_attempt=1)
    launcher = RecordingLauncher()
    session = GuiSession(desktop=desktop, start_process=launcher, policy=_NO_PAUSE)
    session.launch(WINFORMS_COMMAND)
    session.launch(WINFORMS_COMMAND)
    launcher.started[0].refuse_to_die()

    # When the test that owned them ends
    session.shutdown_all()

    # Then the second app was still killed, whatever the first one did
    assert launcher.started[1].terminations == 1, (
        "one unkillable app must not turn every later window into a leak"
    )


def test_an_app_whose_window_never_appears_is_still_killed_at_shutdown() -> None:
    # Given a launch that starts a process but never sees a window
    desktop = DesktopPaintingLate(shows_window_on_attempt=_NEVER)
    launcher = RecordingLauncher()
    session = GuiSession(desktop=desktop, start_process=launcher, policy=_NO_PAUSE)
    with pytest.raises(WindowNotFound):
        session.launch(WINFORMS_COMMAND, ready_timeout=0.0)

    # When the test ends
    session.shutdown_all()

    # Then the process that did start is gone, though no app was ever handed out
    assert launcher.started[0].terminations == 1, (
        "a crashed launch leaks its process unless the session owns it from the "
        "moment it is started, not from the moment it is usable"
    )


def test_attach_hands_back_an_app_driving_the_window_with_the_given_title() -> None:
    # Given a desktop showing a window that some other process put there
    desktop = DesktopShowingSomebodyElsesWindow("pytest-uia WinForms Fixture")
    session = GuiSession(desktop=desktop, policy=_NO_PAUSE)

    # When a test attaches to it by the caption on its title bar
    app = session.attach(title="pytest-uia WinForms Fixture")

    # Then it gets an app driving exactly that window
    assert desktop.titles_looked_up == ["pytest-uia WinForms Fixture"], (
        "attach must search by the title it was given, not by anything else"
    )
    assert app.title == "pytest-uia WinForms Fixture", (
        "the attached app is not wired to the window that was found"
    )


def test_shutdown_leaves_a_window_the_session_only_attached_to_alone() -> None:
    # Given a session attached to a window some other process owns
    desktop = DesktopShowingSomebodyElsesWindow("Somebody Else's Editor")
    session = GuiSession(desktop=desktop, policy=_NO_PAUSE)
    session.attach(title="Somebody Else's Editor")

    # When the test that attached to it ends
    session.shutdown_all()

    # Then the window is still open, because the session never started it
    assert desktop.window.closes == 0, (
        "closing what a test merely looked at would shut down the developer's "
        "own applications between runs"
    )
