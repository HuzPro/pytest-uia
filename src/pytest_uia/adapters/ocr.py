"""Adapter over Windows' built-in OCR engine: a window read as pixels.

The last link of the locator chain; it runs only for surfaces UIA cannot
answer for. **OCR ignores `query.role`**: it sees text alone, so roles are
honoured by UIA and by UIA alone. Recognition runs on a fresh worker thread:
`asyncio.run` breaks under a caller that already has an event loop, and the
WinRT blocking `get()` refuses the STA that importing `uiautomation` created.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

import uiautomation as auto
from winrt.windows.foundation import Rect
from winrt.windows.graphics.imaging import (
    BitmapAlphaMode,
    BitmapPixelFormat,
    SoftwareBitmap,
)
from winrt.windows.media.ocr import OcrEngine, OcrResult
from winrt.windows.storage.streams import DataWriter

from pytest_uia.adapters.capture import (
    CapturedImage,
    MssScreenCapture,
    ScreenCapture,
    ScreenRegion,
)
from pytest_uia.adapters.input import WINDOWS_POINTER, PointerInput
from pytest_uia.adapters.uia import bring_to_the_front, reporting_a_dead_window_as
from pytest_uia.domain.errors import ElementNotFound
from pytest_uia.domain.name_match import ById, Containing, Exactly, NameMatch
from pytest_uia.domain.query import Query
from pytest_uia.domain.text_match import Box, Word, find_phrase

# LocatorChain prefixes these with the locator's class name, so each has to
# read as a bare reason rather than as a repetition of the query.
_NOT_VISIBLE = "phrase not visible"
_NO_PATTERNS_IN_PAINT = "the pixel link matches painted words, not patterns"
_NO_IDS_IN_PAINT = "the pixel link matches painted words, not automation ids"
_NOTHING_INSIDE_PAINT = "words read off the screen have no inside to search"

# UIA runs on the calling thread and so does everything that leads here, so
# there is never a second recognition wanting the pool at the same time.
_ONE_RECOGNITION_AT_A_TIME = 1


class OcrUnavailable(RuntimeError):
    """Windows itself cannot read text here, so no phrase could ever match.

    Deliberately not an ElementNotFound: the chain absorbs those and reports a
    missing element, which would blame the application for a machine that has
    no OCR language pack installed.
    """


class OcrTypingRefused(NotImplementedError):
    """Typing into something located in pixels was asked for, and declined.

    Not an ElementNotFound: the chain absorbs those, which would blame the
    application for a call this package refuses to make. Refused because OCR
    cannot tell an input box from the label beside it, so the keys would land
    wherever clicking a label puts the caret.
    """


class TextReader(Protocol):
    """Where words come from: the seam between the locator and an OCR engine."""

    def recognize(self, image: CapturedImage) -> list[Word]: ...


class WindowsOcrReader:
    """Adapter presenting Windows.Media.Ocr as a reader of captured pixels."""

    def recognize(self, image: CapturedImage) -> list[Word]:
        result = _recognized(_bitmap_of(image))
        return [
            Word(text=word.text, box=_box_of(word.bounding_rect), line=index)
            for index, line in enumerate(result.lines)
            for word in line.words
        ]


_READER = WindowsOcrReader()
_CAPTURE = MssScreenCapture()


class OcrLocator:
    """Adapter presenting what a window paints as the domain's Locator.

    Takes the same top-level UIA control the accessibility-tree locator uses:
    window-level UIA works even where the contents expose nothing, and the
    window is both the region to photograph and the thing to bring to the front
    before photographing it.
    """

    def __init__(
        self,
        window: auto.Control,
        *,
        reader: TextReader = _READER,
        capture: ScreenCapture = _CAPTURE,
        pointer: PointerInput = WINDOWS_POINTER,
    ) -> None:
        self._window = window
        self._reader = reader
        self._capture = capture
        self._pointer = pointer

    def find(self, query: Query) -> OcrElement:
        # Declined before anything is photographed: a query the pixels can
        # never answer must not cost a foreground steal on every poll.
        phrase = _the_phrase_meant_by(query.name)
        # A window that has died is the chain's *last* link reaching for a
        # rectangle that no longer exists, and it raised a bare HRESULT where
        # the whole point of this locator being last is that it reports a miss.
        with reporting_a_dead_window_as(ElementNotFound, self._window):
            region = self._region_of_the_window_in_front()
            words = self._reader.recognize(self._capture.grab(region))
        box = find_phrase(words, phrase)
        if box is None:
            raise ElementNotFound(_NOT_VISIBLE)
        return OcrElement(
            phrase,
            _screen_point_of(box, region),
            self._window,
            pointer=self._pointer,
        )

    def _region_of_the_window_in_front(self) -> ScreenRegion:
        # Nothing may overlap the window: a grab photographs whatever is on
        # top, so a window that would not come forward is refused rather than
        # photographed anyway.
        bring_to_the_front(self._window)
        return _region_of(self._window)


def _the_phrase_meant_by(match: NameMatch | ById) -> str:
    # Pixels hold words: an exact name and a fragment both mean "these words
    # are painted somewhere", which is what `find_phrase` looks for.
    if isinstance(match, Exactly):
        return match.text
    if isinstance(match, Containing):
        return match.fragment
    if isinstance(match, ById):
        raise ElementNotFound(_NO_IDS_IN_PAINT)
    raise ElementNotFound(_NO_PATTERNS_IN_PAINT)


@dataclass(frozen=True)
class ClickPoint:
    """Somewhere on the desktop the mouse can be aimed, in physical pixels."""

    x: int
    y: int


class OcrElement:
    """Adapter presenting a recognised phrase as the domain's Element.

    Knows only what a person looking at the screen knows: some words, and where
    they are. Every interaction therefore goes through the mouse and the
    keyboard, because there is no accessibility pattern to ask instead.
    """

    def __init__(
        self,
        phrase: str,
        point: ClickPoint,
        window: auto.Control,
        *,
        pointer: PointerInput = WINDOWS_POINTER,
    ) -> None:
        self._phrase = phrase
        self._point = point
        self._window = window
        self._pointer = pointer

    def click(self) -> None:
        with reporting_a_dead_window_as(ElementNotFound, self._window):
            # The pointer hits whatever is on top, so the window has to be in
            # front before a point measured inside it means anything.
            bring_to_the_front(self._window)
            # Not `uiautomation.Click`, which discards Windows' answer: a click
            # the desktop refused has to be distinguishable from one the app
            # ignored.
            self._pointer.click(self._point.x, self._point.y)

    def type_text(self, text: str) -> None:
        # Clicking and then sending keys is the only thing this element could
        # do, and it is not good enough to ship: see OcrTypingRefused.
        raise OcrTypingRefused(
            f"cannot type {text!r} into {self._phrase!r}: OCR reads text and "
            "nothing else, so it cannot tell an input box from the label "
            "beside it, and typing into what it matched would put the keys "
            "wherever clicking those words happened to put the caret. Give "
            "the box an accessible name so UIA can see it (for a Tk "
            "application that is `tk_uia.enable(root)`), or type through an "
            "element UIA located instead"
        )

    def read_text(self) -> str:
        return self._phrase

    def is_visible(self) -> bool:
        # Unconditionally true, and honestly so: being painted on the screen is
        # the only way this element could have been located at all.
        return True

    def scroll_into_view(self) -> None:
        # Nothing to do, for the same reason is_visible answers True.
        return

    def contents(self) -> NothingInside:
        return NothingInside()


class NothingInside:
    """Locator for the inside of a recognised phrase, which pixels do not have."""

    def find(self, query: Query) -> OcrElement:
        raise ElementNotFound(_NOTHING_INSIDE_PAINT)


def _screen_point_of(box: Box, region: ScreenRegion) -> ClickPoint:
    # The recogniser answers in the captured image's own coordinates; the mouse
    # is aimed in the desktop's. The only thing between them is where the grab
    # was taken from.
    return ClickPoint(
        x=region.left + int(box.left + box.width / 2),
        y=region.top + int(box.top + box.height / 2),
    )


def _region_of(window: auto.Control) -> ScreenRegion:
    rectangle = window.BoundingRectangle
    return ScreenRegion(
        left=rectangle.left,
        top=rectangle.top,
        width=rectangle.width(),
        height=rectangle.height(),
    )


def _recognized(bitmap: SoftwareBitmap) -> OcrResult:
    # Waited for on a thread of its own, for the two reasons in the module
    # docstring: the calling thread may already be running an event loop, and
    # it is certainly in the apartment `uiautomation` put it in. The worker is
    # joined before this returns, so nothing outlives the call.
    with ThreadPoolExecutor(max_workers=_ONE_RECOGNITION_AT_A_TIME) as worker:
        return worker.submit(lambda: _engine().recognize_async(bitmap).get()).result()


def _engine() -> OcrEngine:
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise OcrUnavailable(
            "Windows has no OCR language pack installed for any of this "
            "user's languages, so nothing on screen can be read"
        )
    return engine


def _bitmap_of(image: CapturedImage) -> SoftwareBitmap:
    writer = DataWriter()
    writer.write_bytes(image.bgra)
    # Alpha is ignored rather than premultiplied: a screen grab carries no
    # meaningful alpha channel, and treating its zeroes as transparency hands
    # the recogniser a blank image.
    bitmap = SoftwareBitmap(
        BitmapPixelFormat.BGRA8, image.width, image.height, BitmapAlphaMode.IGNORE
    )
    bitmap.copy_from_buffer(writer.detach_buffer())
    return bitmap


def _box_of(rectangle: Rect) -> Box:
    return Box(
        left=rectangle.x,
        top=rectangle.y,
        width=rectangle.width,
        height=rectangle.height,
    )
