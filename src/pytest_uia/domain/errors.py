"""Failures the domain raises when the desktop does not match what a test asked for.

Every adapter translates its own technology's misses into these, so a test never
has to read a comtypes HRESULT or a WinRT exception.
"""

from __future__ import annotations


class ElementNotFound(Exception):
    """No locator in the chain could resolve the query to an on-screen element."""


class WindowNotFound(Exception):
    """A launched application owns no visible top-level window (yet)."""


class TextNeverSettled(Exception):
    """An element was found; the text a test waited for never became its own.

    Deliberately not an ElementNotFound: the control was located every time it
    was looked at. What is late is the value the application re-announces once
    its own message pump has run, and reporting that as a missing element sends
    whoever reads the failure looking for a control that is right there.
    """


class InputRefused(Exception):
    """Windows dropped the synthetic input this process injected.

    Not a missing element: everything the test looked for was found, and the
    desktop simply would not let it be touched. Reporting it as the former
    sends whoever reads the failure looking for a control that is right there.
    """
