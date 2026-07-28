"""Behavioral spec for every kind of control a test can ask for, in one window.

Reads only, apart from the checkbox: the claim is that each one can be found,
and that toggle state can be read back after acting on it.
"""

from __future__ import annotations

import sys

import pytest

from pytest_uia.adapters.uia import UiaLocator, resolve_main_window
from pytest_uia.application.driver import App
from pytest_uia.domain.errors import ElementNotFound
from pytest_uia.domain.query import Query, Role
from tests.conftest import (
    skipped_when_windows_refuses_synthetic_input,
    tk_uia_is_installed,
)

pytestmark = [
    pytest.mark.gui,
    pytest.mark.skipif(
        sys.platform != "win32", reason="UI Automation is a Windows API"
    ),
    pytest.mark.skipif(
        not tk_uia_is_installed(),
        reason="install tk-uia: the fixture app annotates itself with it",
    ),
]

# Declared here rather than imported from the fixture app, which is a script and
# reaches `legible` the way a script does. Drift cannot hide: every one of these
# is asserted by name below.
EVERY_CONTROL_IN_THE_GALLERY = [
    ("checkbox", "Notify me"),
    ("radio", "By email"),
    ("slider", "Volume"),
    ("spinbox", "Quantity"),
    ("combobox", "Priority"),
    ("listbox", "Search results"),
    ("tree", "Task list"),
    ("progressbar", "Upload progress"),
    ("scrollbar", "Scroll the results"),
    ("group", "Details"),
    ("image", "Activity sparkline"),
    ("split_button", "Actions"),
    ("separator", "Divider"),
    ("thumb", "Resize this window"),
    ("tab_strip", "Settings"),
]

NOTIFY_ME = "Notify me"
UPLOAD_PROGRESS = "Upload progress"


@pytest.mark.parametrize(("call", "name"), EVERY_CONTROL_IN_THE_GALLERY)
def test_every_kind_of_control_is_found_by_the_call_named_after_it(
    tk_gallery_app: App, call: str, name: str
) -> None:
    # Given a Tk window holding one of every kind of control, each named
    # When the test asks for one the way its own method spells it
    found = getattr(tk_gallery_app, call)(name).exists()

    # Then it is there. Each of these was announced correctly to a screen reader
    # and reachable by nothing here: a role the plugin does not ask for makes a
    # perfectly accessible control invisible to every test ever written.
    assert found, f"app.{call}({name!r}) found nothing"


def test_a_control_of_the_wrong_kind_is_refused_by_a_query_for_another(
    tk_gallery_app: App,
) -> None:
    # Given the checkbox, which is named "Notify me", and the accessibility
    # locator on its own rather than the whole chain
    locator = UiaLocator(resolve_main_window(tk_gallery_app.pid))

    # When something asks for a *button* or a *slider* by that name
    # Then neither is found. Fifteen new roles is fifteen new ways for a query
    # to match something it should not, and a role that matched anything would
    # make every spec above pass for the wrong reason.
    for wrong in (Role.BUTTON, Role.SLIDER):
        with pytest.raises(ElementNotFound):
            locator.find(Query(role=wrong, name=NOTIFY_ME))

    # Deliberately not asked of `app.button(...)`, which is the whole chain: its
    # second link reads pixels, and pixels have no roles. Measured, the OCR
    # fallback finds the words "Notify me" painted on that checkbox and answers
    # a query for a button with them. That is the documented behaviour of the
    # fallback and not a defect in the role table, so the role's own claim is
    # asked of the locator that makes it.


def test_clicking_a_checkbox_changes_the_state_a_test_can_read_back(
    tk_gallery_app: App,
) -> None:
    # Given a checkbox that starts unchecked
    with skipped_when_windows_refuses_synthetic_input():
        checkbox = tk_gallery_app.checkbox(NOTIFY_ME)
        assert checkbox.is_checked() is False, "the gallery's checkbox starts checked"

        # When the test clicks it
        checkbox.click()

        # Then the state a client reads has changed. This is the pair that makes
        # a checkbox testable at all: a suite that clicked and assumed would
        # pass just as happily when the click went nowhere, which on an
        # owner-drawn Tk button it silently can.
        assert checkbox.is_checked() is True, (
            "the checkbox was clicked and still reads as unchecked"
        )


def test_asking_whether_something_that_cannot_be_checked_is_checked_says_no(
    tk_gallery_app: App,
) -> None:
    # Given a control with no toggle state at all
    # When a test asks anyway
    # Then it answers rather than raising. False is the honest answer to "is
    # this checked" for something that cannot be, and the query that found it
    # has already refused every control of the wrong kind.
    assert tk_gallery_app.group("Details").is_checked() is False


def test_the_dump_offers_a_query_for_every_control_in_the_gallery(
    tk_gallery_app: App,
) -> None:
    # Given the window as it opens
    queries = tk_gallery_app.dump().queries

    # Then every control is offered as the call that reaches it. The dump is
    # where somebody meets a window for the first time; a control listed with no
    # query beside it is a wall they cannot pass.
    missing = [
        f'app.{call}("{name}")'
        for call, name in EVERY_CONTROL_IN_THE_GALLERY
        if f'app.{call}("{name}")' not in queries
    ]
    assert missing == [], f"the dump offers no way to reach {missing}"
