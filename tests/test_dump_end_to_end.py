"""Behavioral spec for `app.dump()` against the three real fixture windows.

Where it plugs in: the public surface only, on the real desktop. The formatter
is specified exhaustively with hand-built nodes in `tests/test_tree_dump.py`
and the walk with doubles in `tests/test_uia_tree_walk.py`; what is left, and
what only a real window can answer, is whether the two agree about an
application nobody wrote for this test.

The three windows are the argument in miniature: WinForms has always had a full
accessibility tree, Tk has one because `tk_uia` annotated it, and the canvas
window has nothing at all, and the dump has to be useful about all three,
including the one where the honest answer is "no query will ever reach this".

These specs take no input and steal no foreground. The dump reads properties
and never clicks, types or photographs anything, so unlike every other gui spec
here they are immune to a desktop that is refusing synthetic input.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from pytest_uia.application.driver import App
from tests.conftest import (
    skipped_when_windows_refuses_synthetic_input,
    tk_uia_is_installed,
)

pytestmark = [
    pytest.mark.gui,
    pytest.mark.skipif(
        sys.platform != "win32",
        reason="UI Automation is a Windows API",
    ),
]

SETTINGS = "Settings"
OPEN_SETTINGS = "Open Settings"
WINFORMS_FIXTURE = "pytest-uia WinForms Fixture"

_A_MINUTE = 60


def test_the_dump_of_a_real_window_prints_the_query_that_finds_its_button(
    winforms_app: App,
) -> None:
    # Given the WinForms fixture on screen, whose journey the README opens with
    # When the test dumps it
    dump = winforms_app.dump()
    rendered = str(dump)

    # Then the three queries that journey is written in come back out of a real
    # accessibility tree, ready to paste. This is the whole feature: not that
    # the controls are there, but that the reader is handed the calls
    assert 'app.button("New Task")' in rendered, (
        f"the button the README's first example clicks is missing from the "
        f"dump of the window it clicks it in:\n{rendered}"
    )
    assert 'app.textbox("Title")' in dump.queries, (
        f"an edit control has to be offered as a textbox: {dump.queries}"
    )
    assert 'app.text("ready")' in dump.queries, (
        f"a status label has to be offered as text: {dump.queries}"
    )


def test_the_dump_of_a_window_that_paints_its_own_controls_reports_that_none_are_addressable(
    tk_canvas_app: App,
) -> None:
    # Given the canvas fixture on screen: an interface drawn on one Tk canvas,
    # which the accessibility tree serves as anonymous panes and nothing else
    # When the test dumps it
    dump = tk_canvas_app.dump()
    rendered = str(dump)

    # Then it says there is nothing to query, and what to do instead. A tool
    # that printed a tidy tree here would leave the reader convinced their
    # button was somewhere in it
    assert dump.queries == (), (
        f"this window authorises no query at all, and pretending otherwise is "
        f"the failure this feature exists to prevent: {dump.queries}"
    )
    assert "no query: nothing inside it, so what it shows is paint" in rendered, (
        f"an empty pane is the entire diagnosis for a canvas window:\n{rendered}"
    )
    assert "tk_uia.enable(root)" in rendered, (
        f"and for a Tk app the reader owns there is a one-line fix:\n{rendered}"
    )


@pytest.mark.skipif(
    not tk_uia_is_installed(),
    reason="install tk-uia: the fixture app annotates itself with it",
)
def test_the_dump_of_a_dialog_stops_at_that_dialogs_edge(tk_app: App) -> None:
    # Given the Tk fixture with its Settings dialog open, both windows carrying
    # a button named Confirm. Opening it is the one act in this module that
    # needs the desktop's co-operation, so it is the one that can be skipped
    with skipped_when_windows_refuses_synthetic_input():
        tk_app.button(OPEN_SETTINGS).click()
    settings = tk_app.dialog(SETTINGS)

    # When each window is dumped
    everything = tk_app.dump()
    just_the_dialog = settings.dump()

    # Then the app's dump reports the unscoped call as reaching both, and the
    # scoped one as reaching exactly this button. That collision is the reason
    # `app.dialog` exists, and this is the dump showing it rather than
    # describing it
    assert 'ambiguous: 2 controls answer app.button("Confirm")' in str(everything), (
        f"the whole window is where the collision is visible:\n{everything}"
    )
    assert 'app.dialog("Settings").button("Confirm")' in everything.queries, (
        f"and the call that resolves it has to be offered: {everything.queries}"
    )
    # and the dialog's own dump stops at its edge, in its own calls
    assert just_the_dialog.queries == (
        'app.dialog("Settings").button("Confirm")',
        'app.dialog("Settings").textbox("Folder")',
    ), (
        f"a dialog's dump covers exactly the subtree its queries search, and "
        f"answers in the calls a reader holding it would write: "
        f"{just_the_dialog.queries}"
    )


def test_the_command_line_dumps_a_window_that_is_already_on_screen(
    winforms_app: App,
) -> None:
    # Given the WinForms fixture on screen and no test written against it,
    # which is the situation this command exists for
    assert winforms_app.title == WINFORMS_FIXTURE

    # When the command line is run against its caption, as a user would
    finished = subprocess.run(
        [sys.executable, "-m", "pytest_uia", "--title", WINFORMS_FIXTURE],
        capture_output=True,
        text=True,
        timeout=_A_MINUTE,
        check=False,
    )

    # Then the queries are on stdout of a process that did not have to be a
    # test. Attaching never ends what it attached to, so the fixture is still
    # there for the teardown that owns it
    assert 'app.button("New Task")' in finished.stdout, (
        f"the command line is the answer to 'what is my control called' for "
        f"somebody with no test yet:\n{finished.stdout}\n{finished.stderr}"
    )
    assert finished.returncode == 0, (
        f"a window that was found and dumped is a successful run: "
        f"{finished.returncode}\n{finished.stderr}"
    )
