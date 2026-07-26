"""Adapter over Windows' built-in OCR engine: a window read as pixels.

Where it plugs in: the last link of the chain a window builds for itself in
:mod:`pytest_uia.adapters.uia`. UIA answers first, and this only ever runs for
surfaces that expose nothing to answer with — Tk widgets, canvas-drawn UI,
anything custom-painted.

**OCR ignores `query.role`.** It can only see text, so it cannot know whether
the phrase it matched was painted on a button, on a label, or in a picture.
The concrete consequence: `app.textbox("Title")` resolved by OCR will match the
*label* reading "Title" beside the box rather than the empty box itself, and
typing then goes wherever clicking that label happens to put the caret. Roles
are honoured by UIA, and by UIA alone.

Recognition runs on the calling thread, inside `asyncio.run`. Should WinRT ever
refuse the apartment comtypes has already put that thread in, the contingency
is to run the recognise on a fresh joined worker thread that has never
initialised COM, contained entirely within `WindowsOcrReader`.
"""

from __future__ import annotations

import asyncio
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
from pytest_uia.domain.errors import ElementNotFound
from pytest_uia.domain.query import Query
from pytest_uia.domain.text_match import Box, Word, find_phrase

# LocatorChain prefixes this with the locator's class name, so it has to read
# as a bare reason rather than as a repetition of the query.
_NOT_VISIBLE = "phrase not visible"


class OcrUnavailable(RuntimeError):
    """Windows itself cannot read text here, so no phrase could ever match.

    Deliberately not an ElementNotFound: the chain absorbs those and reports a
    missing element, which would blame the application for a machine that has
    no OCR language pack installed.
    """


class TextReader(Protocol):
    """Where words come from: the seam between the locator and an OCR engine."""

    def recognize(self, image: CapturedImage) -> list[Word]: ...


class WindowsOcrReader:
    """Adapter presenting Windows.Media.Ocr as a reader of captured pixels."""

    def recognize(self, image: CapturedImage) -> list[Word]:
        result = asyncio.run(_recognized(_engine(), _bitmap_of(image)))
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
        region = self._region_of_the_window_in_front()
        words = self._reader.recognize(self._capture.grab(region))
        box = find_phrase(words, query.name)
        if box is None:
            raise ElementNotFound(_NOT_VISIBLE)
        return OcrElement(
            query.name,
            _screen_point_of(box, region),
            self._window,
            pointer=self._pointer,
        )

    def _region_of_the_window_in_front(self) -> ScreenRegion:
        # Nothing may overlap the window: a screen grab photographs whatever is
        # on top, and OCR would then faithfully read the wrong application.
        self._window.SetActive()
        return _region_of(self._window)


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
        # The pointer hits whatever is on top, so the window has to be in front
        # before a point measured inside it means anything.
        self._window.SetActive()
        # Not `uiautomation.Click`, which discards Windows' answer: a click the
        # desktop refused has to be distinguishable from one the app ignored.
        self._pointer.click(self._point.x, self._point.y)

    def type_text(self, text: str) -> None:
        # Clicking is the only way to focus something OCR found: there is no
        # value pattern to set, and no control to hand the caret to. Keystrokes
        # land wherever clicking the words put it.
        self.click()
        auto.SendKeys(text, charMode=True)

    def read_text(self) -> str:
        return self._phrase

    def is_visible(self) -> bool:
        # Unconditionally true, and honestly so: being painted on the screen is
        # the only way this element could have been located at all.
        return True


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


async def _recognized(engine: OcrEngine, bitmap: SoftwareBitmap) -> OcrResult:
    # WinRT hands back an IAsyncOperation, which is awaitable but is not a
    # coroutine; asyncio.run insists on one, so this is the wrapper that turns
    # the former into the latter.
    return await engine.recognize_async(bitmap)


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
