"""Behavioral spec for the locator fallback chain (Chain of Responsibility).

The chain is the heart of the hybrid strategy: consult the accessibility
tree first, fall back to OCR only when a surface exposes nothing. Scoping a
query inside an element another query finds is a Decorator over the same
seam, so it is specified here too.
"""

from __future__ import annotations

import pytest

from pytest_uia.domain.errors import ElementNotFound
from pytest_uia.domain.locator import Element, LocatorChain, ScopedLocator
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


class ContainerWithContents:
    """Test double: an element whose inside is searchable, like a named row."""

    def __init__(self, contents: object) -> None:
        self._contents = contents

    def contents(self) -> object:
        return self._contents


THE_ROW = Query(role=Role.GROUP, name="record 23256")
THE_DURATION = Query(role=Role.TEXT, name="1m 8s")


def test_a_scoped_query_is_answered_from_inside_the_element_enclosing_it() -> None:
    # Given a window holding a named row, and a duration inside that row
    duration = object()
    row = ContainerWithContents(StubLocator(duration))
    scoped = ScopedLocator(StubLocator(row), THE_ROW)

    # When the duration is asked for through the scope
    found = scoped.find(THE_DURATION)

    # Then it was answered from the row's own inside, so the same words
    # painted twenty rows further down can never answer instead
    assert found is duration


def test_a_scoped_query_misses_when_the_enclosing_element_is_missing() -> None:
    # Given a scope whose enclosing element is not on screen
    scoped = ScopedLocator(MissingLocator(), THE_ROW)

    # When something inside it is asked for
    with pytest.raises(ElementNotFound) as miss:
        scoped.find(THE_DURATION)

    # Then the failure blames the enclosure, not the thing inside it: whoever
    # reads it needs to know which of the two names to go looking for
    assert "record 23256" in str(miss.value), (
        f"the missing ancestor is the first suspect and has to be named: {miss.value}"
    )


def test_a_scoped_query_misses_when_nothing_inside_the_element_matches() -> None:
    # Given a row that is on screen with nothing matching inside it
    row = ContainerWithContents(MissingLocator())
    scoped = ScopedLocator(StubLocator(row), THE_ROW)

    # When the absent thing is asked for through the scope
    with pytest.raises(ElementNotFound) as miss:
        scoped.find(THE_DURATION)

    # Then the failure says the search happened inside the enclosure, because
    # "not found" alone reads as "not in the window", which is not what was
    # looked at
    assert "inside" in str(miss.value) and "record 23256" in str(miss.value), (
        f"a scoped miss has to say where it looked: {miss.value}"
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
