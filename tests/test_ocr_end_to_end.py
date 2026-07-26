"""Behavioral spec for reading a window that has nothing to read in its tree.

Every spec here drives the OCR locator directly, never through the chain, so
what is proven is that the pixels really were recognised — not that some other
link answered first.
"""

from __future__ import annotations

import sys

import pytest

from pytest_uia.application.driver import App
from pytest_uia.domain.errors import ElementNotFound, InputRefused
from pytest_uia.domain.locator import Locator
from pytest_uia.domain.query import Query, Role
from pytest_uia.domain.waiting import RetryPolicy, poll
from tests.conftest import (
    skipped_when_windows_refuses_synthetic_input,
    windows_ocr_is_installed,
)

pytestmark = [
    pytest.mark.gui,
    pytest.mark.skipif(
        sys.platform != "win32",
        reason="Windows' OCR engine is a Windows API",
    ),
    pytest.mark.skipif(
        not windows_ocr_is_installed(),
        reason="install pytest-uia[ocr]",
    ),
]

NEW_TASK_BUTTON = Query(role=Role.BUTTON, name="New Task")
TASK_CREATED_STATUS = Query(role=Role.TEXT, name="task created")
UNPAINTED_BUTTON = Query(role=Role.BUTTON, name="Delete Everything")

# The app repaints on its own message pump, so its reaction lands well after
# the click that caused it has returned — and every look costs a screen grab
# and a recognition pass, which is why the interval is not the domain default.
_REACTION_POLICY = RetryPolicy(timeout=10.0, interval=0.5)


@pytest.fixture
def tk_text(tk_app: App) -> Locator:
    """An OCR locator over the Tk fixture window, and nothing else in the chain.

    The adapter is imported here rather than at module scope because a missing
    `ocr` extra has to skip these specs, and an import at module scope would
    turn it into a collection error that no skipif can prevent.
    """
    from pytest_uia.adapters.ocr import OcrLocator
    from pytest_uia.adapters.uia import resolve_main_window

    return OcrLocator(resolve_main_window(tk_app.pid))


def test_ocr_finds_text_painted_on_a_window_with_no_accessibility_tree(
    tk_text: Locator,
) -> None:
    # When a phrase the Tk app paints, and never names, is looked for
    found = tk_text.find(NEW_TASK_BUTTON)

    # Then it comes back as an element that reads as the phrase on screen
    assert found.read_text() == "New Task", (
        "OCR did not read the button's caption off the window's pixels"
    )


def test_ocr_reports_a_bare_reason_when_the_phrase_is_not_painted_anywhere(
    tk_text: Locator,
) -> None:
    # When a phrase the Tk app paints nowhere is looked for
    with pytest.raises(ElementNotFound) as miss:
        tk_text.find(UNPAINTED_BUTTON)

    # Then the miss reads as a reason rather than as a sentence, because the
    # chain is what puts this locator's name in front of it
    assert str(miss.value) == "phrase not visible", (
        "the chain builds its enriched message out of these fragments"
    )


def test_clicking_text_found_by_ocr_presses_the_underlying_tk_button(
    tk_text: Locator,
) -> None:
    # Given a button located by nothing but the caption painted on it
    button = tk_text.find(NEW_TASK_BUTTON)

    # When it is clicked where those pixels were read — retried while the
    # desktop refuses the pointer, because the adapter is one-shot by contract
    # and waiting is always the caller's job here
    with skipped_when_windows_refuses_synthetic_input():
        poll(button.click, _REACTION_POLICY, retry_on=InputRefused)

    # Then the application acted on it, and repainted its status line to say so
    status = poll(
        lambda: tk_text.find(TASK_CREATED_STATUS),
        _REACTION_POLICY,
        retry_on=ElementNotFound,
    )

    assert status.read_text() == "task created", (
        "the click landed somewhere other than on the button it read"
    )
