"""Adapter over the `uiautomation` package: the Windows accessibility tree.

This is the only module allowed to import `uiautomation`. The domain stays
stdlib-only so it can be reasoned about, and unit tested, with no desktop at
all. `UiaLocator` and `UiaElement` are GoF Adapters: they present the domain's
Locator and Element ports in terms of UIA controls and patterns.

Three rules hold for everything below.

An untrusted provider can be *read*, but not *driven*. Where a control's owner
never wrote a UIA provider, Windows fabricates one out of the old MSAA API, and
that bridge advertises patterns it cannot honour: on an owner-drawn widget
`Invoke` and `SetValue` return cleanly and reach nothing. Reading is a different
matter — a name or a value served out of an annotation store is the
application's own word about itself — so only the *acting* half is gated.

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
from typing import Protocol

import uiautomation as auto
from comtypes import COMError

from pytest_uia.adapters.input import WINDOWS_POINTER, PointerInput
from pytest_uia.adapters.process_tree import process_family
from pytest_uia.domain.errors import DialogNotFound, ElementNotFound, WindowNotFound
from pytest_uia.domain.locator import Locator, LocatorChain
from pytest_uia.domain.query import Query, Role

_TOP_LEVEL_WINDOWS = 1  # search depth: the desktop root's own children
_LOOK_ONCE = 0  # maxSearchSeconds: waiting is poll()'s job, not the library's

# What UIA calls the bridge it puts in front of any plain HWND whose owner
# never implemented a provider of its own.
_THE_GENERIC_PROXY = "Microsoft: MSAA Proxy"

# Measured, not assumed: WinForms is served by that same proxy and its buttons
# are owner-drawn exactly like Tk's, so neither the marker nor the window style
# separates them. The framework does — 'WinForm' against Tk's 'Win32' — because
# behind the proxy these toolkits implement IAccessible themselves, and a
# BM_CLICK they never see is not how their controls are reached.
_FRAMEWORKS_THAT_ANSWER_FOR_THEMSELVES = frozenset(
    {
        "WinForm",
        "WPF",
        "XAML",
        "DirectUI",
        "Chrome",
        "Silverlight",
        "JavaAccessBridge",
    }
)

_CONTROL_TYPE_FOR_ROLE = {
    Role.BUTTON: auto.ControlType.ButtonControl,
    Role.TEXT: auto.ControlType.TextControl,
    Role.TEXTBOX: auto.ControlType.EditControl,
}


def resolve_main_window(pid: int) -> auto.Control:
    """Find the one visible top-level window a launched application owns.

    "Owns" means the launched process *or anything it started*. The pid a
    launch reports is often a shim — a virtual environment's `python.exe`, a
    console-script wrapper, a `.bat` — that runs the real application as a
    child, and the window then belongs to a pid the caller never saw.

    Deliberately unconstrained by control type: a Tk toplevel is not a
    WindowControl, and the thinnest trees are exactly the ones that matter.

    The family is re-read on every call rather than cached, because this is
    polled while an application starts and the child does not exist yet on the
    first look.
    """
    search = auto.Control(
        searchDepth=_TOP_LEVEL_WINDOWS,
        Compare=_owned_and_on_screen(process_family(pid)),
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


def resolve_dialog_titled(window: auto.Control, title: str) -> auto.Control:
    """Find a child window of `window` by the caption on its own title bar.

    Constrained to WindowControl on purpose. Measured, a Tk `Toplevel` opened
    with `transient()` and `grab_set()` arrives as a WindowControl one level
    under its owner — but so does every label, and without the constraint a
    caption that also appears as a word somewhere in the window would answer
    instead, handing back a "dialog" with no children a test could ever explain.

    Depth is left open, because how deeply a toolkit nests an owned window is
    the toolkit's business and not this function's.
    """
    search = auto.Control(
        searchFromControl=window,
        ControlType=auto.ControlType.WindowControl,
        Name=title,
    )
    if not search.Exists(maxSearchSeconds=_LOOK_ONCE):
        raise DialogNotFound(
            f"no window titled {title!r} inside {window.Name!r} "
            f"(pid {window.ProcessId})"
        )
    return auto.Control.CreateControlFromElement(search.Element)


def close_window(window: auto.Control) -> None:
    """Ask a window to close itself, exactly as its title bar's X does.

    Politeness is the point: an app that closes its own window runs whatever it
    normally runs on the way out, instead of being shot in the head.
    """
    window.GetPattern(auto.PatternId.WindowPattern).Close()


class UiaLocator:
    """Adapter presenting the accessibility tree as the domain's Locator."""

    def __init__(
        self, window: auto.Control, *, pointer: PointerInput = WINDOWS_POINTER
    ) -> None:
        self._window = window
        # Passed through rather than left to the element's own default, exactly
        # as OcrLocator does: it is the only way a spec can watch whether the
        # mouse was reached for at all.
        self._pointer = pointer

    def find(self, query: Query) -> UiaElement:
        control = auto.Control(
            searchFromControl=self._window,
            ControlType=_CONTROL_TYPE_FOR_ROLE[query.role],
            Name=query.name,
        )
        if not control.Exists(maxSearchSeconds=_LOOK_ONCE):
            raise ElementNotFound(self._nothing_matched())
        return UiaElement(control, self._window, pointer=self._pointer)

    def _nothing_matched(self) -> str:
        # LocatorChain prefixes this with the locator's own class name, so it
        # has to read as a reason, not as a repetition of the query.
        return (
            f"no match under window {self._window.Name!r} "
            f"(pid {self._window.ProcessId})"
        )


class ProviderTrust(Protocol):
    """Whether a control's provider really does what its patterns advertise."""

    def acts_for_real(self, control: object) -> bool: ...


class RealProvidersOnly:
    """The generic MSAA proxy synthesises Invoke from a posted BM_CLICK.

    Against an owner-drawn Tk button that is a message into the void: no
    exception, no click, and a test that passes having done nothing. Measured
    against a real click counter, `InvokePattern.Invoke()` and
    `LegacyIAccessible.DoDefaultAction()` both return cleanly and fire nothing.
    """

    def acts_for_real(self, control: object) -> bool:
        if _THE_GENERIC_PROXY not in _how_the_provider_describes_itself(control):
            return True
        return _the_framework_behind(control) in _FRAMEWORKS_THAT_ANSWER_FOR_THEMSELVES


TRUSTED_PROVIDERS: ProviderTrust = RealProvidersOnly()
"""The rule every element applies unless a spec hands it a double instead."""


class UiaElement:
    """Adapter presenting a single UIA control as the domain's Element."""

    def __init__(
        self,
        control: auto.Control,
        window: auto.Control,
        *,
        pointer: PointerInput = WINDOWS_POINTER,
        trust: ProviderTrust = TRUSTED_PROVIDERS,
    ) -> None:
        self._control = control
        self._window = window
        self._pointer = pointer
        self._trust = trust

    def click(self) -> None:
        if self._invoked_through_the_pattern():
            return
        self._click_with_the_mouse()

    def type_text(self, text: str) -> None:
        if self._set_through_the_value_pattern(text):
            return
        if self._trusts_its_provider():
            self._type_into_the_control_the_tree_can_focus(text)
            return
        self._type_where_clicking_puts_the_caret(text)

    def read_text(self) -> str:
        # Deliberately ungated by provider trust. An untrusted provider can be
        # read but not driven: a property served out of an annotation store is
        # the application's own word for itself, and only the *actions* are
        # guesses about a control the proxy cannot really reach.
        if self._holds_editable_text():
            return self._whatever_the_value_pattern_holds()
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

    def _whatever_the_value_pattern_holds(self) -> str:
        pattern = self._control.GetPattern(auto.PatternId.ValuePattern)
        if pattern is None:
            # `GetPattern` answers None rather than raising, so an edit control
            # whose provider never offered one escaped as a bare AttributeError
            # — which is not an ElementNotFound, so poll() never retried it and
            # the driver never caught it.
            return self._control.Name
        # An empty value is an answer, and it is kept. An annotated Tk entry
        # nobody has typed into really is empty, and reporting its label's name
        # instead would be a confident account of text that is not there.
        return pattern.Value

    def _invoked_through_the_pattern(self) -> bool:
        """Invoking needs no focus and steals none, so it is always tried first."""
        if not self._trusts_its_provider():
            return False
        pattern = self._control.GetPattern(auto.PatternId.InvokePattern)
        return pattern is not None and _accepted(pattern.Invoke)

    def _trusts_its_provider(self) -> bool:
        return self._trust.acts_for_real(self._control)

    def _set_through_the_value_pattern(self, text: str) -> bool:
        """Setting the value needs no focus, and it cannot mistype."""
        if not self._trusts_its_provider():
            return False
        pattern = self._control.GetPattern(auto.PatternId.ValuePattern)
        return pattern is not None and _accepted(lambda: pattern.SetValue(text))

    def _type_into_the_control_the_tree_can_focus(self, text: str) -> None:
        # Keystrokes land wherever the caret is, so the window has to be in
        # front first; SendKeys focuses the control itself.
        self._window.SetActive()
        self._control.SendKeys(text, charMode=True)

    def _type_where_clicking_puts_the_caret(self, text: str) -> None:
        # A Tk widget owns focus within its toplevel through Tk's own model, so
        # Win32 focus on its child HWND is not Tk focus, and asking the tree for
        # it hands the caret to nobody. Clicking is what is left — which is
        # exactly what OcrElement does, for exactly the same reason.
        self._click_with_the_mouse()
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


def _how_the_provider_describes_itself(control: object) -> str:
    # Asked with getattr rather than read: absence of evidence of proxying is
    # trust, which is what keeps every control that answers no such question at
    # all — and every test double — on the fast path.
    return str(getattr(control, "ProviderDescription", ""))


def _the_framework_behind(control: object) -> str:
    return str(getattr(control, "FrameworkId", ""))


def _accepted(request: Callable[[], object]) -> bool:
    # A provider is free to advertise a pattern and then fail the call. That is
    # a reason to try the next approach, not a reason to fail the test.
    try:
        request()
    except COMError:
        return False
    return True


def _owned_and_on_screen(
    family: frozenset[int],
) -> Callable[[auto.Control, int], bool]:
    # UIA searches have no ProcessId key, so pid scoping has to ride in on the
    # Compare callback.
    def matches(control: auto.Control, _depth: int) -> bool:
        return control.ProcessId in family and not control.IsOffscreen

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

    def dialog_titled(self, title: str) -> UiaWindow:
        """A window inside this one, searched exactly as this one is searched.

        Answering with another UiaWindow is what makes a dialog scopable: the
        chain it builds starts at the dialog's own control, so a query answered
        through it cannot reach the window underneath.
        """
        return UiaWindow(resolve_dialog_titled(self._control, title))

    def close(self) -> None:
        close_window(self._control)


class UiaDesktop:
    """Adapter presenting the Windows desktop as the session's window source."""

    def window_of_process(self, pid: int) -> UiaWindow:
        return UiaWindow(resolve_main_window(pid))

    def window_titled(self, title: str) -> UiaWindow:
        return UiaWindow(resolve_window_titled(title))
