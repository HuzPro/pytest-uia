"""Fixture app: a Tk window whose pages are behind a notebook.

Where it plugs in: launched as a subprocess by `tests/conftest.py`, then driven
through the accessibility tree like every other fixture here. It exists for one
control the others do not have — a `ttk.Notebook` — because a notebook is the
one widget that can hide the rest of an application from a test.

`ttk` here, deliberately, where `tk_app.py` is classic `tk` throughout and says
why. There is no classic Tk notebook, and a tabbed settings window is the shape
this matters for: whichever page is open is the only one Tk maps, so a test that
cannot change tabs can only ever see one of them. The pages hold classic `tk`
widgets, so what is *on* a page is as reachable as anywhere else.

Each page carries a label naming it, and nothing else, because the assertion is
about which page is showing rather than about what is on it.
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

WINDOW_TITLE = "pytest-uia Notebook Fixture"

GENERAL = "General"
DATABASE = "Database"
ABOUT = "About"
TABS = (GENERAL, DATABASE, ABOUT)


def what_the_page_says(tab: str) -> str:
    """The label on one page, which only that page has while it is showing."""
    return f"{tab} page"


def main() -> None:
    paint_at_physical_pixel_resolution()
    root = _a_window_of_tabbed_pages()
    _accessibility_switched_on(root)
    root.mainloop()


def _a_window_of_tabbed_pages() -> tk.Tk:
    root = tk.Tk()
    root.title(WINDOW_TITLE)
    root.configure(bg=PAPER)
    matched_to_this_displays_dpi(root)
    # Nothing here is measured by size, so the window is left to ask for the
    # room it needs: a fixed geometry makes the Tk packer silently drop
    # whatever will not fit, and an unmapped widget is never annotated.
    root.attributes("-topmost", True)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=12, pady=12)
    for tab in TABS:
        page = tk.Frame(notebook, bg=PAPER)
        tk.Label(page, text=what_the_page_says(tab), bg=PAPER, fg=INK, font=FONT).pack(
            padx=24, pady=24
        )
        notebook.add(page, text=tab)
    return root


def _accessibility_switched_on(root: tk.Tk) -> None:
    strategy = tk_uia.enable(root)
    if strategy is not Strategy.ANNOTATED:
        # Loudly, and before the window is driven: a mis-fired gate would fail
        # every spec with "no such tab", which is true and explains nothing.
        raise SystemExit(
            f"tk_uia.enable reported {strategy}, not {Strategy.ANNOTATED}: "
            "the notebook's tabs would not be in the tree at all"
        )


if __name__ == "__main__":
    main()
