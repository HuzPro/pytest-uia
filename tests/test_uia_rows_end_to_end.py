"""Behavioral spec for rows a provider really exposes, found as list items.

Driven against the WinForms fixture because that is the claim: where a list's
provider exposes its rows (WinForms, WPF, Chromium and so every Electron
window), `list_item` reaches them, unscoped or through the list that holds
them. Tk's rows are not in the tree at all, which is why the gallery cannot
carry this spec.
"""

from __future__ import annotations

import sys

import pytest

from pytest_uia.application.driver import App
from pytest_uia.domain.errors import StillOffscreen

pytestmark = [
    pytest.mark.gui,
    pytest.mark.skipif(
        sys.platform != "win32", reason="UI Automation is a Windows API"
    ),
]

A_ROW = "file the report"
THE_LIST = "Tasks"


def test_a_row_the_provider_exposes_is_found_as_a_list_item(
    winforms_app: App,
) -> None:
    # Given a list whose provider exposes its rows
    # When the test asks for one row by the text it shows
    found = winforms_app.list_item(A_ROW).exists()

    # Then the row itself answers, not merely the list around it
    assert found, f"app.list_item({A_ROW!r}) found nothing"


def test_a_row_is_reachable_through_the_list_that_holds_it(
    winforms_app: App,
) -> None:
    # Given the same list, addressed first
    # When the test asks for the row through it
    found = winforms_app.listbox(THE_LIST).list_item(A_ROW).exists()

    # Then the scoped path answers too: the shape a test needs the moment a
    # second list on the same window holds a row with the same words
    assert found, f'app.listbox("{THE_LIST}").list_item({A_ROW!r}) found nothing'


def test_a_row_whose_provider_cannot_scroll_it_reports_still_offscreen(
    winforms_app: App,
) -> None:
    # Given the last row: in the tree, below the fold, and served by the
    # classic list box proxy, which measures as offering no ScrollItemPattern
    last_row = winforms_app.list_item("backlog item 12")
    assert last_row.exists(), (
        "the row has to be findable for this spec to mean anything"
    )

    # When the test asks for it on screen anyway
    with pytest.raises(StillOffscreen) as failure:
        last_row.scroll_into_view(timeout=0.5)

    # Then the failure names the missing pattern rather than blaming the row.
    # Providers that implement it (Chromium, WPF) get the real scroll; a
    # classic Win32 list gets the truth about why it cannot have one.
    assert "ScrollItemPattern" in str(failure.value)
