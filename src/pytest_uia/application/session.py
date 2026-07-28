"""The owner of every application a test launches, and of killing them again.

Sits behind the `gui` fixture: a test asks a session for an app, and the
session guarantees that nothing it started is still on screen once the test
ends. Knows nothing about pytest, and nothing about Windows either: the
desktop arrives as a port.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol
from warnings import warn

from pytest_uia.application.app_process import AppProcess
from pytest_uia.application.driver import (
    DEFAULT_POLICY,
    App,
    RunningProcess,
    Window,
)
from pytest_uia.domain.errors import LaunchFailed, WindowNotFound
from pytest_uia.domain.waiting import RetryPolicy, poll


class WindowUnderTest(Window, Protocol):
    """A located top-level window, and the search that runs inside it.

    Everything the driver already needs of a window, plus the one thing only a
    session does: the pid, which is what an attached window is owned by and
    what a launched one has to be matched against.
    """

    @property
    def pid(self) -> int: ...


class LaunchedProcess(RunningProcess, Protocol):
    """A process this session started, and can therefore ask how it ended.

    Everything the driver already needs of a process, plus the one thing only a
    launch does: decide whether a window is still coming, or whether the
    command is already over.
    """

    def exit_code(self) -> int | None: ...


class Desktop(Protocol):
    """Where windows come from: the one seam between a session and Windows.

    Both lookups are one-shot and raise WindowNotFound, because waiting is
    `poll`'s job here exactly as it is for elements.
    """

    def window_of_process(self, pid: int) -> WindowUnderTest: ...

    def window_titled(self, title: str) -> WindowUnderTest: ...


class NotOursToEnd:
    """Null Object standing in for the process behind an attached window.

    A session that did not start a process has no business killing it: the
    window a test attached to may belong to something the developer is using.
    Closing that window is as far as `App.close()` may go.
    """

    def __init__(self, pid: int) -> None:
        self._pid = pid

    @property
    def pid(self) -> int:
        return self._pid

    def terminate(self) -> None:
        return


class GuiSession:
    """Every app one test launched, and the promise to leave none behind."""

    def __init__(
        self,
        *,
        desktop: Desktop,
        start_process: Callable[[Sequence[str]], LaunchedProcess] = AppProcess.launch,
        policy: RetryPolicy = DEFAULT_POLICY,
    ) -> None:
        self._desktop = desktop
        self._start_process = start_process
        self._policy = policy
        self._apps: list[App] = []
        self._unclaimed: list[RunningProcess] = []

    def launch(self, command: Sequence[str], *, ready_timeout: float = 30.0) -> App:
        """Start the command and block until its window is on screen."""
        process = self._start_process(command)
        # Held by the session until an App can take it over. An app that never
        # paints is exactly the one that would otherwise be left running.
        self._unclaimed.append(process)
        window = poll(
            lambda: self._whatever_window_it_paints(process),
            self._looking_for_at_most(ready_timeout),
            retry_on=WindowNotFound,
        )
        app = App(window.contents, window=window, process=process, policy=self._policy)
        self._apps.append(app)
        self._unclaimed.remove(process)
        return app

    def attach(self, *, title: str, timeout: float = 10.0) -> App:
        """Drive a window this session did not start, found by its caption."""
        window = poll(
            lambda: self._desktop.window_titled(title),
            self._looking_for_at_most(timeout),
            retry_on=WindowNotFound,
        )
        # Not added to the shutdown list on purpose: see NotOursToEnd.
        return App(
            window.contents,
            window=window,
            process=NotOursToEnd(window.pid),
            policy=self._policy,
        )

    def shutdown_all(self) -> None:
        """Leave nothing this session started still running."""
        for app in self._apps:
            _whatever_happens(app.close)
        for process in self._unclaimed:
            _whatever_happens(process.terminate)
        self._apps.clear()
        self._unclaimed.clear()

    def _whatever_window_it_paints(self, process: LaunchedProcess) -> WindowUnderTest:
        # The window is looked for first and the process only questioned when
        # there was none: a launcher that exits once the real application is up
        # (`cmd /c`, a console-script shim, a `.bat`) has done nothing wrong.
        try:
            return self._desktop.window_of_process(process.pid)
        except WindowNotFound:
            _refuse_to_wait_for_a_command_that_is_already_over(process)
            raise

    def _looking_for_at_most(self, timeout: float) -> RetryPolicy:
        # A launching app repaints on its own message pump, so waiting for its
        # window is the same kind of waiting as waiting for a control in it:
        # same rhythm, longer deadline.
        return RetryPolicy(timeout=timeout, interval=self._policy.interval)


def session_on_this_desktop(*, policy: RetryPolicy = DEFAULT_POLICY) -> GuiSession:
    """Composition root: a session wired to the real Windows desktop.

    The UIA adapter is imported here rather than at module scope so that
    importing this package (which pytest does on every platform the moment the
    plugin is installed) never requires `uiautomation` to be present.
    """
    from pytest_uia.adapters.uia import UiaDesktop

    return GuiSession(desktop=UiaDesktop(), policy=policy)


def _refuse_to_wait_for_a_command_that_is_already_over(
    process: LaunchedProcess,
) -> None:
    """Fail now, with the exit code, rather than out-waiting a dead process.

    Without this, a command that exits immediately spends the whole ready
    timeout and reports `WindowNotFound`, mentioning neither the exit nor its
    code.
    """
    code = process.exit_code()
    if code is None:
        return
    raise LaunchFailed(
        f"the launched command exited with code {code} before it owned a window"
    )


def _whatever_happens(step: Callable[[], None]) -> None:
    # Deliberately blind, and deliberately per step. Teardown is the one place
    # where stopping at the first failure is the worst possible answer: every
    # app after it would be left on the next test's screen.
    try:
        step()
    except Exception as failure:  # noqa: BLE001
        # Blind is not the same as silent. An app that could not be ended goes
        # on to poison every test after it, and this teardown is the only place
        # that knows which run left it there.
        warn(f"pytest-uia could not shut down an app it launched: {failure}")
