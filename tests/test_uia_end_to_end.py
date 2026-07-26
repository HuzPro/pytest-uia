"""Behavioral spec for driving a real window through the accessibility tree.

These specs launch an actual application on the developer's desktop. What they
prove cannot be proved with a test double, and what they cost is a few seconds
and exclusive use of the screen.
"""

from __future__ import annotations

import sys
import time

import pytest

from pytest_uia.adapters.uia import UiaDesktop, UiaLocator, resolve_main_window
from pytest_uia.application.driver import App
from pytest_uia.domain.errors import ElementNotFound
from pytest_uia.domain.query import Query, Role
from pytest_uia.domain.waiting import RetryPolicy, poll
from tests.conftest import tk_uia_is_installed

pytestmark = [
    pytest.mark.gui,
    pytest.mark.skipif(
        sys.platform != "win32",
        reason="UI Automation is a Windows API",
    ),
]

NEW_TASK_BUTTON = Query(role=Role.BUTTON, name="New Task")
ABSENT_BUTTON = Query(role=Role.BUTTON, name="Delete Everything")
TASK_CREATED_LABEL = Query(role=Role.TEXT, name="task created")
TITLE_TEXTBOX = Query(role=Role.TEXTBOX, name="Title")

# Generous: a whole window's subtree is walked in milliseconds. Anything near a
# second means something is waiting that should not be.
_ONE_SHOT_BUDGET_SECONDS = 1.0

# The app repaints on its own message pump, so its reaction lands after the
# call that caused it has already returned.
_REACTION_POLICY = RetryPolicy(timeout=5.0, interval=0.25)


def test_uia_locator_finds_a_button_by_its_accessible_name_in_a_real_window(
    winforms_app: App,
) -> None:
    # Given a locator over the window the app just put on screen
    locator = UiaLocator(resolve_main_window(winforms_app.pid))

    # When the button is looked up by the name a screen reader would announce
    button = locator.find(NEW_TASK_BUTTON)

    # Then the control that comes back is the one the user can see
    assert button.read_text() == "New Task", (
        "the located control is not the button the fixture app shows"
    )


def test_a_control_found_in_a_painted_window_reports_itself_as_visible(
    winforms_app: App,
) -> None:
    # Given the button of a window that is up and painted
    locator = UiaLocator(resolve_main_window(winforms_app.pid))
    button = locator.find(NEW_TASK_BUTTON)

    # When the test asks whether the user could actually see it
    visible = button.is_visible()

    # Then it says yes, because it occupies real pixels on the screen
    assert visible, "a control found in a painted window should report as visible"


def test_uia_locator_raises_element_not_found_for_a_name_the_window_does_not_contain(
    winforms_app: App,
) -> None:
    # Given a locator over a window that shows no such button
    locator = UiaLocator(resolve_main_window(winforms_app.pid))

    # When a name the app never puts on screen is looked up
    started = time.monotonic()
    with pytest.raises(ElementNotFound) as miss:
        locator.find(ABSENT_BUTTON)
    elapsed = time.monotonic() - started

    # Then the miss comes back at once, rather than after a wait of its own
    assert elapsed < _ONE_SHOT_BUDGET_SECONDS, (
        f"the miss took {elapsed:.2f}s: uiautomation is retrying underneath "
        "poll(), which makes every configured timeout a multiple of itself"
    )
    # and it names the window it looked in, since that is all a failing test leaves
    assert "pytest-uia WinForms Fixture" in str(miss.value), (
        f"the miss does not say where it looked: {miss.value}"
    )


def test_clicking_a_button_through_the_accessibility_tree_triggers_its_action(
    winforms_app: App,
) -> None:
    # Given the fixture app's button, with its status label still saying "ready"
    locator = UiaLocator(resolve_main_window(winforms_app.pid))
    button = locator.find(NEW_TASK_BUTTON)

    # When it is clicked the way an assistive technology would invoke it
    button.click()

    # Then the app acts on it: a label announcing the new task appears
    status = poll(
        lambda: locator.find(TASK_CREATED_LABEL),
        _REACTION_POLICY,
        retry_on=ElementNotFound,
    )

    assert status.read_text() == "task created", (
        "the click never reached the button's own handler"
    )


def test_typing_into_a_textbox_through_the_value_pattern_sets_its_text(
    winforms_app: App,
) -> None:
    # Given the app's empty title box, found by the name its label gives it
    locator = UiaLocator(resolve_main_window(winforms_app.pid))
    title = locator.find(TITLE_TEXTBOX)

    # When a test types into it
    title.type_text("Write the report")

    # Then the box holds exactly what was typed, character for character
    assert title.read_text() == "Write the report", (
        "an edit control's content is its value, not its accessible name"
    )


class RecordingPointer:
    """Test double: a mouse that remembers being reached for, and never is."""

    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))


def test_the_winforms_button_is_still_invoked_through_its_pattern_rather_than_clicked(
    winforms_app: App,
) -> None:
    # Given the fixture app's button, with a mouse nobody should need
    pointer = RecordingPointer()
    locator = UiaLocator(resolve_main_window(winforms_app.pid), pointer=pointer)

    # When it is clicked
    locator.find(NEW_TASK_BUTTON).click()

    # Then the app reacted
    status = poll(
        lambda: locator.find(TASK_CREATED_LABEL),
        _REACTION_POLICY,
        retry_on=ElementNotFound,
    )
    assert status.read_text() == "task created", (
        "the click never reached the button's own handler"
    )
    # and it reacted to the pattern, not to a pointer. WinForms is served by
    # the same generic MSAA proxy Tk is, so this is the one spec that fails if
    # provider detection ever mistakes a framework that honours Invoke for one
    # that only pretends to — a misfire that costs nothing but correctness,
    # since the mouse works too, right up until the desktop refuses it.
    assert pointer.clicks == [], (
        f"the mouse was used on a control that can be invoked: {pointer.clicks}"
    )


def test_the_desktop_adapter_finds_a_launched_apps_window_and_searches_inside_it(
    winforms_app: App,
) -> None:
    # Given the real desktop
    desktop = UiaDesktop()

    # When the window belonging to the launched pid is asked for
    window = desktop.window_of_process(winforms_app.pid)

    # Then it knows its own caption, and its contents can be searched
    assert window.title == "pytest-uia WinForms Fixture", (
        f"the adapter found some other window: {window.title!r}"
    )
    assert window.contents.find(NEW_TASK_BUTTON).read_text() == "New Task", (
        "a window that cannot search inside itself is no use to a driver"
    )


@pytest.mark.skipif(
    not tk_uia_is_installed(),
    # The only spec in this module that reaches for the Tk fixture app, which
    # annotates itself with `tk_uia` and exits if it cannot. Without the guard a
    # missing dev dependency kills the app during its own imports and surfaces
    # here as a thirty-second "no visible top-level window" — a failure that
    # says nothing whatever about what is actually absent.
    reason="install tk-uia: the Tk fixture app annotates itself with it",
)
def test_a_window_belonging_to_a_child_of_the_launched_process_is_still_found(
    tk_app: App,
) -> None:
    # Given an app started through `sys.executable`, which inside a virtual
    # environment on Windows is a launcher that runs the interpreter as a child
    desktop = UiaDesktop()

    # When the window of the pid the launch reported is asked for
    window = desktop.window_of_process(tk_app.pid)

    # Then the real window comes back, although its owner is a process nobody
    # ever returned to the caller
    assert window.title == "pytest-uia Tk Fixture", (
        f"the adapter found some other window: {window.title!r}"
    )
    assert window.pid != tk_app.pid, (
        "this spec proves nothing unless the launcher really did spawn a child; "
        "if these pids are equal the environment has stopped reproducing the bug"
    )


def test_the_desktop_adapter_finds_a_window_by_the_caption_on_its_title_bar(
    winforms_app: App,
) -> None:
    # Given the real desktop, and an app nobody told the adapter about
    desktop = UiaDesktop()

    # When a window is asked for by title alone
    window = desktop.window_titled("pytest-uia WinForms Fixture")

    # Then that is the window that comes back
    assert window.contents.find(NEW_TASK_BUTTON).read_text() == "New Task", (
        "attaching by title has to reach the same window a pid lookup would"
    )
