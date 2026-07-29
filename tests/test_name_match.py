"""Behavioral spec for name matching: how a query decides a name is the one.

Exact is the default and stays the default; `containing` and `matching` are
what a test reaches for when an application decorates its captions ("Inbox
(3)") faster than an exact name can keep up.
"""

from __future__ import annotations

import pytest

from pytest_uia import by_id, containing, matching
from pytest_uia.domain.name_match import Exactly
from pytest_uia.domain.query import Query, Role


class TestExactMatching:
    def test_matches_only_the_identical_name(self) -> None:
        # Given the default matcher a plain string becomes
        matcher = Exactly("New Task")

        # Then it accepts the name itself and nothing around it
        assert matcher.matches("New Task")
        assert not matcher.matches("New Task (3)")
        assert not matcher.matches("new task")

    def test_a_query_built_from_a_string_still_renders_as_before(self) -> None:
        # Given a query spelled the way every existing test spells one
        query = Query(role=Role.BUTTON, name="New Task")

        # Then the failure rendering is unchanged
        assert str(query) == "Button 'New Task'"


class TestSubstringMatching:
    def test_matches_a_name_the_fragment_appears_in(self) -> None:
        assert containing("Inbox").matches("Inbox (3)")

    def test_misses_a_name_the_fragment_is_absent_from(self) -> None:
        assert not containing("Inbox").matches("Outbox (3)")

    def test_is_case_sensitive_like_the_exact_match_it_loosens(self) -> None:
        assert not containing("inbox").matches("Inbox (3)")

    def test_renders_as_the_call_that_built_it(self) -> None:
        query = Query(role=Role.TEXT, name=containing("Inbox"))

        assert str(query) == "Text containing('Inbox')"


class TestQueryingByAutomationId:
    def test_renders_as_the_call_that_built_it(self) -> None:
        query = Query(role=Role.TEXTBOX, name=by_id("date-time-edit"))

        assert str(query) == "Textbox by_id('date-time-edit')"

    def test_two_queries_for_the_same_id_are_the_same_query(self) -> None:
        # Equality is what lets a spec assert on the query a locator was asked
        assert by_id("picker") == by_id("picker")
        assert by_id("picker") != by_id("root")


class TestRegexMatching:
    def test_matches_a_name_the_whole_pattern_covers(self) -> None:
        assert matching(r"Inbox \(\d+\)").matches("Inbox (12)")

    def test_misses_a_name_the_pattern_covers_only_part_of(self) -> None:
        # Full match, not search: a pattern that means "anywhere inside" can
        # say so itself with .* at either end
        assert not matching(r"Inbox \(\d+\)").matches("My Inbox (12) folder")

    def test_an_invalid_pattern_fails_at_the_call_site(self) -> None:
        # At construction, where the typo is, not at resolution time inside a
        # retry loop that would repeat the error once per poll
        with pytest.raises(ValueError):
            matching(r"Inbox (")

    def test_renders_as_the_call_that_built_it(self) -> None:
        query = Query(role=Role.TEXT, name=matching(r"Inbox \(\d+\)"))

        assert str(query) == r"Text matching('Inbox \(\d+\)')"
