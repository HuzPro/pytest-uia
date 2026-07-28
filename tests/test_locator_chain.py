"""Behavioral spec for the locator fallback chain (Chain of Responsibility).

The chain is the heart of the hybrid strategy: consult the accessibility
tree first, fall back to OCR only when a surface exposes nothing.
"""

from __future__ import annotations

import pytest

from pytest_uia.domain.errors import ElementNotFound
from pytest_uia.domain.locator import Element, LocatorChain
from pytest_uia.domain.query import Query, Role


class StubLocator:
    """Test double: always resolves the query to the element it was given."""

    def __init__(self, element: Element) -> None:
        self._element = element

    def find(self, query: Query) -> Element:
        return self._element


class MissingLocator:
    """Test double: never finds anything, like UIA facing a canvas-drawn window."""

    def find(self, query: Query) -> Element:
        raise ElementNotFound(query)


class CountingLocator:
    """Test double: resolves the query, and remembers being asked to."""

    def __init__(self, element: Element) -> None:
        self.element = element
        self.consultations = 0

    def find(self, query: Query) -> Element:
        self.consultations += 1
        return self.element


class NoAccessibilityTreeLocator:
    """Test double: misses the way UIA does on a canvas-drawn window."""

    def find(self, query: Query) -> Element:
        raise ElementNotFound("no match under window 'Fixture' (pid 1234)")


class NoVisibleTextLocator:
    """Test double: misses the way OCR does when the phrase is not painted."""

    def find(self, query: Query) -> Element:
        raise ElementNotFound("phrase not visible")


NEW_TASK_BUTTON = Query(role=Role.BUTTON, name="New Task")


def test_raises_element_not_found_when_the_chain_has_no_locators() -> None:
    # Given a chain with no locators to consult
    chain = LocatorChain([])

    # When the chain is asked for an element
    with pytest.raises(ElementNotFound) as miss:
        chain.find(NEW_TASK_BUTTON)

    # Then the failure names the query and reports no locator misses at all
    assert str(miss.value) == "Button 'New Task'"


def test_returns_the_element_resolved_by_the_first_locator_that_finds_it() -> None:
    # Given a primary locator that knows the element
    element = object()
    chain = LocatorChain([StubLocator(element)])

    # When the chain is asked for it
    found = chain.find(NEW_TASK_BUTTON)

    # Then the primary locator's answer is returned as-is
    assert found is element


def test_falls_back_to_the_next_locator_when_the_first_cannot_find_the_element() -> (
    None
):
    # Given a primary locator that sees nothing and a fallback that does
    element = object()
    chain = LocatorChain([MissingLocator(), StubLocator(element)])

    # When the chain is asked for the element
    found = chain.find(NEW_TASK_BUTTON)

    # Then the primary locator's miss is absorbed and the fallback answers
    assert found is element


def test_uia_is_consulted_before_ocr_for_windows_with_an_accessibility_tree() -> None:
    # Given a window both locators could answer for: it has a tree, and it is
    # also painted on the screen like everything else
    accessibility_tree = CountingLocator(object())
    reading_the_pixels = CountingLocator(object())
    chain = LocatorChain([accessibility_tree, reading_the_pixels])

    # When an element is asked for
    found = chain.find(NEW_TASK_BUTTON)

    # Then the tree answered it
    assert found is accessibility_tree.element

    # and the screen was never read at all, which is what keeps a query for a
    # button from matching a label that merely says the same words
    assert reading_the_pixels.consultations == 0, (
        "OCR ran for a window that had already answered through its tree: it "
        "is slower, and it is blind to the role the query asked for"
    )


def test_element_not_found_reports_the_query_and_every_locator_that_missed() -> None:
    # Given a chain where every locator misses for its own reason
    chain = LocatorChain([NoAccessibilityTreeLocator(), NoVisibleTextLocator()])

    # When the chain is exhausted
    with pytest.raises(ElementNotFound) as miss:
        chain.find(NEW_TASK_BUTTON)

    # Then the failure names what was sought and what each locator saw instead
    assert str(miss.value) == (
        "Button 'New Task' -- "
        "NoAccessibilityTreeLocator: no match under window 'Fixture' (pid 1234); "
        "NoVisibleTextLocator: phrase not visible"
    ), "the enriched message is the only debugging aid a failing gui test leaves behind"
