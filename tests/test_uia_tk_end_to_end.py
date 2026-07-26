"""Behavioral spec for driving a Tkinter window through the accessibility tree.

Where it plugs in: the same UIA adapter the WinForms specs drive, aimed at the
toolkit that used to be reachable only by reading its pixels. The fixture app
says who its widgets are, through `tk_uia`; the adapter believes only the parts
of a provider that are true. Both halves are needed, and each is useless alone.

These specs launch a real window on the developer's desktop and inject real
mouse input, because a Tk button's InvokePattern returns cleanly and fires
nothing.
"""

from __future__ import annotations

import sys

import pytest

from pytest_uia.adapters.uia import UiaLocator, resolve_main_window
from pytest_uia.application.driver import App
from pytest_uia.domain.errors import ElementNotFound
from pytest_uia.domain.query import Query, Role
from pytest_uia.domain.waiting import RetryPolicy, poll
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

NEW_TASK_BUTTON = Query(role=Role.BUTTON, name="New Task")
TASK_CREATED_LABEL = Query(role=Role.TEXT, name="task created")
TITLE_TEXTBOX = Query(role=Role.TEXTBOX, name="Title")

A_DRAFT = "Write the report"

# The app reacts on its own message pump, so the repaint lands after the call
# that caused it has already returned.
_REACTION_POLICY = RetryPolicy(timeout=5.0, interval=0.25)


def test_a_tk_button_carrying_an_accessible_name_is_found_by_that_name_in_the_accessibility_tree(
    tk_app: App,
) -> None:
    # Given a locator over the Tk window the fixture app just put on screen
    locator = UiaLocator(resolve_main_window(tk_app.pid))

    # When the button is looked up by the name a screen reader would announce
    button = locator.find(NEW_TASK_BUTTON)

    # Then the control that answers is the button the user can see — which bare
    # Tk offers under no name at all, and so under no query at all
    assert button.read_text() == "New Task", (
        "the located control is not the button the fixture app shows"
    )


def test_clicking_a_tk_button_found_in_the_tree_reaches_the_command_behind_it(
    tk_app: App,
) -> None:
    # Given the fixture app's button, with its status line still saying "ready"
    locator = UiaLocator(resolve_main_window(tk_app.pid))
    button = locator.find(NEW_TASK_BUTTON)

    # When it is clicked exactly as a test drives any other button
    with skipped_when_windows_refuses_synthetic_input():
        button.click()

    # Then the Tk command behind it actually ran. Nothing weaker will do: the
    # button advertises an InvokePattern, and the proxy behind it accepts the
    # call, returns no error and fires nothing — so a test that only checked
    # the click for an exception would pass having done nothing at all.
    status = poll(
        lambda: locator.find(TASK_CREATED_LABEL),
        _REACTION_POLICY,
        retry_on=ElementNotFound,
    )

    assert status.read_text() == "task created", (
        "the click never reached the button's own command"
    )


def test_typing_into_an_annotated_tk_entry_lands_in_the_widget_and_reads_back_through_its_value(
    tk_app: App,
) -> None:
    # Given the app's empty title box, reached through the same fluent element a
    # user's own suite writes against, and found by the name the application had
    # to give it — an entry carries no words of its own to infer one from
    title = tk_app.textbox(TITLE_TEXTBOX.name)
    assert title.read_text() == "", (
        "an entry nobody has typed into has to read as empty rather than as "
        "its own name, or the wait below is satisfied by a box that never "
        "changed"
    )

    # When a test types into it and waits for that value to come back out
    with skipped_when_windows_refuses_synthetic_input():
        title.type_text(A_DRAFT)

    settled = title.wait_until_text_is(A_DRAFT)

    # Then every seam in both packages carried its part: the click gave the
    # widget the caret Tk would not hand over any other way, the keys landed in
    # it, its variable changed, `bind_value_variable` re-announced the new
    # value, and the tree gives it back. The driver absorbs the race between
    # those steps, which is where it bites — the keys land before Tk's message
    # pump has run, so without the wait the tree still reports the old value to
    # the assertion that follows the call which changed it
    assert settled.read_text() == A_DRAFT, (
        "what a client reads out of an edit control is its value, and that is "
        "not what was typed into the widget"
    )
