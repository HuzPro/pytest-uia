"""Failures the domain raises when the desktop does not match what a test asked for.

Every adapter translates its own technology's misses into these, so a test never
has to read a comtypes HRESULT or a WinRT exception.
"""

from __future__ import annotations


class ElementNotFound(Exception):
    """No locator in the chain could resolve the query to an on-screen element."""


class WindowNotFound(Exception):
    """A launched application owns no visible top-level window (yet)."""


class DialogNotFound(Exception):
    """No window with the caption a test addressed is open inside the application.

    Deliberately not a WindowNotFound: that one means the application has
    nothing on screen at all, and it is what a launch waits through. This is
    raised by an app whose main window is right there, so the first suspect is
    the step that was supposed to open the dialog — a click that reached
    nothing, or a caption that is not the one on the title bar.
    """


class DialogStillOpen(Exception):
    """A dialog a test waited to see the back of is still on screen.

    The other half of DialogNotFound, and a separate failure because it points
    at a different suspect: nothing is missing, and the step that should have
    dismissed the window either never ran or was refused.
    """


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
