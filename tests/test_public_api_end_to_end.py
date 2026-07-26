"""The journey a user writes on their first day, driven exactly as they write it.

Nothing in this module reaches past the public surface — no locators, no
adapters, no policies. If this reads awkwardly, the API is wrong.
"""

from __future__ import annotations

import sys

import pytest

from pytest_uia.application.session import GuiSession
from tests.conftest import winforms_command

pytestmark = [
    pytest.mark.gui,
    pytest.mark.skipif(
        sys.platform != "win32",
        reason="UI Automation is a Windows API",
    ),
]


def test_the_readme_journey_runs_through_the_public_api(gui: GuiSession) -> None:
    app = gui.launch(winforms_command())

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
