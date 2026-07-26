"""Behavioral spec for how an element found in pixels acts on what it found.

No desktop and no recogniser here: what is specified is the wiring between a
phrase's position and the mouse, including the case the whole retry machinery
exists for — Windows refusing the click outright.
"""

from __future__ import annotations

import pytest

from pytest_uia.domain.errors import InputRefused

# The adapter reaches WinRT and `uiautomation` the moment it is imported, so a
# machine without the `ocr` extra skips this file rather than failing to
# collect it — the same bargain every other spec that touches OCR makes.
ocr = pytest.importorskip("pytest_uia.adapters.ocr", reason="install pytest-uia[ocr]")

_WHERE_THE_WORDS_WERE_READ = (120, 340)
_WHY_THE_DESKTOP_REFUSED = "the foreground is held by 'GameInputServiceWindow'"


class RecordingPointer:
    """Test double: a mouse that remembers where it was aimed."""

    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))


class RefusedPointer:
    """Test double: the pointer Windows is currently dropping every event from."""

    def click(self, x: int, y: int) -> None:
        raise InputRefused(_WHY_THE_DESKTOP_REFUSED)


class RecordingWindow:
    """Test double: a window that remembers being brought to the front.

    Carries `uiautomation`'s own PascalCase name on purpose — it stands in for
    one of its Controls, and renaming it would hide that.
    """

    def __init__(self) -> None:
        self.activations = 0

    def SetActive(self) -> None:
        self.activations += 1


def _element_clicked_through(pointer: object) -> object:
    return ocr.OcrElement(
        "New Task",
        ocr.ClickPoint(*_WHERE_THE_WORDS_WERE_READ),
        RecordingWindow(),
        pointer=pointer,
    )


def test_clicking_words_read_off_the_screen_aims_the_pointer_at_where_they_were() -> (
    None
):
    # Given an element standing for a phrase recognised at a known point
    window = RecordingWindow()
    pointer = RecordingPointer()
    element = ocr.OcrElement(
        "New Task",
        ocr.ClickPoint(*_WHERE_THE_WORDS_WERE_READ),
        window,
        pointer=pointer,
    )

    # When the test clicks it
    element.click()

    # Then the window came forward first — a pointer hits whatever is on top —
    # and the click landed on the pixels the phrase was read from
    assert window.activations == 1, (
        "a click on a background window presses whatever is covering it"
    )
    assert pointer.clicks == [_WHERE_THE_WORDS_WERE_READ], (
        "the click must land where the words were, in the desktop's own pixels"
    )


def test_a_click_windows_drops_is_reported_rather_than_passing_for_a_click() -> None:
    # Given a desktop refusing every event this process injects
    element = _element_clicked_through(RefusedPointer())

    # When the test clicks it
    with pytest.raises(InputRefused) as refusal:
        element.click()

    # Then the caller can retry or report; swallowing it here is what turned a
    # foreground thief into "the application never reacted"
    assert _WHY_THE_DESKTOP_REFUSED in str(refusal.value), (
        f"the refusal has to reach the caller intact: {refusal.value}"
    )
