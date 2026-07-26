"""The pitch, executed — and the proof of which half of it did the work.

Where it plugs in: the whole chain, over the fixture apps, end to end. Two of
them expose an accessibility tree and one exposes nothing but paint, and the
same journey drives all three without being told which is which.

What this file now also exists to stop is a spec that passes while proving
nothing. The chain returns the first answer, so the moment `tk_uia` made the Tk
fixture accessible its pixel link stopped being consulted at all — and the one
spec that used to live here, which asserted only that the journey passed, went
on passing under a parameter id reading `tkinter-through-ocr` that had become a
lie. **Passing is no longer the evidence. Which link answered is**, so the
pixel link is wrapped in something that remembers being asked.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass

import pytest

from pytest_uia.adapters.uia import UiaLocator, resolve_main_window
from pytest_uia.application.driver import App, UIElement
from pytest_uia.application.session import GuiSession
from pytest_uia.domain.locator import Element, Locator, LocatorChain
from pytest_uia.domain.query import Query, Role
from tests.conftest import (
    skipped_when_windows_refuses_synthetic_input,
    tk_canvas_command,
    tk_command,
    tk_uia_is_installed,
    windows_ocr_is_installed,
    winforms_command,
)

pytestmark = [
    pytest.mark.gui,
    pytest.mark.skipif(
        sys.platform != "win32",
        reason="both locators are Windows APIs",
    ),
    pytest.mark.skipif(
        not windows_ocr_is_installed(),
        # Both specs need the extra installed, including the one that proves
        # the pixels are never read: the double wraps a real OCR locator, and
        # there is no importing that without it.
        reason="install pytest-uia[ocr]",
    ),
]

NEW_TASK_BUTTON = Query(role=Role.BUTTON, name="New Task")
TASK_CREATED_TEXT = Query(role=Role.TEXT, name="task created")

_NEEDS_THE_ANNOTATOR = pytest.mark.skipif(
    not tk_uia_is_installed(),
    reason="install tk-uia: the Tk fixture app annotates itself with it",
)


class CountingLocator:
    """Test double: a locator that remembers being asked.

    A Decorator over the real locator rather than a stand-in for it. The
    question is which link answered, and a chain whose last link is a stub
    would answer a different one — the journey has to be able to succeed
    through the pixels for `asked == 0` to mean anything at all.
    """

    def __init__(self, inner: Locator) -> None:
        self._inner = inner
        self.asked = 0

    def find(self, query: Query) -> Element:
        self.asked += 1
        return self._inner.find(query)


@dataclass(frozen=True)
class WatchedChain:
    """A window's locator chain, and the pixel link's memory of being asked."""

    contents: Locator
    pixels: CountingLocator


@pytest.mark.parametrize(
    "launch_command",
    [
        pytest.param(winforms_command, id="winforms"),
        pytest.param(tk_command, id="tkinter", marks=_NEEDS_THE_ANNOTATOR),
    ],
)
def test_the_accessibility_tree_answers_for_every_window_that_has_one_and_the_pixels_are_never_read(
    gui: GuiSession,
    launch_command: Callable[[], list[str]],
) -> None:
    # Given the full chain over a window whose contents are in the tree
    watched = _a_chain_whose_pixel_link_counts(gui.launch(launch_command()))

    # When the journey the README promises is driven through it
    reacted = _the_journey_the_readme_promises(watched)

    # Then it ran, and it ran on the accessibility tree alone
    assert reacted, (
        "the journey that passes against one window with an accessibility "
        "tree has to pass against every window that has one, unchanged"
    )
    assert watched.pixels.asked == 0, (
        f"the pixels were read {watched.pixels.asked} time(s) for a window "
        "whose accessibility tree could answer everything it was asked"
    )


def test_pixels_answer_for_the_one_window_whose_contents_have_no_accessibility_tree(
    gui: GuiSession,
) -> None:
    # Given the same chain over the window that is nothing but paint
    watched = _a_chain_whose_pixel_link_counts(gui.launch(tk_canvas_command()))

    # When the very same journey is driven through it
    reacted = _the_journey_the_readme_promises(watched)

    # Then it ran on the fallback, because there was nothing else to run on
    assert reacted, (
        "the journey has to survive a window that exposes no tree at all, "
        "which is the whole reason the pixel path is still in the chain"
    )
    assert watched.pixels.asked > 0, (
        "the chain answered without ever reading the pixels, so either this "
        "window has become accessible or the fallback is not wired in"
    )


def _the_journey_the_readme_promises(watched: WatchedChain) -> bool:
    """Press New Task, then say whether the window admitted to it."""
    # The driver already retries a refused click for the whole implicit wait.
    # Only a desktop that refuses for all of it reaches here, and that is a
    # machine that cannot run this spec rather than a product that is broken.
    with skipped_when_windows_refuses_synthetic_input():
        UIElement(NEW_TASK_BUTTON, watched.contents).click()
    return UIElement(TASK_CREATED_TEXT, watched.contents).exists()


def _a_chain_whose_pixel_link_counts(app: App) -> WatchedChain:
    """The chain a window builds for itself, with a witness on its last link.

    Deliberately assembled here rather than taken from the App the session
    hands back: that one is already built, and it offers no seam to slip a
    double into — which is exactly the property that let the old spec go
    vacuous without anybody noticing.
    """
    # Imported inside the helper because the `ocr` extra may be absent, and a
    # module-scope import would be a collection error that no skipif prevents.
    from pytest_uia.adapters.ocr import OcrLocator

    window = resolve_main_window(app.pid)
    pixels = CountingLocator(OcrLocator(window))
    return WatchedChain(LocatorChain([UiaLocator(window), pixels]), pixels)
