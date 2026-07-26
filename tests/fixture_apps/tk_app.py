"""Fixture app: a Tk window that says who its widgets are.

Where it plugs in: launched as a subprocess by `tests/conftest.py`, then driven
from the pytest process through the accessibility tree — the same tree, and the
same adapter, that the WinForms fixture is driven through. `tk_uia.enable()` is
what makes that possible: bare Tk puts every widget in the tree under no name
and mostly the wrong control type, so a query by name and role matches nothing
at all.

Classic `tk` throughout, never `ttk`: measured across all fifteen themed widget
types, each arrives as an anonymous `PaneControl` and `ttk.Button` has no
InvokePattern, so ttk is strictly the worse starting point.

The journey is the WinForms fixture's journey widget for widget — a title box,
a "New Task" trigger, and a status line that becomes "task created" — because
the whole point of the project is that one test body drives both.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass

import tk_uia
from legible import (
    FONT,
    INK,
    PAPER,
    matched_to_this_displays_dpi,
    paint_at_physical_pixel_resolution,
)
from tk_uia import Strategy

WINDOW_TITLE = "pytest-uia Tk Fixture"
NEW_TASK = "New Task"
TITLE = "Title"
READY = "ready"
TASK_CREATED = "task created"

# Chosen by this application rather than derived from a widget path: an id that
# moved whenever the layout was repacked would make every repack a breaking
# change for whoever locates by it.
NEW_TASK_NUMBER = 4207


@dataclass(frozen=True)
class Widgets:
    """The widgets the specs drive, held together while they are wired up."""

    root: tk.Tk
    title_entry: tk.Entry
    draft: tk.StringVar
    new_task: tk.Button
    status: tk.StringVar
    status_label: tk.Label


def main() -> None:
    paint_at_physical_pixel_resolution()
    widgets = _a_window_of_classic_tk_widgets()
    # Realised and mapped before accessibility is switched on. `<Map>` fires
    # once, on the way up, so everything already showing is annotated by
    # `enable()`'s own sweep instead — which is the path any application that
    # builds its window first will take.
    widgets.root.update()

    _accessibility_switched_on(widgets.root)
    _the_things_no_widget_can_say_for_itself(widgets)

    widgets.root.mainloop()


def _a_window_of_classic_tk_widgets() -> Widgets:
    root = tk.Tk()
    root.title(WINDOW_TITLE)
    root.geometry("460x280")
    root.configure(bg=PAPER)
    # Kept in front because both of the driver's fallbacks act on pixels: a
    # control whose provider only pretends to support Invoke is clicked with
    # the real mouse, and OCR photographs whatever is on top.
    root.attributes("-topmost", True)
    matched_to_this_displays_dpi(root)

    status = tk.StringVar(value=READY)
    status_label = tk.Label(root, textvariable=status, font=FONT, fg=INK, bg=PAPER)
    status_label.pack(pady=(30, 20))

    draft = tk.StringVar()
    title_entry = tk.Entry(
        root, textvariable=draft, font=FONT, fg=INK, bg=PAPER, width=28
    )
    title_entry.pack(pady=(0, 20))

    new_task = tk.Button(
        root,
        text=NEW_TASK,
        font=FONT,
        fg=INK,
        bg=PAPER,
        padx=16,
        pady=8,
        command=lambda: status.set(TASK_CREATED),
    )
    new_task.pack()

    return Widgets(
        root=root,
        title_entry=title_entry,
        draft=draft,
        new_task=new_task,
        status=status,
        status_label=status_label,
    )


def _accessibility_switched_on(root: tk.Tk) -> None:
    strategy = tk_uia.enable(root)
    if strategy is not Strategy.ANNOTATED:
        # Loudly, and before the window is worth reading: a version gate that
        # mis-fires leaves every widget exactly as bare Tk left it, and a suite
        # that only asserted "the name is right" would report that as an
        # ordinary miss against the driver.
        raise SystemExit(
            f"tk_uia.enable reported {strategy}, not {Strategy.ANNOTATED}: "
            "nothing in this window has been annotated, so the specs driving "
            "it would be measuring bare Tk"
        )


def _the_things_no_widget_can_say_for_itself(widgets: Widgets) -> None:
    # An entry has no `-text` to be named from, and a name invented from its Tk
    # path would be worse than no name at all, so this is the application's job
    # — exactly as the WinForms fixture sets `AccessibleName` on its own
    # textbox, and for exactly the same reason.
    tk_uia.set_acc_name(widgets.title_entry, TITLE)
    # A name and a value are different properties, and neither follows the
    # widget on its own. Without this the box would announce the name "Title"
    # and an empty value forever, however much was typed into it.
    tk_uia.bind_value_variable(widgets.title_entry, widgets.draft)
    # A label showing a `textvariable` has no `-text` of its own either, and it
    # is the one widget here whose entire job is to report what just happened.
    tk_uia.bind_text_variable(widgets.status_label, widgets.status)
    tk_uia.set_automation_id(widgets.new_task, NEW_TASK_NUMBER)


if __name__ == "__main__":
    main()
