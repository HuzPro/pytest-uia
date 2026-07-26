"""Behavioral spec for noticing that Windows threw a synthetic click away.

Runs against doubles, and deliberately so: the failure being specified here is
one no fixture app can stage on demand. While a window owned by a
higher-integrity process holds the foreground, User Interface Privilege
Isolation drops every event this process injects and `SetCursorPos` answers 0 —
and `uiautomation.Click` discards that answer, so the click looks like it
worked and the test fails seconds later blaming the application.
"""

from __future__ import annotations

import pytest

from pytest_uia.adapters.input import CheckedPointer
from pytest_uia.domain.errors import InputRefused

_A_POINT_ON_A_BUTTON = (120, 340)


class AcceptingMouse:
    """Test double: a mouse Windows lets through, remembering where it aimed."""

    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []

    def click_at(self, x: int, y: int) -> bool:
        self.clicks.append((x, y))
        return True

    def foreground_holder(self) -> str:
        return "'FixtureWindow' (pid 1234)"


class RefusingMouse(AcceptingMouse):
    """Test double: a mouse whose every event Windows drops on the floor."""

    def __init__(self, holder: str = "'GameInputServiceWindow' (pid 6680)") -> None:
        super().__init__()
        self._holder = holder

    def click_at(self, x: int, y: int) -> bool:
        self.clicks.append((x, y))
        return False

    def foreground_holder(self) -> str:
        return self._holder


def test_a_click_windows_allows_is_aimed_at_the_point_it_was_given() -> None:
    # Given a pointer over a mouse Windows is currently letting through
    mouse = AcceptingMouse()
    pointer = CheckedPointer(mouse)

    # When a caller clicks the point an element was found at
    pointer.click(*_A_POINT_ON_A_BUTTON)

    # Then the click went to exactly that point, and nothing was raised
    assert mouse.clicks == [_A_POINT_ON_A_BUTTON], (
        "the pointer must aim where it was told, in the desktop's own pixels"
    )


def test_a_click_windows_refuses_raises_instead_of_looking_like_it_worked() -> None:
    # Given a pointer over a mouse whose every event Windows is dropping
    pointer = CheckedPointer(RefusingMouse())

    # When a caller clicks
    with pytest.raises(InputRefused):
        pointer.click(*_A_POINT_ON_A_BUTTON)

    # Then it hears about it now, rather than from an assertion five seconds
    # later saying the application never reacted


def test_a_refused_click_blames_the_window_that_is_holding_the_foreground() -> None:
    # Given a pointer refused while a service's window owns the foreground
    pointer = CheckedPointer(RefusingMouse("'GameInputServiceWindow' (pid 6680)"))

    # When a caller clicks
    with pytest.raises(InputRefused) as refusal:
        pointer.click(*_A_POINT_ON_A_BUTTON)

    # Then the report names the culprit and what to do about it, because the
    # reader has no other way to find out why their desktop ignores the mouse
    reason = str(refusal.value)
    assert "'GameInputServiceWindow' (pid 6680)" in reason, (
        f"a refusal that does not name the foreground window is a shrug: {reason}"
    )
    assert "integrity" in reason, (
        f"the reader has to be told this is UIPI, not a broken click: {reason}"
    )
