"""Failures the domain raises when the desktop does not match what a test asked for.

Every adapter translates its own technology's misses into these, so a test never
has to read a comtypes HRESULT or a WinRT exception.
"""

from __future__ import annotations


class ElementNotFound(Exception):
    """No locator in the chain could resolve the query to an on-screen element."""


class WindowNotFound(Exception):
    """No visible top-level window answers for the application under test.

    Covers both ends of a window's life: one that has not been painted yet,
    which is what a launch waits through, and one that has been destroyed
    underneath a test still holding it.
    """


class LaunchFailed(Exception):
    """The command a test launched was gone before it could own a window.

    Not a WindowNotFound: there is nothing left to wait for, and the exit
    code is the entire diagnosis.
    """


class ProcessStillRunning(Exception):
    """Every way of ending an application was tried, and it is still there.

    Raised rather than returned from, because the alternative is the worst
    outcome a teardown has: a window nobody expects on the next test's screen,
    and no record anywhere of which run left it there.
    """


class DialogNotFound(Exception):
    """No window with the caption a test addressed is open inside the application.

    Not a WindowNotFound: the main window is right there, so the first suspect
    is the step that was supposed to open the dialog.
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
    """The desktop would not let this process reach the window under test.

    Dropped synthetic input, or a window that would not come to the front.
    Not a missing element: everything the test looked for was found, and the
    desktop simply would not let it be touched.
    """
