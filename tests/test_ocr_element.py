"""Behavioral spec for how an element found in pixels acts on what it found.

No desktop and no recogniser here: what is specified is the wiring between a
phrase's position and the mouse, including the case the whole retry machinery
exists for, Windows refusing the click outright.
"""

from __future__ import annotations

import asyncio

import pytest

from pytest_uia.adapters.capture import CapturedImage, ScreenRegion
from pytest_uia.domain.errors import ElementNotFound, InputRefused
from pytest_uia.domain.name_match import by_id, containing, matching
from pytest_uia.domain.query import Query, Role
from pytest_uia.domain.text_match import Box, Word

# The adapter reaches WinRT and `uiautomation` the moment it is imported, so a
# machine without the `ocr` extra skips this file rather than failing to
# collect it, the same bargain every other spec that touches OCR makes.
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

    Carries `uiautomation`'s own PascalCase name on purpose, it stands in for
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

    The foreground lock bites for entirely ordinary reasons (another
    application called `LockSetForegroundWindow`, or simply got there first),
    and `SetActive` then answers False having done nothing at all.

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

    # Then the window came forward first (a pointer hits whatever is on top),
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

    # Then nothing was photographed and nothing was read: a grab of a covered
    # window recognises whatever is covering it


def test_typing_into_something_ocr_located_is_refused_rather_than_attempted() -> None:
    # Given a phrase read off the screen: an input box, the label beside one,
    # or a word in a picture, and nothing in the pixels says which
    pointer = RecordingPointer()
    element = _element_clicked_through(pointer)

    # When the test types into it
    with pytest.raises(ocr.OcrTypingRefused) as refusal:
        element.type_text("Buy milk")

    # Then nothing was clicked and nothing was typed: the keys would land
    # wherever clicking a label happens to put the caret
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
    # Given a thread with an event loop already running on it, which is every
    # thread inside a `pytest-asyncio` suite's async test
    async def read_from_inside_the_loop() -> list[Word]:
        return ocr.WindowsOcrReader().recognize(_A_BLANK_IMAGE)

    # When something reached from there asks OCR to read captured pixels
    words = asyncio.run(read_from_inside_the_loop())

    # Then it answers, rather than a bare RuntimeError about a second loop
    assert words == [], "a blank image has no words in it"


class ARectangleOnScreen:
    """Test double: where a window sits, in `uiautomation`'s own vocabulary."""

    left = 0
    top = 0

    def width(self) -> int:
        return 64

    def height(self) -> int:
        return 32


class WindowWithPixels(RecordingWindow):
    """Test double: a window that can also say where its pixels are."""

    Name = "pytest-uia Canvas Fixture"
    BoundingRectangle = ARectangleOnScreen()


class ReaderOfOneLine:
    """Test double: a recogniser that always reads the same painted line."""

    def __init__(self, *texts: str) -> None:
        self._words = [
            Word(text=text, box=Box(left=8 * i, top=0, width=8, height=8), line=0)
            for i, text in enumerate(texts)
        ]

    def recognize(self, image: CapturedImage) -> list[Word]:
        return self._words


class BlankCapture:
    """Test double: a screen grabber handing back the same blank image."""

    def grab(self, region: ScreenRegion) -> CapturedImage:
        return _A_BLANK_IMAGE


def test_a_substring_query_resolves_through_the_words_it_names() -> None:
    # Given a window painted with "task created" and a query loosened to a
    # fragment of it
    locator = ocr.OcrLocator(
        WindowWithPixels(),
        reader=ReaderOfOneLine("task", "created"),
        capture=BlankCapture(),
    )

    # When the fragment is looked for
    element = locator.find(Query(role=Role.TEXT, name=containing("created")))

    # Then the pixel link answers with those words, exactly as it would have
    # for an exact query spelling them out
    assert element.read_text() == "created"


def test_a_pattern_query_is_declined_by_the_pixel_link_before_any_screen_grab() -> None:
    # Given a query only a regular expression can express
    window = WindowWithPixels()
    locator = ocr.OcrLocator(
        window,
        reader=NeverAskedReader(),
        capture=NeverAskedCapture(),
    )

    # When the pixel link is asked for it
    with pytest.raises(ElementNotFound) as miss:
        locator.find(Query(role=Role.TEXT, name=matching(r"task \d+")))

    # Then it declined as a miss the chain can report, without stealing the
    # foreground for a photograph it could never match against
    assert window.activations == 0, (
        "a query the pixels can never answer must not cost a foreground steal"
    )
    assert "pattern" in str(miss.value), (
        f"the reason has to say the pixel link cannot do patterns: {miss.value}"
    )


def test_an_id_query_is_declined_by_the_pixel_link_before_any_screen_grab() -> None:
    # Given a query by automation id, which no pixel carries
    window = WindowWithPixels()
    locator = ocr.OcrLocator(
        window,
        reader=NeverAskedReader(),
        capture=NeverAskedCapture(),
    )

    # When the pixel link is asked for it
    with pytest.raises(ElementNotFound) as miss:
        locator.find(Query(role=Role.TEXTBOX, name=by_id("date-time-edit")))

    # Then it declined without stealing the foreground for a photograph that
    # could never carry an id
    assert window.activations == 0
    assert "id" in str(miss.value)


def test_scoping_a_query_inside_words_read_off_the_screen_misses_honestly() -> None:
    # Given an element that is nothing but a phrase and its position
    element = _element_clicked_through(RecordingPointer())

    # When something is looked for inside it
    with pytest.raises(ElementNotFound) as miss:
        element.contents().find(Query(role=Role.TEXT, name="anything"))

    # Then the miss says pixels have no inside, rather than pretending an
    # empty search happened
    assert "inside" in str(miss.value), (
        f"the reason has to say what pixels cannot offer: {miss.value}"
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
