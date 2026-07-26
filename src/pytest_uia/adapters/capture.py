"""Adapter over `mss`: a rectangle of the screen, as raw pixels.

Where it plugs in: :mod:`pytest_uia.adapters.ocr` grabs the region a window
occupies and hands the pixels to Windows' OCR engine. The format is chosen for
that consumer — BGRA is what a `SoftwareBitmap` takes and what `mss` already
produces, so no image library sits between the screen and the recogniser.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import mss


@dataclass(frozen=True)
class ScreenRegion:
    """A rectangle of the desktop, in physical pixels.

    Physical, not logical: importing `uiautomation` makes this process
    per-monitor DPI aware, so UIA's rectangles, `mss`'s grabs and the
    coordinates a click is aimed at are all in the same units already.
    """

    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class CapturedImage:
    """Pixels read off the screen, four bytes per pixel, blue-green-red-alpha."""

    width: int
    height: int
    bgra: bytes


class ScreenCapture(Protocol):
    """Where pixels come from: the seam between OCR and the actual desktop."""

    def grab(self, region: ScreenRegion) -> CapturedImage: ...


class MssScreenCapture:
    """Adapter presenting `mss` as the screen-capture port."""

    def grab(self, region: ScreenRegion) -> CapturedImage:
        # A fresh grabber per capture on purpose: an `mss` instance is bound to
        # the thread and the device context it was created on, and one that
        # outlives a display change hands back stale pixels.
        with mss.MSS() as screen:
            shot = screen.grab(
                {
                    "left": region.left,
                    "top": region.top,
                    "width": region.width,
                    "height": region.height,
                }
            )
        return CapturedImage(
            width=shot.width, height=shot.height, bgra=bytes(shot.bgra)
        )
