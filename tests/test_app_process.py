"""Behavioral spec for the process lifecycle behind every launched app.

A gui suite that leaks processes poisons every run after it, so the one thing
this has to get right is that terminate() never returns while the app is alive.
"""

from __future__ import annotations

import subprocess
import sys

from pytest_uia.application.app_process import AppProcess

# A child that outlives the whole suite unless something really kills it.
_SLEEPS_FOR_MINUTES = "import time; time.sleep(300)"

_UNRESPONSIVE_PID = 4242


class StubbornProcess:
    """Test double: a process that ignores every polite request to exit.

    Not a hypothetical. A GUI app wedged in a modal message pump, or one that
    spawned children of its own, routinely survives what Popen offers.
    """

    def __init__(self) -> None:
        self.pid = _UNRESPONSIVE_PID
        self._exited = False

    def poll(self) -> int | None:
        return 0 if self._exited else None

    def wait(self, timeout: float | None = None) -> int:
        if not self._exited:
            raise subprocess.TimeoutExpired(cmd="stubborn", timeout=timeout or 0)
        return 0

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        pass

    def give_up_the_ghost(self) -> None:
        self._exited = True


def test_launch_starts_a_process_that_terminate_reliably_kills() -> None:
    # Given a launched child that would otherwise run for minutes
    process = AppProcess.launch([sys.executable, "-c", _SLEEPS_FOR_MINUTES])

    # When it is asked to terminate
    was_running = process.is_running()
    process.terminate()

    # Then it really was alive, and it is gone by the time terminate returns
    assert was_running, f"pid {process.pid} should be alive right after launch"
    assert not process.is_running(), f"pid {process.pid} outlived terminate()"


def test_terminate_escalates_to_a_forced_tree_kill_when_the_process_ignores_it() -> (
    None
):
    # Given a process that survives every request Popen can make
    stubborn = StubbornProcess()
    killed_trees: list[int] = []

    def kill_tree(pid: int) -> None:
        killed_trees.append(pid)
        stubborn.give_up_the_ghost()

    process = AppProcess(stubborn, force_kill_tree=kill_tree)

    # When it is asked to terminate, with no patience at all
    process.terminate(grace_seconds=0.0)

    # Then the last resort ran against its tree and it is finally gone
    assert killed_trees == [_UNRESPONSIVE_PID], (
        "an app that ignores terminate must still be killed by pid, children and all"
    )
    assert not process.is_running(), "terminate must not give up while the app lives"
