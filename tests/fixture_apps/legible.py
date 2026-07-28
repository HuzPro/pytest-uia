"""How a fixture window makes itself readable, to a person and to a recogniser.

Where it plugs in: imported by the Tk fixture apps beside it. They are run as
scripts, so this sits on `sys.path[0]` next to them rather than being reached
through the `tests` package.

OCR's accuracy floor is small anti-aliased text on a low-contrast background,
so anything a spec may have to read back stays black on white, 12 pt, and far
enough apart that neighbouring words never merge into one recognised run.
"""

from __future__ import annotations

import ctypes
import tkinter as tk

FACE = "Segoe UI"
POINTS = 12
FONT = (FACE, POINTS)
INK = "#000000"
PAPER = "#ffffff"

_PER_MONITOR_DPI_AWARE = 2
_POINTS_PER_INCH = 72
_LOGPIXELSX = 88  # GetDeviceCaps index: the display's horizontal dots per inch


def paint_at_physical_pixel_resolution() -> None:
    """Opt out of DPI virtualisation, which is OCR's worst enemy.

    A process that is not DPI-aware gets its window bitmap-stretched by Windows
    on a scaled display. The text a test then reads back is a blurred copy of
    text that was rendered for a smaller screen, and every coordinate the
    accessibility tree reports for it is in somebody else's pixels.
    """
    ctypes.windll.shcore.SetProcessDpiAwareness(_PER_MONITOR_DPI_AWARE)


def matched_to_this_displays_dpi(root: tk.Misc) -> None:
    """Tell Tk how big a point is here, now that Windows has stopped scaling."""
    root.tk.call("tk", "scaling", _screen_dots_per_inch() / _POINTS_PER_INCH)


def _screen_dots_per_inch() -> float:
    device_context = ctypes.windll.user32.GetDC(0)
    try:
        dots_per_inch = ctypes.windll.gdi32.GetDeviceCaps(device_context, _LOGPIXELSX)
    finally:
        ctypes.windll.user32.ReleaseDC(0, device_context)
    return float(dots_per_inch)
