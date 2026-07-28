"""Behavioral spec for driving an application that is no longer there.

Whole stack rather than doubles: the searches build their own `uiautomation`
objects and cannot be handed a control that misbehaves. The doubles that cover
the rest are in `test_uia_dead_window.py`.
"""

from __future__ import annotations

import sys

import pytest

from pytest_uia.application.driver import App
from pytest_uia.domain.errors import WindowNotFound
from pytest_uia.domain.waiting import RetryPolicy, poll

pytestmark = [
    pytest.mark.gui,
    pytest.mark.skipif(
        sys.platform != "win32",
        reason="UI Automation is a Windows API",
    ),
]

# The caption of a dialog this fixture app has never had, asked for so that the
# answer can only be about the window being gone.
SETTINGS = "Settings"

# A window outlives the process that owned it by however long Windows takes to
# tear it down. Every look is a fresh walk of the process table and a one-shot
# desktop search, so the interval is the domain default rather than tighter.
_GIVING_WINDOWS_TIME_TO_NOTICE = RetryPolicy(timeout=10.0, interval=0.25)


class StillOnScreen(Exception):
    """The application is on its way out and the desktop has not caught up."""


@pytest.fixture
def app_that_has_died(winforms_app: App) -> App:
    """An app the test is still holding, and the application behind it gone.

    Ended through `close()` rather than shot, because that is the ordinary way
    a suite meets this: the last step of a journey clicks Quit. What is left
    behind (a window handle whose provider has died) is exactly what a crash
    leaves behind too.
    """
    pid = winforms_app.pid
    winforms_app.close()
    poll(
        lambda: _no_window_left_for(pid),
        _GIVING_WINDOWS_TIME_TO_NOTICE,
        retry_on=StillOnScreen,
    )
    return winforms_app


def _no_window_left_for(pid: int) -> None:
    # The UIA adapter is imported here rather than at module scope because this
    # module is collected on every platform, and only the specs named after
    # that adapter are shielded from it.
    from pytest_uia.adapters.uia import resolve_main_window

    try:
        resolve_main_window(pid)
    except WindowNotFound:
        return
    raise StillOnScreen(f"pid {pid} still owns a visible window")


def test_a_query_against_an_application_that_has_died_answers_rather_than_raising(
    app_that_has_died: App,
) -> None:
    # When the test asks the question it was in the middle of asking
    present = app_that_has_died.button("New Task").exists(timeout=0.0)

    # Then it gets something to assert on. Both links of the chain are walked
    # here (the accessibility tree first, then the pixels) and each of them
    # was reaching a window that is not there any more
    assert present is False, (
        "`exists()` promises True or False for both directions of assertion, "
        "and an HRESULT out of comtypes keeps neither"
    )


def test_the_title_of_an_application_that_has_died_says_the_window_is_gone(
    app_that_has_died: App,
) -> None:
    # When the test asks the simplest question in the API
    with pytest.raises(WindowNotFound) as gone:
        _ = app_that_has_died.title

    # Then it is told what happened, in the vocabulary the rest of the package
    # uses. A gui failure usually leaves nothing behind but this string, and an
    # HRESULT is not something anybody can act on
    assert "gone" in str(gone.value), (
        f"the reader has to be told the window went away: {gone.value}"
    )


def test_asking_a_dead_application_whether_a_dialog_is_open_answers_rather_than_raising(
    app_that_has_died: App,
) -> None:
    # When the test asks whether a wizard step is up
    up = app_that_has_died.has_dialog(SETTINGS, timeout=0.0)

    # Then no dialog is open, which is the truth about an application that has
    # exited, and the answer `has_dialog` exists to give instead of an
    # exception a caller would have to catch
    assert up is False, "a dead application has no dialogs on screen"
