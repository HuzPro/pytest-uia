"""The pitch, executed: one journey, two windows, two ways of being found.

The WinForms fixture exposes a full accessibility tree and is driven through
it. The Tk fixture exposes controls with no names at all, and is driven by
reading its pixels. The test body below cannot tell the difference, and that
is the entire point of this project.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

import pytest

from pytest_uia.application.session import GuiSession
from tests.conftest import tk_command, windows_ocr_is_installed, winforms_command

pytestmark = [
    pytest.mark.gui,
    pytest.mark.skipif(
        sys.platform != "win32",
        reason="both locators are Windows APIs",
    ),
    pytest.mark.skipif(
        not windows_ocr_is_installed(),
        reason="install pytest-uia[ocr]",
    ),
]


@pytest.mark.parametrize(
    "launch_command",
    [
        pytest.param(winforms_command, id="winforms-through-the-accessibility-tree"),
        pytest.param(tk_command, id="tkinter-through-ocr"),
    ],
)
def test_the_same_journey_drives_winforms_via_uia_and_tkinter_via_ocr(
    gui: GuiSession,
    launch_command: Callable[[], list[str]],
) -> None:
    app = gui.launch(launch_command())

    app.button("New Task").click()

    assert app.text("task created").exists(), (
        "the journey that passes against a window with an accessibility tree "
        "has to pass against one without it, unchanged"
    )
