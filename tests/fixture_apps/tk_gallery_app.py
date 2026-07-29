"""Fixture app: one of every kind of control a test can ask for, in one window.

`tk_uia.enable(root)` gives each widget its role; explicit `set_acc_name`
calls name the ones with no words of their own. Classic `tk` where both
toolkits have the widget, `ttk` for the four it alone has.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import tk_uia
from legible import (
    FONT,
    INK,
    PAPER,
    matched_to_this_displays_dpi,
    paint_at_physical_pixel_resolution,
)
from tk_uia import Strategy

WINDOW_TITLE = "pytest-uia Gallery Fixture"

NOTIFY_ME = "Notify me"
BY_EMAIL = "By email"
VOLUME = "Volume"
QUANTITY = "Quantity"
# An int, because what tk-uia writes is GWLP_ID, the Win32 control id; UIA
# renders it back as the string '4207'.
QUANTITY_ID = 4207
PRIORITY = "Priority"
SEARCH_RESULTS = "Search results"
TASK_LIST = "Task list"
UPLOAD_PROGRESS = "Upload progress"
SCROLL_THE_RESULTS = "Scroll the results"
DETAILS = "Details"
SPARKLINE = "Activity sparkline"
ACTIONS = "Actions"
DIVIDER = "Divider"
RESIZE = "Resize this window"
SETTINGS = "Settings"
FIRST_TAB = "General"


def main() -> None:
    paint_at_physical_pixel_resolution()
    root, to_be_named = _a_window_of_every_kind_of_control()
    # In this order, and it is the order every application has to use: there is
    # nothing to annotate *through* until `enable()` has installed, and the
    # sweep it runs annotates whatever is already on screen.
    _accessibility_switched_on(root)
    for name, widget in to_be_named.items():
        tk_uia.set_acc_name(widget, name)
    # One deliberately set automation id, standing in for a WPF x:Name or a
    # web page's DOM id: the only kind worth querying by.
    tk_uia.set_automation_id(to_be_named[QUANTITY], QUANTITY_ID)
    root.mainloop()


def _a_window_of_every_kind_of_control() -> tuple[tk.Tk, dict[str, tk.Misc]]:
    root = tk.Tk()
    root.title(WINDOW_TITLE)
    root.configure(bg=PAPER)
    matched_to_this_displays_dpi(root)
    # No fixed geometry, deliberately: it makes the Tk packer drop whatever will
    # not fit, and a widget Tk never maps is never annotated.
    root.attributes("-topmost", True)

    _the_widgets_that_carry_their_own_words(root)
    return root, _the_widgets_an_application_has_to_name(root)


def _the_widgets_that_carry_their_own_words(root: tk.Tk) -> None:
    tk.Checkbutton(
        root,
        text=NOTIFY_ME,
        bg=PAPER,
        fg=INK,
        font=FONT,
        variable=tk.IntVar(master=root),
    ).pack(anchor="w", padx=12, pady=4)
    tk.Radiobutton(
        root,
        text=BY_EMAIL,
        value=1,
        variable=tk.IntVar(master=root, value=1),
        bg=PAPER,
        fg=INK,
        font=FONT,
    ).pack(anchor="w", padx=12, pady=4)
    # A Scale keeps its caption in `-label`, not `-text`: the one widget in the
    # toolkit built that way, and tk-uia infers a name from it.
    tk.Scale(
        root,
        from_=0,
        to=10,
        orient="horizontal",
        label=VOLUME,
        bg=PAPER,
        fg=INK,
        font=FONT,
    ).pack(fill="x", padx=12, pady=4)
    menubutton = tk.Menubutton(
        root, text=ACTIONS, relief="raised", bg=PAPER, fg=INK, font=FONT
    )
    menu = tk.Menu(menubutton, tearoff=False)
    menu.add_command(label="Archive")
    menubutton.configure(menu=menu)
    menubutton.pack(anchor="w", padx=12, pady=4)


def _the_widgets_an_application_has_to_name(root: tk.Tk) -> dict[str, tk.Misc]:
    """Everything with no words of its own, and the name it needs.

    Returned rather than named here: `set_acc_name` has nothing to write
    through until `enable()` has run, and `enable()` wants the widgets built.
    """
    spinbox = tk.Spinbox(root, from_=0, to=10, font=FONT)
    spinbox.pack(fill="x", padx=12, pady=4)

    combobox = ttk.Combobox(root, values=["high", "low"])
    combobox.pack(fill="x", padx=12, pady=4)

    listbox = tk.Listbox(root, height=3, font=FONT)
    for row in ("first", "second"):
        listbox.insert("end", row)
    listbox.pack(fill="x", padx=12, pady=4)

    tree = ttk.Treeview(root, height=3)
    tree.insert("", "end", text="a row")
    tree.pack(fill="x", padx=12, pady=4)

    progressbar = ttk.Progressbar(root, value=40)
    progressbar.pack(fill="x", padx=12, pady=4)

    scrollbar = tk.Scrollbar(root, orient="vertical")
    scrollbar.pack(side="right", fill="y")

    group = tk.Frame(root, bg=PAPER, borderwidth=2, relief="groove")
    tk.Label(group, text="inside", bg=PAPER, fg=INK, font=FONT).pack(padx=8, pady=8)
    group.pack(fill="x", padx=12, pady=4)

    canvas = tk.Canvas(root, width=160, height=40, bg="white")
    canvas.create_text(80, 20, text="painted words")
    canvas.pack(padx=12, pady=4)

    separator = ttk.Separator(root, orient="horizontal")
    separator.pack(fill="x", padx=12, pady=4)

    sizegrip = ttk.Sizegrip(root)
    sizegrip.pack(anchor="e", padx=12, pady=4)

    notebook = ttk.Notebook(root)
    page = ttk.Frame(notebook)
    ttk.Label(page, text="a page").pack(padx=10, pady=10)
    notebook.add(page, text=FIRST_TAB)
    notebook.pack(fill="x", padx=12, pady=4)

    return {
        QUANTITY: spinbox,
        PRIORITY: combobox,
        SEARCH_RESULTS: listbox,
        TASK_LIST: tree,
        UPLOAD_PROGRESS: progressbar,
        SCROLL_THE_RESULTS: scrollbar,
        DETAILS: group,
        SPARKLINE: canvas,
        # A real application leaves a decorative separator unnamed; this one
        # names it so the spec can prove the query reaches it.
        DIVIDER: separator,
        RESIZE: sizegrip,
        SETTINGS: notebook,
    }


def _accessibility_switched_on(root: tk.Tk) -> None:
    # Only UNSUPPORTED leaves the gallery bare; every other strategy puts
    # its controls in the tree, which is all these specs need.
    strategy = tk_uia.enable(root)
    if strategy is Strategy.UNSUPPORTED:
        raise SystemExit(
            f"tk_uia.enable reported {strategy}: "
            "none of the gallery's controls would be in the tree"
        )


if __name__ == "__main__":
    main()
