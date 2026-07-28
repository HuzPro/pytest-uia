"""End-to-end spec for the `gui` fixture, run the way a user would run it.

Each spec writes a miniature project into tmp_path, runs a real `pytest` there
against the installed plugin, and then (from outside that run, once it is
over) asks Windows whether the app it launched is still alive. Nothing short
of a separate process can prove that, which is why these are not unit tests.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import winforms_command

pytestmark = [
    pytest.mark.gui,
    pytest.mark.skipif(
        sys.platform != "win32",
        reason="UI Automation is a Windows API",
    ),
]

# A whole pytest startup plus a WinForms launch, with room for a cold JIT.
_CHILD_RUN_BUDGET_SECONDS = 300

_PASSING_TEST = """\
import pytest

WINFORMS_COMMAND = {command!r}
PID_FILE = {pid_file!r}


@pytest.mark.gui
def test_the_fixture_app_can_be_driven(gui):
    app = gui.launch(WINFORMS_COMMAND)
    open(PID_FILE, "w").write(str(app.pid))

    assert app.title == "pytest-uia WinForms Fixture"
"""

_FAILING_TEST = """\
import pytest

WINFORMS_COMMAND = {command!r}
PID_FILE = {pid_file!r}


@pytest.mark.gui
def test_something_goes_wrong_while_an_app_is_open(gui):
    app = gui.launch(WINFORMS_COMMAND)
    open(PID_FILE, "w").write(str(app.pid))

    assert False, "the app is still on screen when this blows up"
"""


_IMPATIENT_TEST = """import time

import pytest

from pytest_uia.domain.errors import ElementNotFound

WINFORMS_COMMAND = {command!r}
PID_FILE = {pid_file!r}


@pytest.mark.gui
def test_a_control_the_window_does_not_have_fails_within_the_configured_wait(gui):
    app = gui.launch(WINFORMS_COMMAND)
    open(PID_FILE, "w").write(str(app.pid))

    started = time.monotonic()
    with pytest.raises(ElementNotFound):
        app.button("Delete Everything").click()
    elapsed = time.monotonic() - started

    assert elapsed < 1.0, f"--uia-timeout=0 was ignored: the lookup took {{elapsed:.1f}}s"
"""


def _write_project(root: Path, body: str) -> Path:
    pid_file = root / "launched.pid"
    (root / "test_generated_gui.py").write_text(
        body.format(command=winforms_command(), pid_file=str(pid_file)),
        encoding="utf-8",
    )
    return pid_file


def _run_pytest_in(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", ".", "-q", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_CHILD_RUN_BUDGET_SECONDS,
        check=False,
    )


def _is_running(pid: int) -> bool:
    listing = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    return str(pid) in listing.stdout


def test_a_test_using_the_gui_fixture_launches_and_tears_down_its_app(
    tmp_path: Path,
) -> None:
    # Given a project whose one test launches the fixture app through `gui`
    pid_file = _write_project(tmp_path, _PASSING_TEST)

    # When it is run by a real pytest
    result = _run_pytest_in(tmp_path)

    # Then the test passed, so the fixture really did drive the app
    assert result.returncode == 0, result.stdout + result.stderr
    # and nothing it launched is still running now that the run is over
    launched_pid = int(pid_file.read_text(encoding="utf-8"))
    assert not _is_running(launched_pid), (
        f"pid {launched_pid} outlived the test that launched it"
    )


def test_an_app_leaked_by_a_failing_test_is_still_killed_at_teardown(
    tmp_path: Path,
) -> None:
    # Given a project whose one test fails with the app still open
    pid_file = _write_project(tmp_path, _FAILING_TEST)

    # When it is run by a real pytest
    result = _run_pytest_in(tmp_path)

    # Then the failure was reported, not swallowed
    assert result.returncode != 0, (
        f"the generated test was supposed to fail:\n{result.stdout}"
    )
    # and the window is gone anyway, because teardown does not care how it went
    launched_pid = int(pid_file.read_text(encoding="utf-8"))
    assert not _is_running(launched_pid), (
        f"pid {launched_pid} was leaked by a failing test: every run after it "
        "now shares the desktop with a window nobody owns"
    )


def test_uia_timeout_sets_the_implicit_wait_every_lookup_inherits(
    tmp_path: Path,
) -> None:
    # Given a project whose one test asserts a control is absent
    _write_project(tmp_path, _IMPATIENT_TEST)

    # When it is run with no patience configured at all
    result = _run_pytest_in(tmp_path, "--uia-timeout=0")

    # Then the lookup gave up at once instead of spending the built-in default
    assert result.returncode == 0, result.stdout + result.stderr
