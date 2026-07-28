"""How a query becomes an element, and what happens when it cannot.

This is the seam the whole hybrid strategy hangs on: adapters (UIA, OCR) implement
Locator, and LocatorChain decides the order they are consulted in. Nothing here
knows that Windows exists.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pytest_uia.domain.errors import ElementNotFound
from pytest_uia.domain.query import Query

_QUERY_FROM_MISSES = " -- "
_BETWEEN_MISSES = "; "


class Element(Protocol):
    """Something on screen a test can act on, however it was located."""

    def click(self) -> None: ...

    def type_text(self, text: str) -> None: ...

    def read_text(self) -> str: ...

    def is_visible(self) -> bool: ...


class Locator(Protocol):
    """Strategy for turning a query into an element.

    Implementations MUST be one-shot: look once, raise ElementNotFound, and let
    the caller decide about waiting. A locator that retries internally would
    multiply with the domain's own polling and blow the configured timeout.
    """

    def find(self, query: Query) -> Element: ...


class LocatorChain:
    """Chain of Responsibility over element locators.

    Locators are consulted in order; the first one that resolves the query wins.
    Satisfies Locator itself, so a chain can be nested inside another chain.
    """

    def __init__(self, locators: Sequence[Locator]) -> None:
        self._locators = locators

    def find(self, query: Query) -> Element:
        misses: list[str] = []
        for locator in self._locators:
            try:
                return locator.find(query)
            except ElementNotFound as miss:
                misses.append(f"{type(locator).__name__}: {miss}")
        raise ElementNotFound(_miss_report(query, misses))


def _miss_report(query: Query, misses: Sequence[str]) -> str:
    # A failing gui test usually leaves nothing behind but this string, so it has
    # to name both what was sought and what every locator saw instead of it.
    if not misses:
        return str(query)
    return f"{query}{_QUERY_FROM_MISSES}{_BETWEEN_MISSES.join(misses)}"
