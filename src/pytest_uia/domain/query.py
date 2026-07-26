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


@dataclass(frozen=True)
class Query:
    """What the test is looking for, in accessibility terms: a role and a name."""

    role: Role
    name: str

    def __str__(self) -> str:
        return f"{self.role.name.capitalize()} '{self.name}'"
