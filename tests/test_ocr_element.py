"""Behavioral spec for how an element found in pixels acts on what it found.

No desktop and no recogniser here: what is specified is the wiring between a
phrase's position and the mouse, including the case the whole retry machinery
exists for — Windows refusing the click outright.
"""

from __future__ import annotations

import asyncio

import pytest

from pytest_uia.adapters.capture import CapturedImage, ScreenRegion
from pytest_uia.domain.errors import InputRefused
from pytest_uia.domain.query import Query, Role
from pytest_uia.domain.text_match import Word

# The adapter reaches WinRT and `uiautomation` the moment it is imported, so a
# machine without the `ocr` extra skips this file rather than failing to
# collect it — the same bargain every other spec that touches OCR makes.
ocr = pytest.importorskip("pytest_uia.adapters.ocr", reason="install pytest-uia[ocr]")

_WHERE_THE_WORDS_WERE_READ = (120, 340)
_WHY_THE_DESKTOP_REFUSED = "the foreground is held by 'GameInputServiceWindow'"

TASK_CREATED = Query(role=Role.TEXT, name="task created")

_BLANK = 255
_A_BLANK_IMAGE = CapturedImage(width=64, height=32, bgra=bytes([_BLANK] * 64 * 32 * 4))


def _windows_has_no_ocr_language_pack() -> bool:
    """Whether Windows itself can read text here, asked without a screen grab.

    Reached only after the `importorskip` above has already proved the WinRT
    projections are installed, which is what makes this import safe here.
    """
    from winrt.windows.media.ocr import OcrEngine

    return OcrEngine.try_create_from_user_profile_languages() is None


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
    one of its Controls, and renaming it would hide that. Answers True the way
    `SetActive` does when `SetForegroundWindow` worked.
    """

    def __init__(self) -> None:
        self.activations = 0

    def SetActive(self) -> bool:
        self.activations += 1
        return True


class WindowThatStaysBehind:
    """Test double: a window Windows would not bring to the front.

    The foreground lock bites for entirely ordinary reasons — another
    application called `LockSetForegroundWindow`, or simply got there first —
    with no integrity level involved, and `SetActive` then answers False having
    done nothing at all.

    It still answers for its own caption, which is what tells it apart from a
    window whose application has exited: that one declines to come forward too,
    and raises rather than naming itself.
    """

    Name = "pytest-uia Canvas Fixture"

    def SetActive(self) -> bool:
        return False


class NeverAskedReader:
    """Test double: a recogniser that fails if anything asks it to read."""

    def recognize(self, image: CapturedImage) -> list[Word]:
        raise AssertionError("nothing should be recognised out of a covered window")


class NeverAskedCapture:
    """Test double: a screen grabber that fails if anything asks it to grab."""

    def grab(self, region: ScreenRegion) -> CapturedImage:
        raise AssertionError("a covered window must not be photographed at all")


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


def test_clicking_words_in_a_window_that_will_not_come_forward_is_refused() -> None:
    # Given a phrase read from a window Windows keeps behind another
    pointer = RecordingPointer()
    element = ocr.OcrElement(
        "New Task",
        ocr.ClickPoint(*_WHERE_THE_WORDS_WERE_READ),
        WindowThatStaysBehind(),
        pointer=pointer,
    )

    # When the test clicks it
    with pytest.raises(InputRefused):
        element.click()

    # Then the pointer was never aimed at a point another application now owns
    assert pointer.clicks == [], (
        "a point measured inside a window means nothing once something else is "
        "on top of it"
    )


def test_reading_a_window_that_will_not_come_forward_is_refused_rather_than_guessed() -> (
    None
):
    # Given a locator over a window Windows keeps behind another
    locator = ocr.OcrLocator(
        WindowThatStaysBehind(),
        reader=NeverAskedReader(),
        capture=NeverAskedCapture(),
    )

    # When a phrase is looked for in it
    with pytest.raises(InputRefused):
        locator.find(TASK_CREATED)

    # Then nothing was photographed and nothing was read. A grab of a covered
    # window faithfully recognises whatever is covering it, and the miss that
    # follows says "phrase not visible" about a phrase that is right there —
    # the exact misleading failure class v0.1 removed for clicks


def test_typing_into_something_ocr_located_is_refused_rather_than_attempted() -> None:
    # Given a phrase read off the screen. It may be an input box, or the label
    # beside one, or a word in a picture — nothing in the pixels says which
    pointer = RecordingPointer()
    element = _element_clicked_through(pointer)

    # When the test types into it
    with pytest.raises(ocr.OcrTypingRefused) as refusal:
        element.type_text("Buy milk")

    # Then nothing was clicked and nothing was typed. Clicking the recognised
    # phrase and sending keys is the coin-flip the roadmap refuses outright:
    # it puts the caret wherever clicking a *label* happens to put it, and the
    # text then goes somewhere nobody chose. This is the same move the adapter
    # already makes for an MSAA-proxy `Invoke` — decline a call that only
    # pretends to work — turned on this package's own API
    assert pointer.clicks == [], (
        "a call that cannot be honoured must not half-run before saying so"
    )

    # and the refusal says what to do instead, because the reader of it is
    # someone whose app has no accessibility tree and no obvious next step
    reason = str(refusal.value)
    assert "label" in reason, (
        f"the reason has to name the confusion it cannot resolve: {reason}"
    )
    assert "UIA" in reason, f"the way out is a control UIA can see: {reason}"


@pytest.mark.skipif(
    _windows_has_no_ocr_language_pack(),
    reason="Windows has no OCR language pack for any of this user's languages",
)
def test_recognising_pixels_works_on_a_thread_that_already_runs_an_event_loop() -> None:
    # Given a thread with an event loop already running on it — which is every
    # thread inside a `pytest-asyncio` suite's async test
    async def read_from_inside_the_loop() -> list[Word]:
        return ocr.WindowsOcrReader().recognize(_A_BLANK_IMAGE)

    # When something reached from there asks OCR to read captured pixels
    words = asyncio.run(read_from_inside_the_loop())

    # Then it answers. `asyncio.run` refuses to start a second loop on a thread
    # that already has one, so recognition used to raise a bare RuntimeError
    # about event loops — from outside the domain's error contract entirely,
    # and in the one place a caller has no reason to suspect asyncio at all
    assert words == [], "a blank image has no words in it"


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
