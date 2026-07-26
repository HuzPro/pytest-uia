"""Fixture app whose contents have no accessibility tree, driven by the OCR specs.

Stands in for the surfaces UIA cannot see: ATLAS's Tk first-run dialogs, and
custom-drawn UI generally. Same journey as the WinForms fixture — a "New Task"
trigger and a status line that becomes "task created" — so the hybrid spec can
run one test body against both.

Stdlib only, on purpose: a fixture app that needed installing would be a second
thing to debug when a gui spec goes red.
"""

from __future__ import annotations

import ctypes
import tkinter as tk

WINDOW_TITLE = "pytest-uia Tk Fixture"
NEW_TASK = "New Task"
READY = "ready"
TASK_CREATED = "task created"

# OCR's accuracy floor is small anti-aliased text on a low-contrast background,
# so this fixture stays deliberately legible: black on white, 12 pt, and enough
# padding that neighbouring words never merge into one recognised run.
_FACE = "Segoe UI"
_POINTS = 12
_INK = "#000000"
_PAPER = "#ffffff"

_PER_MONITOR_DPI_AWARE = 2
_POINTS_PER_INCH = 72
_LOGPIXELSX = 88  # GetDeviceCaps index: the display's horizontal dots per inch


def main() -> None:
    _paint_at_physical_pixel_resolution()
    root = _window()
    status = tk.Label(root, text=READY, font=(_FACE, _POINTS), fg=_INK, bg=_PAPER)
    status.pack(pady=(30, 20))
    tk.Button(
        root,
        text=NEW_TASK,
        font=(_FACE, _POINTS),
        fg=_INK,
        bg=_PAPER,
        padx=16,
        pady=8,
        command=lambda: status.configure(text=TASK_CREATED),
    ).pack()
    root.mainloop()


def _window() -> tk.Tk:
    root = tk.Tk()
    root.title(WINDOW_TITLE)
    root.geometry("460x240")
    root.configure(bg=_PAPER)
    # Kept in front so a screen grab of this window's rectangle contains this
    # window, rather than whatever the developer left on top of it.
    root.attributes("-topmost", True)
    root.tk.call("tk", "scaling", _screen_dots_per_inch() / _POINTS_PER_INCH)
    return root


def _paint_at_physical_pixel_resolution() -> None:
    """Opt out of DPI virtualisation, which is OCR's worst enemy.

    A process that is not DPI-aware gets its window bitmap-stretched by Windows
    on a scaled display. The text the test then reads back is a blurred copy of
    text that was rendered for a smaller screen.
    """
    ctypes.windll.shcore.SetProcessDpiAwareness(_PER_MONITOR_DPI_AWARE)


def _screen_dots_per_inch() -> float:
    device_context = ctypes.windll.user32.GetDC(0)
    try:
        dots_per_inch = ctypes.windll.gdi32.GetDeviceCaps(device_context, _LOGPIXELSX)
    finally:
        ctypes.windll.user32.ReleaseDC(0, device_context)
    return float(dots_per_inch)


if __name__ == "__main__":
    main()
