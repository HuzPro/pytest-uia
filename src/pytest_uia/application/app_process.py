"""The operating-system process behind an application under test.

Everything above this module talks about windows and elements; this is the one
place that knows an app is also a pid that has to be started and, above all,
stopped again.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from pytest_uia.domain.errors import ProcessStillRunning

_DEFAULT_GRACE_SECONDS = 5.0

# An app under test should put exactly one window on screen: its own. A console
# host alongside it makes "the window belonging to this pid" ambiguous, and it
# flashes up on every launch. Fetched by name because the flag is Windows-only
# and this module still has to import where there is no desktop at all.
_NO_CONSOLE_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Process(Protocol):
    """The slice of a running process this module depends on.

    Popen satisfies it structurally, which keeps the escalation ladder testable
    without spawning something genuinely unkillable.
    """

    @property
    def pid(self) -> int: ...

    def poll(self) -> int | None: ...

    def wait(self, timeout: float | None = ...) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


def kill_process_tree(pid: int) -> None:
    """Last resort: Windows' own killer, which also takes the app's children."""
    subprocess.run(
        ["taskkill", "/pid", str(pid), "/t", "/f"],
        capture_output=True,
        check=False,
    )


class AppProcess:
    """A launched application, owned for exactly as long as a test needs it."""

    def __init__(
        self,
        process: Process,
        *,
        force_kill_tree: Callable[[int], None] = kill_process_tree,
    ) -> None:
        self._process = process
        self._force_kill_tree = force_kill_tree

    @classmethod
    def launch(cls, command: Sequence[str], *, cwd: Path | None = None) -> AppProcess:
        return cls(subprocess.Popen(command, cwd=cwd, creationflags=_NO_CONSOLE_WINDOW))

    @property
    def pid(self) -> int:
        return self._process.pid

    def exit_code(self) -> int | None:
        """What the process ended with, or None while it is still running."""
        return self._process.poll()

    def is_running(self) -> bool:
        return self.exit_code() is None

    def wait_for_exit(self, timeout_seconds: float) -> bool:
        """Block until the process is gone; True if it went before the timeout."""
        try:
            self._process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            return False
        return True

    def terminate(self, grace_seconds: float = _DEFAULT_GRACE_SECONDS) -> None:
        """Escalate through ruder and ruder ways of ending the process.

        Every rung gets the grace period to work. Running out of rungs raises:
        returning quietly would leave a surviving app on the next test's
        screen with no record of which run left it there.
        """
        for request_exit in self._escalating_exit_requests():
            request_exit()
            if self.wait_for_exit(grace_seconds):
                return
        raise ProcessStillRunning(
            f"pid {self.pid} survived terminate, kill and a forced kill of its "
            f"whole tree, and is still running"
        )

    def _escalating_exit_requests(self) -> tuple[Callable[[], None], ...]:
        return (
            self._process.terminate,
            self._process.kill,
            lambda: self._force_kill_tree(self.pid),
        )
