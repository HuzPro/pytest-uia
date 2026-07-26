"""The journey a user writes on their first day, driven exactly as they write it.

Nothing in this module reaches past the public surface — no locators, no
adapters, no policies. If this reads awkwardly, the API is wrong.

The journey runs against both fixture apps, and the point of that is that the
body does not change. One is a WinForms window whose provider honours every
pattern it advertises; the other is a Tkinter window whose provider advertises
the same patterns and honours none of them, and which is reachable at all only
because the application annotated itself.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

import pytest

from pytest_uia.application.session import GuiSession
from tests.conftest import (
    skipped_when_windows_refuses_synthetic_input,
    tk_command,
    tk_uia_is_installed,
    winforms_command,
)

pytestmark = [
    pytest.mark.gui,
    pytest.mark.skipif(
        sys.platform != "win32",
        reason="UI Automation is a Windows API",
    ),
]


@pytest.mark.parametrize(
    "launch_command",
    [
        pytest.param(winforms_command, id="winforms"),
        pytest.param(
            tk_command,
            id="tkinter",
            marks=pytest.mark.skipif(
                not tk_uia_is_installed(),
                reason="install tk-uia: the Tk fixture app annotates itself with it",
            ),
        ),
    ],
)
def test_the_readme_journey_runs_through_the_public_api(
    gui: GuiSession,
    launch_command: Callable[[], list[str]],
) -> None:
    app = gui.launch(launch_command())

    # The README's own lines, verbatim. The `with` is the single addition, and
    # it says something about this machine rather than about the journey: the
    # Tk half drives a provider whose patterns are pretence, so it injects real
    # mouse input, and a desktop that is dropping it cannot run the spec.
    with skipped_when_windows_refuses_synthetic_input():
        app.textbox("Title").type_text("Buy milk")
        app.button("New Task").click()

    assert app.text("task created").exists()


def test_attaching_to_a_running_window_by_title_drives_the_same_app(
    gui: GuiSession,
) -> None:
    # Given an app already on screen
    launched = gui.launch(winforms_command())

    # When a second handle on it is taken by the caption on its title bar
    attached = gui.attach(title="pytest-uia WinForms Fixture")
    attached.button("New Task").click()

    # Then the click landed in the very same application
    assert launched.text("task created").exists(), (
        "attaching by title found a window other than the one just launched"
    )
