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
    # A notebook's tab. Added in 0.6.0 rather than at v1, and the distinction
    # matters: this is not the locator being widened to accept a control type
    # it used to reject. Tk's tabs were painted rather than exposed, so there
    # was nothing in the tree to name — `tk-uia` 0.4.0 gives each one a window
    # handle of its own, and a role that had nothing to match now has.
    TAB = auto()


@dataclass(frozen=True)
class Query:
    """What the test is looking for, in accessibility terms: a role and a name."""

    role: Role
    name: str

    def __str__(self) -> str:
        return f"{self.role.name.capitalize()} '{self.name}'"
