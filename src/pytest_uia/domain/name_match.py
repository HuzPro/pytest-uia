"""How a query decides an accessible name is the one it means.

`Exactly` is what a plain string becomes and behaves as every query always
has; `containing` and `matching` are the loosenings a test asks for by name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol


class NameMatch(Protocol):
    """Whether an accessible name is the one a query means."""

    def matches(self, name: str) -> bool: ...


@dataclass(frozen=True)
class Exactly:
    """The whole name, case and all."""

    text: str

    def matches(self, name: str) -> bool:
        return name == self.text

    def __str__(self) -> str:
        return f"'{self.text}'"


@dataclass(frozen=True)
class Containing:
    """Any name the fragment appears in: 'Inbox' accepts 'Inbox (3)'."""

    fragment: str

    def matches(self, name: str) -> bool:
        return self.fragment in name

    def __str__(self) -> str:
        return f"containing('{self.fragment}')"


@dataclass(frozen=True)
class Matching:
    """Any name the whole pattern covers; anchor-free searching is spelled .*"""

    pattern: str
    _compiled: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Compiled here so a typo fails at the call site, not once per poll
        # inside the implicit wait.
        try:
            compiled = re.compile(self.pattern)
        except re.error as invalid:
            raise ValueError(f"not a usable pattern: {invalid}") from invalid
        object.__setattr__(self, "_compiled", compiled)

    def matches(self, name: str) -> bool:
        return self._compiled.fullmatch(name) is not None

    def __str__(self) -> str:
        return f"matching('{self.pattern}')"


@dataclass(frozen=True)
class ById:
    """The control whose AutomationId this is, wherever one is set deliberately."""

    id: str

    def __str__(self) -> str:
        return f"by_id('{self.id}')"


def containing(fragment: str) -> Containing:
    """A name matcher satisfied by any name the fragment appears in."""
    return Containing(fragment)


def matching(pattern: str) -> Matching:
    """A name matcher satisfied by any name the whole pattern covers."""
    return Matching(pattern)


def by_id(automation_id: str) -> ById:
    """Address a control by its AutomationId instead of its name.

    Worth using only where an application sets one deliberately (WPF `x:Name`,
    a web page's DOM id, `tk_uia.set_automation_id`): WinForms derives ids
    from window handles, differently on every launch.
    """
    return ById(automation_id)
