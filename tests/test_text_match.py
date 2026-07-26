"""Behavioral spec for finding a phrase among the words an OCR pass reported.

Pure domain: the words here could have come from any engine, and no screen is
involved. What is under test is the matching, never the recognising.
"""

from __future__ import annotations

from pytest_uia.domain.text_match import Box, Word, find_phrase


def test_finds_the_box_of_a_single_word_equal_to_the_query_text() -> None:
    # Given one recognised word, alone on its line
    new = Word(text="New", box=Box(left=10, top=20, width=30, height=12), line=0)

    # When exactly that text is looked for
    found = find_phrase([new], "New")

    # Then the box that comes back is the region the word occupies
    assert found == Box(left=10, top=20, width=30, height=12)


def test_matches_a_multi_word_phrase_spanning_adjacent_words_on_one_line() -> None:
    # Given two words painted side by side on one line
    new = Word(text="New", box=Box(left=10, top=20, width=30, height=12), line=0)
    task = Word(text="Task", box=Box(left=45, top=20, width=40, height=12), line=0)

    # When the phrase the two of them spell is looked for
    found = find_phrase([new, task], "New Task")

    # Then the box that comes back is the one region covering both words
    assert found == Box(left=10, top=20, width=75, height=12), (
        "a click aimed between the words has to land inside the phrase"
    )


def test_matching_ignores_case_and_collapses_runs_of_whitespace() -> None:
    # Given words carrying the capitalisation the application chose to paint
    new = Word(text="NEW", box=Box(left=10, top=20, width=30, height=12), line=0)
    task = Word(text="Task", box=Box(left=45, top=20, width=40, height=12), line=0)

    # When the phrase is asked for the way somebody would casually type it
    found = find_phrase([new, task], "  new   task ")

    # Then it still matches, and still reports the region both words cover
    assert found == Box(left=10, top=20, width=75, height=12), (
        "a test should not have to reproduce a label's capitalisation or spacing"
    )


def test_returns_none_when_no_line_contains_the_phrase() -> None:
    # Given a window where the two words are painted, but one line apart
    new = Word(text="New", box=Box(left=10, top=20, width=30, height=12), line=0)
    task = Word(text="Task", box=Box(left=10, top=40, width=40, height=12), line=1)

    # When the phrase they would spell if they were adjacent is looked for
    found = find_phrase([new, task], "New Task")

    # Then nothing matches, because no single line reads that way
    assert found is None, (
        "a box spanning two lines would put the click point in the gap between "
        "them, on whatever happens to be there"
    )
