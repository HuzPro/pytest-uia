"""Behavioral spec for driving a tabbed window through the accessibility tree.

Where it plugs in: the same adapter every other UIA spec drives, aimed at the
one widget that can hide an application from a test. A notebook shows one page
and unmaps the rest, so without a way to change tabs a suite can only assert on
whichever page the application happened to open with — for a settings window,
that is one tab out of six.

Both halves are needed and each is useless alone. `tk-uia` gives every tab a
window handle so there is something in the tree to name; this plugin has to ask
for the control type a tab really is. Neither half is visible in the test body,
which is the point: `app.tab("Database").click()` reads like every other line.

Real mouse input, like the rest of the Tk specs: a tab's handle is transparent
to hit-testing so the click passes through to Tk, and Tk's own tabs were never
pressable through a pattern in the first place.
"""

from __future__ import annotations

import sys

import pytest

from pytest_uia.application.driver import App
from pytest_uia.domain.errors import ElementNotFound
from tests.conftest import (
    skipped_when_windows_refuses_synthetic_input,
    tk_uia_is_installed,
)

# Declared here rather than imported from the fixture app, which is a script
# and reaches `legible` the way a script does. Drift between the two cannot
# hide: every spec below fails by name if a tab is not on the strip.
GENERAL = "General"
DATABASE = "Database"
ABOUT = "About"
TABS = (GENERAL, DATABASE, ABOUT)


def what_the_page_says(tab: str) -> str:
    return f"{tab} page"


pytestmark = [
    pytest.mark.gui,
    pytest.mark.skipif(
        sys.platform != "win32",
        reason="UI Automation is a Windows API",
    ),
    pytest.mark.skipif(
        not tk_uia_is_installed(),
        reason="install tk-uia: the fixture app annotates itself with it",
    ),
]


def test_every_tab_of_a_notebook_is_reachable_by_the_name_on_it(
    tk_notebook_app: App,
) -> None:
    # Given a Tk window whose three pages sit behind a notebook
    # When the test asks for each tab by the name the strip shows
    # Then every one of them is there. Bare Tk paints its tab strip inside the
    # notebook's own window and exposes no tabs at all, so this is the whole
    # difference between a tabbed window a suite can drive and one it cannot
    missing = [tab for tab in TABS if not tk_notebook_app.tab(tab).exists()]

    assert missing == [], f"no tab in the tree answers to {missing}"


def test_clicking_a_tab_brings_its_page_into_the_tree(
    tk_notebook_app: App,
) -> None:
    # Given a notebook opened on its first page, whose other pages Tk has not
    # mapped and which therefore are not in the accessibility tree at all
    with skipped_when_windows_refuses_synthetic_input():
        assert tk_notebook_app.text(what_the_page_says(GENERAL)).exists()
        assert not tk_notebook_app.text(what_the_page_says(DATABASE)).exists()

        # When the test selects another tab
        tk_notebook_app.tab(DATABASE).click()

        # Then that page is the one a query can now reach. This is the point of
        # the whole feature: everything on a page a test cannot open is
        # unreachable no matter how well the application names it
        assert tk_notebook_app.text(what_the_page_says(DATABASE)).exists(), (
            "the tab was clicked and the page behind it never appeared"
        )


def test_the_page_left_behind_stops_answering_once_another_tab_is_open(
    tk_notebook_app: App,
) -> None:
    # Given the notebook showing its first page
    with skipped_when_windows_refuses_synthetic_input():
        assert tk_notebook_app.text(what_the_page_says(GENERAL)).exists()

        # When the test moves to another tab
        tk_notebook_app.tab(ABOUT).click()

        # Then the page it left is gone from the tree. Worth pinning rather
        # than assuming: Tk unmaps the page it is no longer showing, so a suite
        # that asserted on both pages at once would be asserting on a window
        # that has never existed
        assert not tk_notebook_app.text(what_the_page_says(GENERAL)).exists(), (
            "the page that is no longer showing is still answering queries"
        )


def test_asking_for_a_tab_that_is_not_on_the_strip_says_so_rather_than_hanging(
    tk_notebook_app: App,
) -> None:
    # Given the same window
    # When the test asks for a tab the notebook does not have
    with pytest.raises(ElementNotFound):
        tk_notebook_app.tab("Nonexistent", timeout=1.0).click()

    # Then it is told. A tab query that quietly matched something else would be
    # worse than one that missed: the click would land somewhere on the strip


def test_the_dump_offers_a_tab_query_for_every_tab_it_can_see(
    tk_notebook_app: App,
) -> None:
    # Given the window as it opens
    # When its tree is dumped
    queries = tk_notebook_app.dump().queries

    # Then each tab is offered as the call that would select it. The dump is
    # where somebody meets a tabbed window for the first time, and a tab listed
    # with no query beside it is the reader being shown a wall they cannot pass
    for tab in TABS:
        assert f'app.tab("{tab}")' in queries, (
            f"the dump offers {queries}, with no way to reach {tab}"
        )
