"""Behavioral spec for the session that owns every app a test launches.

The session is the thing standing between a suite and a desktop full of
orphaned windows, so its specs are about lifecycle rather than about clicking:
what it waits for before handing an app over, and what it guarantees to kill.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from pytest_uia.application.session import GuiSession
from pytest_uia.domain.errors import LaunchFailed, WindowNotFound
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

    def __init__(self, pid: int, *, exited_with: int | None = None) -> None:
        self.pid = pid
        self.terminations = 0
        self._exited_with = exited_with
        self._unkillable = False

    def exit_code(self) -> int | None:
        return self._exited_with

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


class DesktopShowingNothing:
    """Test double: a desktop the launched command never puts a window on.

    Distinct from a desktop that paints late: there is no attempt count at
    which this one relents, which is what makes it able to say that a launch
    gave up for a reason other than running out of patience.
    """

    def __init__(self) -> None:
        self.lookups = 0

    def window_of_process(self, pid: int) -> FakeWindow:
        self.lookups += 1
        raise WindowNotFound(f"no visible top-level window for pid {pid}")


class DesktopShowingSomebodyElsesWindow:
    """Test double: a desktop with a window this session never launched."""

    def __init__(self, title: str) -> None:
        self.window = FakeWindow(title)
        self.titles_looked_up: list[str] = []

    def window_titled(self, title: str) -> FakeWindow:
        self.titles_looked_up.append(title)
        return self.window


class RecordingLauncher:
    """Test double: starts nothing, but remembers what it was asked to start.

    `exits_with` is the everyday disaster: a typo in the command path, an
    import error in the app, a `.bat` that returns 1. The process really is
    started, and it is dead again long before any window could have appeared.
    """

    def __init__(self, *, exits_with: int | None = None) -> None:
        self.commands: list[Sequence[str]] = []
        self.started: list[FakeProcess] = []
        self._exits_with = exits_with

    def __call__(self, command: Sequence[str]) -> FakeProcess:
        self.commands.append(command)
        process = FakeProcess(
            _FIRST_PID + len(self.started), exited_with=self._exits_with
        )
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


def test_launching_a_command_that_dies_at_once_fails_with_the_code_it_died_with() -> (
    None
):
    # Given a command that exits before it could ever have painted anything —
    # a typo in the path, an import error, a wrapper script returning non-zero
    desktop = DesktopShowingNothing()
    launcher = RecordingLauncher(exits_with=3)
    session = GuiSession(desktop=desktop, start_process=launcher, policy=_NO_PAUSE)

    # When a test launches it with the generous deadline a real app needs
    with pytest.raises(LaunchFailed) as died:
        session.launch(WINFORMS_COMMAND, ready_timeout=30.0)

    # Then it was told at once, and told what actually happened. Waiting out the
    # full deadline and then reporting "no visible top-level window for pid
    # 19940" describes a process that has been dead the whole time, and is the
    # first wall every newcomer with a mistyped command walks into
    reason = str(died.value)
    assert "3" in reason, f"the exit code is the whole diagnosis: {reason}"
    assert desktop.lookups == 1, (
        f"a dead process cannot grow a window, so the deadline is pure delay: "
        f"{desktop.lookups} look(s)"
    )


def test_a_launcher_that_exits_once_its_real_application_is_up_is_not_a_failure() -> (
    None
):
    # Given a shim that starts the application and returns straight away, with
    # the window belonging to a pid the session never saw
    desktop = DesktopPaintingLate(shows_window_on_attempt=1)
    launcher = RecordingLauncher(exits_with=0)
    session = GuiSession(desktop=desktop, start_process=launcher, policy=_NO_PAUSE)

    # When a test launches through it
    app = session.launch(WINFORMS_COMMAND)

    # Then the window on screen settles it. `cmd /c`, a console-script wrapper
    # and a `.bat` all exit the moment the real application is up, so an exited
    # pid is only evidence of anything when there is no window to be found
    assert app.title == "Fixture", (
        "a launcher's own exit must not be mistaken for the application's"
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

    # When the test that owned them ends. The wedged app complains on its way
    # past — that is the sibling spec's subject, and caught here so this one's
    # warning does not surface in every unrelated run of the suite.
    with pytest.warns(UserWarning, match=str(_FIRST_PID)):
        session.shutdown_all()

    # Then the second app was still killed, whatever the first one did
    assert launcher.started[1].terminations == 1, (
        "one unkillable app must not turn every later window into a leak"
    )


def test_shutdown_says_out_loud_which_app_it_could_not_end() -> None:
    # Given a session whose only app is wedged past saving
    desktop = DesktopPaintingLate(shows_window_on_attempt=1)
    launcher = RecordingLauncher()
    session = GuiSession(desktop=desktop, start_process=launcher, policy=_NO_PAUSE)
    session.launch(WINFORMS_COMMAND)
    launcher.started[0].refuse_to_die()

    # When the test that owned it ends
    with pytest.warns(UserWarning, match=str(_FIRST_PID)) as complaints:
        session.shutdown_all()

    # Then teardown carried on — blind by design, so one bad app strands none of
    # the others — but it did not carry on silently. An app left running poisons
    # every test after it, and the run that caused it is the only one that knows
    assert complaints, "a leak nobody is told about is a leak nobody looks for"


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
