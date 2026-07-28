"""What a test is looking for, expressed in accessibility terms.

Locators consume a Query; each adapter maps Role onto its own vocabulary (UIA
control types, or nothing at all in OCR's case, which can only see text).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class Role(Enum):
    """The kinds of element a test can ask for. Grows only as a cycle demands it."""

    BUTTON = auto()
    TEXT = auto()
    TEXTBOX = auto()
    TAB = auto()
    # Each role is one control type, named the way somebody writing a test
    # would say it rather than the way UI Automation spells it.
    CHECKBOX = auto()
    RADIO = auto()
    SLIDER = auto()
    SPINBOX = auto()
    COMBOBOX = auto()
    LISTBOX = auto()
    TREE = auto()
    PROGRESSBAR = auto()
    SCROLLBAR = auto()
    GROUP = auto()
    IMAGE = auto()
    # UI Automation's own words for the three that have no everyday name. A
    # `tk.Menubutton` is a split button, a `ttk.Sizegrip` is a thumb, and a
    # notebook's strip is a tab control; naming them after the Tk widget would
    # be this plugin, which drives WinForms and WPF too, speaking one toolkit.
    SPLIT_BUTTON = auto()
    SEPARATOR = auto()
    THUMB = auto()
    TAB_STRIP = auto()


@dataclass(frozen=True)
class Query:
    """What the test is looking for, in accessibility terms: a role and a name."""

    role: Role
    name: str

    def __str__(self) -> str:
        return f"{self.role.name.capitalize()} '{self.name}'"
