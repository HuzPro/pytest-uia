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

On top of that it opens a modal `Toplevel`, which the WinForms fixture does not,
because that is the shape a first-run wizard has: a dialog whose Confirm carries
the same accessible name as a Confirm on the window underneath it. Two controls
answering one query is what makes "which window did you mean" a question at all.
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

OPEN_SETTINGS = "Open Settings"
SETTINGS = "Settings"
FOLDER = "Folder"
# Deliberately on both windows. A wizard reuses its captions from step to step —
# Next, Back, OK — and this is the smallest honest version of that collision.
CONFIRM = "Confirm"
MAIN_CONFIRMED = "main confirmed"
SETTINGS_SAVED = "settings saved"

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
    root.geometry("460x420")
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

    # Neither of these is held in Widgets: nothing further is done to them, and a
    # field nobody reads is a claim that something reads it.
    tk.Button(
        root,
        text=OPEN_SETTINGS,
        font=FONT,
        fg=INK,
        bg=PAPER,
        padx=16,
        pady=8,
        command=lambda: _a_modal_settings_dialog(root, status),
    ).pack(pady=(20, 0))

    tk.Button(
        root,
        text=CONFIRM,
        font=FONT,
        fg=INK,
        bg=PAPER,
        padx=16,
        pady=8,
        command=lambda: status.set(MAIN_CONFIRMED),
    ).pack(pady=(20, 0))

    return Widgets(
        root=root,
        title_entry=title_entry,
        draft=draft,
        new_task=new_task,
        status=status,
        status_label=status_label,
    )


def _a_modal_settings_dialog(root: tk.Tk, status: tk.StringVar) -> None:
    """Open the first-run wizard's one step: a Toplevel that owns the keyboard.

    `transient` plus `grab_set` is what makes this a dialog rather than a second
    window, and it is the shape the driver has to cope with — Tk owns the window
    at the Win32 level, so UI Automation nests it inside its owner's subtree and
    a search that starts at the main window reaches straight into it.
    """
    dialog = tk.Toplevel(root)
    dialog.title(SETTINGS)
    dialog.geometry("340x220")
    dialog.configure(bg=PAPER)
    # Kept in front for the same reason the main window is: both of the driver's
    # fallbacks act on pixels.
    dialog.attributes("-topmost", True)
    dialog.transient(root)

    chosen_folder = tk.StringVar()
    folder_entry = tk.Entry(
        dialog, textvariable=chosen_folder, font=FONT, fg=INK, bg=PAPER, width=24
    )
    folder_entry.pack(pady=(40, 25))

    tk.Button(
        dialog,
        text=CONFIRM,
        font=FONT,
        fg=INK,
        bg=PAPER,
        padx=16,
        pady=8,
        command=lambda: _saved_and_dismissed(dialog, status),
    ).pack()

    # The same two calls the main window's entry needs, for the same two reasons:
    # an entry carries no words to be named from, and its value does not follow
    # the widget on its own. Everything else in here is annotated by the `<Map>`
    # binding `enable()` left on the `all` bindtag, which a Toplevel built long
    # after that call still fires.
    tk_uia.set_acc_name(folder_entry, FOLDER)
    tk_uia.bind_value_variable(folder_entry, chosen_folder)

    # Modal only once it is built: a grab taken over a half-drawn window is one
    # the user cannot use and the driver cannot read.
    dialog.grab_set()


def _saved_and_dismissed(dialog: tk.Toplevel, status: tk.StringVar) -> None:
    # The outcome is announced on the *main* window on purpose: a wizard step
    # that saved something is only proven by what outlives the dialog.
    status.set(SETTINGS_SAVED)
    dialog.destroy()


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
