"""Adapter over the `uiautomation` package: the Windows accessibility tree.

This is the only module allowed to import `uiautomation`. The domain stays
stdlib-only so it can be reasoned about, and unit tested, with no desktop at
all. `UiaLocator` and `UiaElement` are GoF Adapters: they present the domain's
Locator and Element ports in terms of UIA controls and patterns.

Two rules hold for everything below.

Every search is one-shot. Left alone, `uiautomation` retries inside `Exists`
and waits ten seconds inside any property access on a control it has not found
yet; underneath the domain's own `poll` that turns each configured timeout into
a multiple of itself. Passing `maxSearchSeconds=0` keeps `poll` the single
authority on waiting.

All UIA work happens on the calling thread, which in v1 means the main thread.
`uiautomation`'s `UIAutomationInitializerInThread(debug=True)` calls
`threading.currentThread()`, removed in Python 3.12, so moving UIA off the main
thread is a trap rather than an optimisation.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib.util import find_spec

import uiautomation as auto
from comtypes import COMError

from pytest_uia.adapters.input import WINDOWS_POINTER, PointerInput
from pytest_uia.domain.errors import ElementNotFound, WindowNotFound
from pytest_uia.domain.locator import Locator, LocatorChain
from pytest_uia.domain.query import Query, Role

_TOP_LEVEL_WINDOWS = 1  # search depth: the desktop root's own children
_LOOK_ONCE = 0  # maxSearchSeconds: waiting is poll()'s job, not the library's

_CONTROL_TYPE_FOR_ROLE = {
    Role.BUTTON: auto.ControlType.ButtonControl,
    Role.TEXT: auto.ControlType.TextControl,
    Role.TEXTBOX: auto.ControlType.EditControl,
}


def resolve_main_window(pid: int) -> auto.Control:
    """Find the one visible top-level window a launched application owns.

    Deliberately unconstrained by control type: a Tk toplevel is not a
    WindowControl, and the thinnest trees are exactly the ones that matter.
    """
    search = auto.Control(
        searchDepth=_TOP_LEVEL_WINDOWS,
        Compare=_owned_and_on_screen(pid),
    )
    if not search.Exists(maxSearchSeconds=_LOOK_ONCE):
        raise WindowNotFound(f"no visible top-level window for pid {pid}")
    # A search hands back a bare Control wrapper. The window's real class — and
    # with it SetActive, which only top-level controls have — comes from asking
    # the element what it actually is.
    return auto.Control.CreateControlFromElement(search.Element)


def resolve_window_titled(title: str) -> auto.Control:
    """Find a visible top-level window by the caption on its title bar."""
    search = auto.Control(searchDepth=_TOP_LEVEL_WINDOWS, Name=title)
    if not search.Exists(maxSearchSeconds=_LOOK_ONCE):
        raise WindowNotFound(f"no visible top-level window titled {title!r}")
    return auto.Control.CreateControlFromElement(search.Element)


def close_window(window: auto.Control) -> None:
    """Ask a window to close itself, exactly as its title bar's X does.

    Politeness is the point: an app that closes its own window runs whatever it
    normally runs on the way out, instead of being shot in the head.
    """
    window.GetPattern(auto.PatternId.WindowPattern).Close()


class UiaLocator:
    """Adapter presenting the accessibility tree as the domain's Locator."""

    def __init__(self, window: auto.Control) -> None:
        self._window = window

    def find(self, query: Query) -> UiaElement:
        control = auto.Control(
            searchFromControl=self._window,
            ControlType=_CONTROL_TYPE_FOR_ROLE[query.role],
            Name=query.name,
        )
        if not control.Exists(maxSearchSeconds=_LOOK_ONCE):
            raise ElementNotFound(self._nothing_matched())
        return UiaElement(control, self._window)

    def _nothing_matched(self) -> str:
        # LocatorChain prefixes this with the locator's own class name, so it
        # has to read as a reason, not as a repetition of the query.
        return (
            f"no match under window {self._window.Name!r} "
            f"(pid {self._window.ProcessId})"
        )


class UiaElement:
    """Adapter presenting a single UIA control as the domain's Element."""

    def __init__(
        self,
        control: auto.Control,
        window: auto.Control,
        *,
        pointer: PointerInput = WINDOWS_POINTER,
    ) -> None:
        self._control = control
        self._window = window
        self._pointer = pointer

    def click(self) -> None:
        if self._invoked_through_the_pattern():
            return
        self._click_with_the_mouse()

    def type_text(self, text: str) -> None:
        if self._set_through_the_value_pattern(text):
            return
        self._type_with_the_keyboard(text)

    def read_text(self) -> str:
        if self._holds_editable_text():
            return self._control.GetPattern(auto.PatternId.ValuePattern).Value
        return self._control.Name

    def is_visible(self) -> bool:
        # Being on-screen is not enough: a control can sit in the tree of a
        # painted window and still occupy no pixels at all.
        rectangle = self._control.BoundingRectangle
        return not self._control.IsOffscreen and not rectangle.isempty()

    def _holds_editable_text(self) -> bool:
        # An edit control's Name is its label ("Title"); what the user typed
        # lives in its value instead.
        return self._control.ControlType == auto.ControlType.EditControl

    def _invoked_through_the_pattern(self) -> bool:
        """Invoking needs no focus and steals none, so it is always tried first."""
        pattern = self._control.GetPattern(auto.PatternId.InvokePattern)
        return pattern is not None and _accepted(pattern.Invoke)

    def _set_through_the_value_pattern(self, text: str) -> bool:
        """Setting the value needs no focus, and it cannot mistype."""
        pattern = self._control.GetPattern(auto.PatternId.ValuePattern)
        return pattern is not None and _accepted(lambda: pattern.SetValue(text))

    def _type_with_the_keyboard(self, text: str) -> None:
        # Keystrokes land wherever the caret is, so the window has to be in
        # front first; SendKeys focuses the control itself.
        self._window.SetActive()
        self._control.SendKeys(text, charMode=True)

    def _click_with_the_mouse(self) -> None:
        # The pointer hits whatever is on top, so the window has to be in front
        # before the control's own coordinates mean anything.
        self._window.SetActive()
        # Not `Control.Click`, which discards Windows' answer: once the
        # accessibility tree has run out of patterns this is as exposed to a
        # foreground thief as an OCR-located click, and has to say so.
        middle = self._control.BoundingRectangle
        self._pointer.click(middle.xcenter(), middle.ycenter())


def _accepted(request: Callable[[], object]) -> bool:
    # A provider is free to advertise a pattern and then fail the call. That is
    # a reason to try the next approach, not a reason to fail the test.
    try:
        request()
    except COMError:
        return False
    return True


def _owned_and_on_screen(pid: int) -> Callable[[auto.Control, int], bool]:
    # UIA searches have no ProcessId key, so pid scoping has to ride in on the
    # Compare callback.
    def matches(control: auto.Control, _depth: int) -> bool:
        return control.ProcessId == pid and not control.IsOffscreen

    return matches


def _locators_for(window: auto.Control) -> list[Locator]:
    """The accessibility tree first, always; pixels only if nothing answered.

    OCR joins the chain only when the `ocr` extra is installed, so a project
    that never needs it never pays for it — and one that installs it gets the
    fallback with nothing to configure.
    """
    locators: list[Locator] = [UiaLocator(window)]
    if _windows_ocr_is_installed():
        # Imported here rather than at module scope: this module has to import
        # on machines where the `ocr` extra was never installed.
        from pytest_uia.adapters.ocr import OcrLocator

        locators.append(OcrLocator(window))
    return locators


def _windows_ocr_is_installed() -> bool:
    try:
        return find_spec("winrt.windows.media.ocr") is not None
    except ModuleNotFoundError:
        # find_spec imports every parent package on the way down, so a missing
        # extra raises out of it rather than answering None.
        return False


class UiaWindow:
    """Adapter presenting a top-level UIA control as a window under test.

    Owns the chain that searches inside it, which is why the chain is built
    here rather than in the session: this is the only object that knows what
    the window actually is.
    """

    def __init__(self, control: auto.Control) -> None:
        self._control = control
        # The single place the locator strategy is decided.
        self._contents = LocatorChain(_locators_for(control))

    @property
    def title(self) -> str:
        return self._control.Name

    @property
    def pid(self) -> int:
        return self._control.ProcessId

    @property
    def contents(self) -> LocatorChain:
        return self._contents

    def close(self) -> None:
        close_window(self._control)


class UiaDesktop:
    """Adapter presenting the Windows desktop as the session's window source."""

    def window_of_process(self, pid: int) -> UiaWindow:
        return UiaWindow(resolve_main_window(pid))

    def window_titled(self, title: str) -> UiaWindow:
        return UiaWindow(resolve_window_titled(title))
