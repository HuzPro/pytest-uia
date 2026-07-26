"""Fixture app: a Tk window that paints an interface and names none of it.

Where it plugs in: launched as a subprocess by `tests/conftest.py`, and driven
by every spec that has to prove the pixel path still carries a window on its
own. Everything visible here is drawn on one `tk.Canvas` with `create_text`,
which the accessibility tree serves as a single anonymous pane with **zero**
children — measured, not assumed. There is nothing in it for a query by name
and role to match, which is exactly the case OCR exists for.

`tk_uia` is deliberately never imported. Its sibling `tk_app.py` is the window
that says who its widgets are; this is the window that says nothing, and the
two are only worth having as a pair.

The words are the WinForms and Tk fixtures' words, so the specs that read them
back need no vocabulary of their own.
"""

from __future__ import annotations

import tkinter as tk

from legible import (
    FONT,
    INK,
    PAPER,
    matched_to_this_displays_dpi,
    paint_at_physical_pixel_resolution,
)

WINDOW_TITLE = "pytest-uia Canvas Fixture"
NEW_TASK = "New Task"
READY = "ready"
TASK_CREATED = "task created"

_WIDTH = 460
_HEIGHT = 280
_CENTRE_X = _WIDTH // 2
_STATUS_Y = 70
_BUTTON_Y = 180
_BUTTON_HALF_WIDTH = 70
_BUTTON_HALF_HEIGHT = 24

# One tag over the drawn button's outline and its caption together, so a click
# anywhere in the shape reaches the handler. OCR aims at the centre of the
# phrase it read, which for two words falls in the space between them.
_THE_BUTTON = "new-task"

_A_LEFT_CLICK = "<Button-1>"


def main() -> None:
    paint_at_physical_pixel_resolution()
    root = _a_window_that_is_only_paint()
    canvas = _a_canvas_filling_it(root)
    status = _the_status_line_drawn_on(canvas)
    _the_button_drawn_on(canvas)
    _clicking_the_drawn_button_reports_a_task(canvas, status)

    root.mainloop()


def _a_window_that_is_only_paint() -> tk.Tk:
    root = tk.Tk()
    root.title(WINDOW_TITLE)
    root.geometry(f"{_WIDTH}x{_HEIGHT}")
    root.configure(bg=PAPER)
    # Kept in front because everything here is reached by photographing the
    # screen and then clicking what was recognised, and both act on whatever
    # happens to be on top.
    root.attributes("-topmost", True)
    matched_to_this_displays_dpi(root)
    return root


def _a_canvas_filling_it(root: tk.Tk) -> tk.Canvas:
    canvas = tk.Canvas(
        root, width=_WIDTH, height=_HEIGHT, bg=PAPER, highlightthickness=0
    )
    canvas.pack(fill=tk.BOTH, expand=True)
    return canvas


def _the_status_line_drawn_on(canvas: tk.Canvas) -> int:
    return canvas.create_text(_CENTRE_X, _STATUS_Y, text=READY, font=FONT, fill=INK)


def _the_button_drawn_on(canvas: tk.Canvas) -> None:
    canvas.create_rectangle(
        _CENTRE_X - _BUTTON_HALF_WIDTH,
        _BUTTON_Y - _BUTTON_HALF_HEIGHT,
        _CENTRE_X + _BUTTON_HALF_WIDTH,
        _BUTTON_Y + _BUTTON_HALF_HEIGHT,
        outline=INK,
        fill=PAPER,
        tags=_THE_BUTTON,
    )
    canvas.create_text(
        _CENTRE_X, _BUTTON_Y, text=NEW_TASK, font=FONT, fill=INK, tags=_THE_BUTTON
    )


def _clicking_the_drawn_button_reports_a_task(canvas: tk.Canvas, status: int) -> None:
    # A canvas item is not a widget and has no command; a binding on the tag is
    # the whole of what makes these pixels behave like a button.
    def report_a_task(_event: tk.Event) -> None:
        canvas.itemconfigure(status, text=TASK_CREATED)

    canvas.tag_bind(_THE_BUTTON, _A_LEFT_CLICK, report_a_task)


if __name__ == "__main__":
    main()
