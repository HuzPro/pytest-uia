"""Behavioral spec for addressing a child modal dialog by the caption it carries.

Where it plugs in: the public surface only — no locators, no adapters — over the
Tk fixture app's first-run dialog, on the real desktop.

What is being proven is *not* that a dialog is reachable. It always was: Tk owns
its `Toplevel` at the Win32 level, so UI Automation nests it inside its owner's
subtree and a search that starts at the main window walks straight into it. What
was missing is a way for a test to say which of two windows it meant, and the
fixture app makes that question real by putting a button named `Confirm` on both.
Both of the specs below fail against a dialog whose search starts at the main
window: the first drives whichever button the tree offers first, and the second
sees the main window's controls from inside the dialog.
"""

from __future__ import annotations

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
    pytest.mark.skipif(
        not tk_uia_is_installed(),
        reason="install tk-uia: the fixture app annotates itself with it",
    ),
]

OPEN_SETTINGS = "Open Settings"
SETTINGS = "Settings"
CONFIRM = "Confirm"
FOLDER = "Folder"
NEW_TASK = "New Task"

SETTINGS_SAVED = "settings saved"
MAIN_CONFIRMED = "main confirmed"

A_CHOSEN_FOLDER = r"C:\data"

# Nothing is on its way: these are the assertions that something is *absent*,
# and spending the implicit wait on them would only make the suite slower.
_ALREADY_SETTLED = 0.0


def test_the_confirm_a_dialog_is_driven_by_is_its_own_and_not_the_one_underneath(
    tk_app: App,
) -> None:
    # Given the app's modal dialog open over a main window whose own Confirm is
    # a different button of the same name
    with skipped_when_windows_refuses_synthetic_input():
        tk_app.button(OPEN_SETTINGS).click()
        settings = tk_app.dialog(SETTINGS)

        # When the test drives the Confirm inside the dialog
        settings.button(CONFIRM).click()

    # Then the dialog's own button is the one that ran
    assert tk_app.text(SETTINGS_SAVED).exists(), (
        "the Confirm inside the dialog never reached the command behind it"
    )
    # and the identically named button one window out never did
    assert not tk_app.text(MAIN_CONFIRMED).exists(timeout=_ALREADY_SETTLED), (
        "the click landed on the main window's Confirm, which is the ambiguity "
        "addressing a dialog by name exists to remove"
    )


def test_a_control_that_only_the_main_window_has_is_out_of_a_dialogs_reach(
    tk_app: App,
) -> None:
    # Given the same dialog open over the same main window
    with skipped_when_windows_refuses_synthetic_input():
        tk_app.button(OPEN_SETTINGS).click()
    settings = tk_app.dialog(SETTINGS)

    # When the dialog is asked for a button only the window underneath it has
    within_the_dialog = settings.button(NEW_TASK).exists(timeout=_ALREADY_SETTLED)

    # Then it is not there. This is the whole difference between scoping and
    # nothing at all: the main window's subtree *contains* the dialog, so a
    # search that started there would answer this one yes
    assert within_the_dialog is False, (
        "a query scoped to the dialog reached a control on the window "
        "underneath it, so the scope is not a narrowing at all"
    )
    # and it really is on screen, one window out
    assert tk_app.button(NEW_TASK).exists(), (
        "the main window's own button has gone missing, so the assertion above "
        "proves nothing about scope"
    )


def test_a_wizard_step_can_be_filled_in_confirmed_and_then_waited_out(
    tk_app: App,
) -> None:
    # Given the app's modal dialog, with a folder box that is nobody else's
    with skipped_when_windows_refuses_synthetic_input():
        tk_app.button(OPEN_SETTINGS).click()
        settings = tk_app.dialog(SETTINGS)

        # When the test fills it in and confirms it
        settings.textbox(FOLDER).type_text(A_CHOSEN_FOLDER)
        settings.textbox(FOLDER).wait_until_text_is(A_CHOSEN_FOLDER)
        settings.button(CONFIRM).click()

    # Then the step ends: the dialog goes away, and what it saved is left behind
    settings.wait_closed()

    assert not tk_app.has_dialog(SETTINGS, timeout=_ALREADY_SETTLED), (
        "the dialog is still on screen after the wait that said it had gone"
    )
    assert tk_app.text(SETTINGS_SAVED).exists(), (
        "the dialog closed without its Confirm having reached the application"
    )
