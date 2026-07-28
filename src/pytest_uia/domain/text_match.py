"""Finding a phrase among words an OCR pass reported, and where it sits.

The pure half of the OCR fallback. `adapters/ocr.py` recognises pixels into
`Word`s and turns the `Box` this returns into a click point; the matching
itself lives here, with no screen anywhere near it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Box:
    """A rectangle in the coordinate space of whatever image was recognised."""

    left: float
    top: float
    width: float
    height: float


@dataclass(frozen=True)
class Word:
    """One recognised word: its text, where it is, and which line it belongs to."""

    text: str
    box: Box
    line: int


def find_phrase(words: Sequence[Word], phrase: str) -> Box | None:
    wanted = _spoken_words_of(phrase)
    for start in range(len(words) - len(wanted) + 1):
        run = words[start : start + len(wanted)]
        if _reads_as(run, wanted) and _sits_on_one_line(run):
            return _union([word.box for word in run])
    return None


def _reads_as(run: Sequence[Word], wanted: Sequence[str]) -> bool:
    return [_comparable(word.text) for word in run] == list(wanted)


def _sits_on_one_line(run: Sequence[Word]) -> bool:
    # The last word of one line and the first of the next spell anything you
    # like. Their union box covers the gap between the lines, so a click on its
    # centre lands on whatever sits there instead.
    return len({word.line for word in run}) == 1


def _spoken_words_of(phrase: str) -> list[str]:
    # OCR reports what a label was painted as; a test says what it means.
    # Neither capitalisation nor the spacing between words is a difference
    # anybody writing an acceptance test intends to assert on.
    return [_comparable(part) for part in phrase.split()]


def _comparable(text: str) -> str:
    return text.casefold()


def _union(boxes: Sequence[Box]) -> Box:
    left = min(box.left for box in boxes)
    top = min(box.top for box in boxes)
    right = max(box.left + box.width for box in boxes)
    bottom = max(box.top + box.height for box in boxes)
    return Box(left=left, top=top, width=right - left, height=bottom - top)
