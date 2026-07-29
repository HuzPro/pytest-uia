"""Adapter over the `uiautomation` package: the Windows accessibility tree.

The only module allowed to import `uiautomation`; the domain stays stdlib-only.
`UiaLocator` and `UiaElement` are GoF Adapters over the domain's ports.

Three rules hold below. An MSAA-bridged provider is read but never driven: the
bridge advertises `Invoke`/`SetValue` it cannot honour, so only acting is
gated. Every search is one-shot (`maxSearchSeconds=0`); waiting belongs to
`poll` alone. All UIA work stays on the calling thread:
`UIAutomationInitializerInThread` uses `threading.currentThread()`, removed in
Python 3.12.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from importlib.util import find_spec
from typing import Protocol

import uiautomation as auto
from comtypes import COMError

from pytest_uia.adapters.input import WINDOWS_POINTER, PointerInput
from pytest_uia.adapters.process_tree import process_family
from pytest_uia.domain.errors import (
    DialogNotFound,
    ElementNotFound,
    InputRefused,
    StillOffscreen,
    WindowNotFound,
)
from pytest_uia.domain.locator import Locator, LocatorChain
from pytest_uia.domain.name_match import ById, NameMatch
from pytest_uia.domain.query import Query, Role
from pytest_uia.domain.tree import (
    DEFAULT_LIMITS,
    DumpLimits,
    TreeNode,
    Walk,
    WalkEnded,
)

_TOP_LEVEL_WINDOWS = 1  # search depth: the desktop root's own children
_LOOK_ONCE = 0  # maxSearchSeconds: waiting is poll()'s job, not the library's

# What UIA calls the bridge it puts in front of any plain HWND whose owner
# never implemented a provider of its own.
_THE_GENERIC_PROXY = "Microsoft: MSAA Proxy"

# WinForms sits behind the same proxy with owner-drawn buttons of its own, but
# implements IAccessible itself; the Framework property is what separates them.
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
    Role.TAB: auto.ControlType.TabItemControl,
    Role.CHECKBOX: auto.ControlType.CheckBoxControl,
    Role.RADIO: auto.ControlType.RadioButtonControl,
    Role.SLIDER: auto.ControlType.SliderControl,
    Role.SPINBOX: auto.ControlType.SpinnerControl,
    Role.COMBOBOX: auto.ControlType.ComboBoxControl,
    Role.LISTBOX: auto.ControlType.ListControl,
    Role.TREE: auto.ControlType.TreeControl,
    Role.PROGRESSBAR: auto.ControlType.ProgressBarControl,
    Role.SCROLLBAR: auto.ControlType.ScrollBarControl,
    Role.GROUP: auto.ControlType.GroupControl,
    Role.IMAGE: auto.ControlType.ImageControl,
    Role.SPLIT_BUTTON: auto.ControlType.SplitButtonControl,
    Role.SEPARATOR: auto.ControlType.SeparatorControl,
    Role.THUMB: auto.ControlType.ThumbControl,
    Role.TAB_STRIP: auto.ControlType.TabControl,
    Role.LIST_ITEM: auto.ControlType.ListItemControl,
    Role.TREE_ITEM: auto.ControlType.TreeItemControl,
    Role.MENU_ITEM: auto.ControlType.MenuItemControl,
    Role.DATA_ITEM: auto.ControlType.DataItemControl,
    Role.HYPERLINK: auto.ControlType.HyperlinkControl,
    Role.DOCUMENT: auto.ControlType.DocumentControl,
}

# Derived so that widening a query and widening the dump stay one edit.
_ROLE_FOR_CONTROL_TYPE = {
    control_type: role for role, control_type in _CONTROL_TYPE_FOR_ROLE.items()
}


@contextmanager
def reporting_a_dead_window_as(
    absence: type[Exception], window: auto.Control
) -> Iterator[None]:
    """Translate the HRESULT a destroyed window answers with into a domain miss.

    A window that dies mid-test answers `COMError` to every property access,
    which no retry loop recognises. Shared with the OCR adapter, which grabs
    and clicks through the same window control.
    """
    try:
        yield
    except COMError as died:
        raise absence(_the_window_is_gone(window)) from died


def bring_to_the_front(window: auto.Control) -> None:
    """Put the window under test in front, and refuse to go on if it stayed put.

    `SetActive`'s answer must not be discarded: after a failed foreground
    change the mouse presses coordinates another application owns, and a grab
    photographs whatever is covering the window. `InputRefused` so the driver
    retries a foreground race inside the implicit wait.
    """
    if window.SetActive():
        return
    # A dead window answers False here too. Reading the caption separates the
    # two: a dead provider raises, and `reporting_a_dead_window_as` translates.
    raise InputRefused(_it_would_not_come_forward(window.Name))


def _it_would_not_come_forward(name: str) -> str:
    # A bare reason, not a sentence: the caller that owns the deadline prefixes
    # it with how long it kept trying before giving up.
    return (
        f"Windows would not bring the window {name!r} to the front, so whatever "
        "is covering it would have taken the click, or been photographed in "
        "its place"
    )


def _the_window_is_gone(window: auto.Control) -> str:
    # Asked defensively: the caption comes from the provider that just refused.
    try:
        which = f" {window.Name!r} (pid {window.ProcessId})"
    except COMError:
        which = ""
    return f"the window{which} is gone: the application behind it has exited"


def resolve_main_window(pid: int) -> auto.Control:
    """Find the one visible top-level window a launched application owns.

    "Owns" means the launched process *or anything it started*. The pid a
    launch reports is often a shim (a virtual environment's `python.exe`, a
    console-script wrapper, a `.bat`) that runs the real application as a
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
    # A search hands back a bare Control wrapper; asking the element what it
    # is restores the real class, and with it SetActive.
    return auto.Control.CreateControlFromElement(search.Element)


def resolve_window_titled(title: str) -> auto.Control:
    """Find a visible top-level window by the caption on its title bar."""
    search = auto.Control(searchDepth=_TOP_LEVEL_WINDOWS, Name=title)
    if not search.Exists(maxSearchSeconds=_LOOK_ONCE):
        raise WindowNotFound(f"no visible top-level window titled {title!r}")
    return auto.Control.CreateControlFromElement(search.Element)


def the_desktop() -> auto.Control:
    """The root every top-level window hangs off."""
    return auto.GetRootControl()


def visible_top_level_titles(desktop: auto.Control) -> tuple[str, ...]:
    """The captions on screen right now, for when an exact match found nothing.

    The usual reason a `--title` misses is a caption that is close but not the
    one on the title bar. Filtered exactly as `resolve_main_window` filters
    (named, and not offscreen) and one level deep, so that every line of it is
    a caption `--title` would have matched.
    """
    return tuple(
        control.Name
        for control, _depth in auto.WalkControl(desktop, maxDepth=_TOP_LEVEL_WINDOWS)
        if control.Name and not control.IsOffscreen
    )


def resolve_dialog_titled(window: auto.Control, title: str) -> auto.Control:
    """Find a child window of `window` by the caption on its own title bar.

    Constrained to WindowControl on purpose: without it, a caption that also
    appears as a word somewhere in the window answers instead. Depth is left
    open; how deeply a toolkit nests an owned window is its own business.
    """
    with reporting_a_dead_window_as(DialogNotFound, window):
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
    """Adapter presenting the accessibility tree as the domain's Locator.

    `root` narrows the search to one control's subtree; the window stays what
    it is either way, because the window is what comes forward for a click and
    what a dead provider is reported against.
    """

    def __init__(
        self,
        window: auto.Control,
        *,
        pointer: PointerInput = WINDOWS_POINTER,
        root: auto.Control | None = None,
    ) -> None:
        self._window = window
        self._root = window if root is None else root
        # Passed through rather than left to the element's own default, exactly
        # as OcrLocator does: it is the only way a spec can watch whether the
        # mouse was reached for at all.
        self._pointer = pointer

    def find(self, query: Query) -> UiaElement:
        with reporting_a_dead_window_as(ElementNotFound, self._window):
            control = auto.Control(
                searchFromControl=self._root,
                ControlType=_CONTROL_TYPE_FOR_ROLE[query.role],
                Compare=_named_as(query.name),
            )
            if not control.Exists(maxSearchSeconds=_LOOK_ONCE):
                raise ElementNotFound(self._nothing_matched())
            return UiaElement(control, self._window, pointer=self._pointer)

    def _nothing_matched(self) -> str:
        # LocatorChain prefixes this with the locator's own class name, so it
        # has to read as a reason, not as a repetition of the query.
        if self._root is not self._window:
            return f"no match inside {self._root.Name!r}"
        return (
            f"no match under window {self._window.Name!r} "
            f"(pid {self._window.ProcessId})"
        )


class ProviderTrust(Protocol):
    """Whether a control's provider really does what its patterns advertise."""

    def acts_for_real(self, control: object) -> bool: ...


class RealProvidersOnly:
    """The generic MSAA proxy synthesises Invoke from a posted BM_CLICK.

    Against an owner-drawn Tk button both `Invoke` and `DoDefaultAction`
    return cleanly and fire nothing, so the proxy is never trusted to act.
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
        with reporting_a_dead_window_as(ElementNotFound, self._window):
            if self._invoked_through_the_pattern():
                return
            if self._acted_through_a_state_pattern():
                return
            self._click_with_the_mouse()

    def type_text(self, text: str) -> None:
        with reporting_a_dead_window_as(ElementNotFound, self._window):
            if self._set_through_the_value_pattern(text):
                return
            if self._trusts_its_provider():
                self._type_into_the_control_the_tree_can_focus(text)
                return
            self._type_where_clicking_puts_the_caret(text)

    def read_text(self) -> str:
        # Ungated by provider trust: a reported property is the application's
        # own word; only actions through an untrusted proxy are guesses.
        with reporting_a_dead_window_as(ElementNotFound, self._window):
            if self._holds_editable_text():
                return self._whatever_the_value_pattern_holds()
            return self._control.Name

    def is_checked(self) -> bool:
        """Whether this control's TogglePattern currently reads as on.

        Ungated by provider trust, like `read_text`: a reported state is a
        fact, an action is a guess. A control with no TogglePattern answers
        False rather than raising.
        """
        with reporting_a_dead_window_as(ElementNotFound, self._window):
            pattern = self._control.GetPattern(auto.PatternId.TogglePattern)
            if pattern is None:
                return False
            return pattern.ToggleState == auto.ToggleState.On

    def is_visible(self) -> bool:
        # Being on-screen is not enough: a control can sit in the tree of a
        # painted window and still occupy no pixels at all.
        with reporting_a_dead_window_as(ElementNotFound, self._window):
            rectangle = self._control.BoundingRectangle
            return not self._control.IsOffscreen and not rectangle.isempty()

    def scroll_into_view(self) -> None:
        """Ask the provider to put this element's pixels on screen, and verify it.

        Not trust-gated: the visibility check afterwards catches a call any
        proxy only pretended to honour, so the postcondition is the gate.
        """
        with reporting_a_dead_window_as(ElementNotFound, self._window):
            pattern = self._control.GetPattern(auto.PatternId.ScrollItemPattern)
            if pattern is not None:
                _accepted(pattern.ScrollIntoView)
            if self.is_visible():
                return
            raise StillOffscreen(
                self._why_it_has_no_pixels(offered=pattern is not None)
            )

    def _why_it_has_no_pixels(self, *, offered: bool) -> str:
        if offered:
            return (
                "the provider accepted ScrollIntoView and the element has no "
                "pixels even so"
            )
        return "the provider offers no ScrollItemPattern, and the element has no pixels"

    def contents(self) -> UiaLocator:
        """The controls inside this one, searchable the way a window's are."""
        return UiaLocator(self._window, pointer=self._pointer, root=self._control)

    def _holds_editable_text(self) -> bool:
        # An edit control's Name is its label ("Title"); what the user typed
        # lives in its value instead.
        return self._control.ControlType == auto.ControlType.EditControl

    def _whatever_the_value_pattern_holds(self) -> str:
        pattern = self._control.GetPattern(auto.PatternId.ValuePattern)
        if pattern is None:
            # GetPattern answers None rather than raising; without this branch
            # a provider with no ValuePattern surfaces a bare AttributeError.
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

    def _acted_through_a_state_pattern(self) -> bool:
        """Toggle and Select are what a click means to the controls that offer
        them instead of Invoke; measured, a provider-served checkbox and radio
        each fire these for real. Trust-gated exactly as Invoke is.
        """
        if not self._trusts_its_provider():
            return False
        toggle = self._control.GetPattern(auto.PatternId.TogglePattern)
        if toggle is not None and _accepted(toggle.Toggle):
            return True
        selection = self._control.GetPattern(auto.PatternId.SelectionItemPattern)
        return selection is not None and _accepted(selection.Select)

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
        bring_to_the_front(self._window)
        self._control.SendKeys(text, charMode=True)

    def _type_where_clicking_puts_the_caret(self, text: str) -> None:
        # Win32 focus on a Tk child HWND is not Tk focus, so clicking is what
        # places the caret; OcrElement does the same for the same reason.
        self._click_with_the_mouse()
        self._control.SendKeys(text, charMode=True)

    def _click_with_the_mouse(self) -> None:
        # The pointer hits whatever is on top, so the window has to be in front
        # before the control's own coordinates mean anything.
        bring_to_the_front(self._window)
        # Not `Control.Click`, which discards Windows' answer: once the
        # accessibility tree has run out of patterns this is as exposed to a
        # foreground thief as an OCR-located click, and has to say so.
        middle = self._control.BoundingRectangle
        self._pointer.click(middle.xcenter(), middle.ycenter())


def _how_the_provider_describes_itself(control: object) -> str:
    # getattr, not attribute read: a control that answers no such question,
    # and every test double, stays on the trusted fast path.
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


def _named_as(match: NameMatch | ById) -> Callable[[auto.Control, int], bool]:
    # A UIA search keys on literal names only, so the matcher rides in on the
    # Compare callback, which `uiautomation` ANDs with the other properties.
    if isinstance(match, ById):

        def accepts(control: auto.Control, _depth: int) -> bool:
            return control.AutomationId == match.id

        return accepts

    def accepts(control: auto.Control, _depth: int) -> bool:
        return match.matches(control.Name)

    return accepts


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

    OCR joins the chain only when the `ocr` extra is installed.
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


def _the_controls_under(
    window: auto.Control, limits: DumpLimits, trust: ProviderTrust = TRUSTED_PROVIDERS
) -> Walk:
    """Read the window's subtree in pre-order, and stop when a limit says so.

    Eager rather than a generator: the result is bounded by construction, and
    a generator would put the `COMError` translation on the consumer's stack
    instead of at this boundary.
    """
    # Checked between controls: a provider can sit inside GetFirstChildControl
    # indefinitely (Program Manager: 4.1 s in one call), so the budget bounds
    # the walk, not a call.
    deadline = time.monotonic() + limits.budget
    nodes: list[TreeNode] = []
    ended = WalkEnded.FINISHED
    for control, depth in _under(window):
        if nodes and time.monotonic() >= deadline:
            ended = WalkEnded.RAN_OUT_OF_TIME
            break
        if nodes and len(nodes) >= limits.max_nodes:
            # One control too many is asked for and dropped, so "there are
            # more" is something the walk saw rather than something it guessed.
            # The window itself is exempt: the whole page is written relative
            # to a root, and a dump with none would have no window to name.
            ended = WalkEnded.HIT_THE_NODE_CAP
            break
        nodes.append(_read_as_a_node(control, depth, trust))
    return Walk(nodes=tuple(nodes), ended=ended, limits=limits)


def _under(window: auto.Control) -> Iterator[tuple[auto.Control, int]]:
    return auto.WalkControl(window, includeTop=True)


def _read_as_a_node(
    control: auto.Control, depth: int, trust: ProviderTrust
) -> TreeNode:
    """One control, or the fact that it stopped answering for itself.

    Caught per node: one control dying mid-dump must not discard everything
    that did answer, and dropping it silently would be worse.
    """
    try:
        return _everything_it_says_about_itself(control, depth, trust)
    except COMError:
        return TreeNode(control_type="", name="", depth=depth, readable=False)


def _everything_it_says_about_itself(
    control: auto.Control, depth: int, trust: ProviderTrust
) -> TreeNode:
    # No GetPattern probing: the trust rule is cheaper, and "does it advertise
    # Invoke" is the question whose answer cannot be believed.
    return TreeNode(
        control_type=control.ControlTypeName,
        name=control.Name,
        depth=depth,
        role=_ROLE_FOR_CONTROL_TYPE.get(control.ControlType),
        automation_id=control.AutomationId,
        driven_by_the_mouse=not trust.acts_for_real(control),
        offscreen=control.IsOffscreen,
    )


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
        with reporting_a_dead_window_as(WindowNotFound, self._control):
            return self._control.Name

    @property
    def pid(self) -> int:
        with reporting_a_dead_window_as(WindowNotFound, self._control):
            return self._control.ProcessId

    @property
    def contents(self) -> LocatorChain:
        return self._contents

    def walk(self, limits: DumpLimits = DEFAULT_LIMITS) -> Walk:
        """Every control under this window, as far as the limits allow."""
        with reporting_a_dead_window_as(WindowNotFound, self._control):
            return _the_controls_under(self._control, limits)

    def dialog_titled(self, title: str) -> UiaWindow:
        """A window inside this one, searched exactly as this one is searched.

        Answering with another UiaWindow is what makes a dialog scopable: the
        chain it builds starts at the dialog's own control, so a query answered
        through it cannot reach the window underneath.
        """
        return UiaWindow(resolve_dialog_titled(self._control, title))

    def close(self) -> None:
        with reporting_a_dead_window_as(WindowNotFound, self._control):
            close_window(self._control)


class UiaDesktop:
    """Adapter presenting the Windows desktop as the session's window source."""

    def window_of_process(self, pid: int) -> UiaWindow:
        return UiaWindow(resolve_main_window(pid))

    def window_titled(self, title: str) -> UiaWindow:
        return UiaWindow(resolve_window_titled(title))
