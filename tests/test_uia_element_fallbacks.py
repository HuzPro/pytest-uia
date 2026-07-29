"""Behavioral spec for what UiaElement does when the UIA patterns let it down.

Plenty of apps worth testing expose a half-built accessibility tree: a control
with no InvokePattern, an edit box whose provider fails the call, and (worst
of the three) one that advertises a pattern, accepts the call, returns no
error and does nothing. These specs use doubles, because a control that
misbehaves exactly when asked is not something a real fixture app can offer.

The doubles carry uiautomation's own PascalCase method names on purpose: they
stand in for its Control objects, and renaming them would hide that.
"""

from __future__ import annotations

import sys

import pytest
import uiautomation as auto
from comtypes import COMError

from pytest_uia.adapters.uia import UiaElement
from pytest_uia.domain.errors import InputRefused, StillOffscreen

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="UI Automation is a Windows API",
)

_E_FAIL = -2147467259

# A control 100x40 at (10, 20), so its centre is somewhere no arithmetic slip
# could reach by accident.
_CONTROL_RECTANGLE = auto.Rect(10, 20, 110, 60)
_ITS_CENTRE = (60, 40)

# What the two fixture windows really report, with the pids that change on
# every run elided. The generic proxy serves both of them, so its marker alone
# separates nothing, the framework behind it is what says whether there is a
# provider under the proxy that will honour the call.
_TK_DESCRIPTION = (
    "Main:Nested [... Annotation(parent link):Microsoft: Annotation Proxy ...; "
    "Main:Microsoft: MSAA Proxy ...]"
)
_TK_FRAMEWORK = "Win32"
_WINFORMS_DESCRIPTION = "Main:Nested [... Main(parent link):Microsoft: MSAA Proxy ...]"
_WINFORMS_FRAMEWORK = "WinForm"

# What a window whose application serves a real UIA provider reports: no MSAA
# proxy anywhere in it, so the trust rule believes its patterns.
_REAL_PROVIDER_DESCRIPTION = (
    "Main:Nested [... Main(parent link):Unidentified Provider (unmanaged)]; "
    "Hwnd(parent link):Microsoft: HWND Proxy (unmanaged:uiautomationcore.dll)]"
)

_A_DRAFT = "Write the report"


def _provider_refuses() -> COMError:
    """A fresh refusal every time.

    One shared exception instance accumulates the traceback of every raise it
    has ever been through, which makes the next failure report point at the
    previous test.
    """
    return COMError(_E_FAIL, "Unspecified error", (None,) * 5)


class PatternlessControl:
    """Test double: a control whose provider supports no pattern at all.

    Offers no `Click` on purpose. `uiautomation`'s own click throws away
    Windows' answer about whether the event was delivered, so an adapter that
    still reached for it would fail this file rather than a gui run.
    """

    IsOffscreen = False

    def __init__(self) -> None:
        self.typed: list[tuple[str, bool]] = []
        self.BoundingRectangle = _CONTROL_RECTANGLE

    def GetPattern(self, patternId: int) -> None:
        return None

    def SendKeys(self, text: str, charMode: bool = True) -> None:
        self.typed.append((text, charMode))


class FailingInvokeControl(PatternlessControl):
    """Test double: a control that advertises Invoke, only Invoke, and refuses it."""

    def GetPattern(self, patternId: int) -> FailingInvokeControl | None:
        if patternId == auto.PatternId.InvokePattern:
            return self
        return None

    def Invoke(self) -> None:
        raise _provider_refuses()


class FailingValueControl(PatternlessControl):
    """Test double: a control that advertises a value pattern and refuses it."""

    def GetPattern(self, patternId: int) -> FailingValueControl:
        return self

    def SetValue(self, value: str) -> None:
        raise _provider_refuses()


class InvokingControl(PatternlessControl):
    """Test double: a control that advertises Invoke and counts the calls."""

    def __init__(self) -> None:
        super().__init__()
        self.invocations = 0

    def GetPattern(self, patternId: int) -> InvokingControl:
        return self

    def Invoke(self) -> None:
        self.invocations += 1


class ProxiedControl(InvokingControl):
    """Test double: a Tk button, as the generic MSAA proxy describes one.

    The proxy synthesises Invoke out of a posted BM_CLICK, and every Tk button
    is owner-drawn, so the message goes nowhere. Nothing raises, nothing
    happens, and a test that trusted the silence would pass having done
    nothing at all.
    """

    ProviderDescription = _TK_DESCRIPTION
    FrameworkId = _TK_FRAMEWORK


class WinFormsControl(InvokingControl):
    """Test double: a WinForms button, which the same generic proxy also serves.

    The reason the proxy marker cannot be the whole rule: this control reports
    it too, is owner-drawn too, and its Invoke works.
    """

    ProviderDescription = _WINFORMS_DESCRIPTION
    FrameworkId = _WINFORMS_FRAMEWORK


class UnbackedEditControl(PatternlessControl):
    """Test double: an edit control whose provider never offered a value.

    `GetPattern` answers None rather than raising; unhandled, that surfaces as
    a bare AttributeError nothing retries.
    """

    ControlType = auto.ControlType.EditControl
    Name = "Title"

    def GetPattern(self, patternId: int) -> None:
        return None


class EmptyEditControl(UnbackedEditControl):
    """Test double: an annotated edit control nobody has typed into yet."""

    Value = ""

    def GetPattern(self, patternId: int) -> EmptyEditControl:
        return self


class JournallingPointer:
    """Test double: a mouse and a keyboard writing into one list, in order.

    Two separate recorders can each say that a thing happened; only a shared
    one can say which happened first, and "click it, then type" is the whole
    of the claim.
    """

    def __init__(self) -> None:
        self.acts: list[str] = []

    def click(self, x: int, y: int) -> None:
        self.acts.append(f"clicked {(x, y)}")

    def keys(self, text: str) -> None:
        self.acts.append(f"typed {text!r}")


class ProxiedTextBox:
    """Test double: a Tk entry, as the generic MSAA proxy describes one.

    It advertises a value pattern (annotating the role is what creates one),
    and `SetValue` on it is `put_accValue` into the same void the proxy's
    Invoke goes into.
    """

    ProviderDescription = _TK_DESCRIPTION
    FrameworkId = _TK_FRAMEWORK

    def __init__(self, journal: JournallingPointer) -> None:
        self._journal = journal
        self.BoundingRectangle = _CONTROL_RECTANGLE

    def GetPattern(self, patternId: int) -> ProxiedTextBox:
        return self

    def SetValue(self, value: str) -> None:
        self._journal.acts.append(f"set the value to {value!r}")

    def SendKeys(self, text: str, charMode: bool = True) -> None:
        self._journal.keys(text)


class RecordingWindow:
    """Test double: a window that remembers being brought to the front.

    Answers True the way `SetActive` does when `SetForegroundWindow` worked:
    the answer is the whole point of asking, and a double that returned nothing
    would stand for a window whose position on screen is unknown.
    """

    def __init__(self) -> None:
        self.activations = 0

    def SetActive(self) -> bool:
        self.activations += 1
        return True


class WindowThatStaysBehind:
    """Test double: a window Windows would not bring to the front.

    Nothing exotic about it. The foreground lock bites for entirely ordinary
    reasons (another application called `LockSetForegroundWindow`, or simply
    got there first) with no integrity level involved, and `SetActive` then
    answers False having done nothing.

    It still answers for its own caption, which is what tells it apart from a
    window whose application has exited: that one declines to come forward too,
    and raises rather than naming itself.
    """

    Name = "pytest-uia WinForms Fixture"

    def SetActive(self) -> bool:
        return False


class RecordingPointer:
    """Test double: a mouse that remembers where it was aimed."""

    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))


class RefusedPointer:
    """Test double: the mouse of a desktop dropping this process's input."""

    def click(self, x: int, y: int) -> None:
        raise InputRefused("the foreground is held by 'GameInputServiceWindow'")


def test_clicking_a_control_with_no_invoke_pattern_falls_back_to_the_mouse() -> None:
    # Given a control that exposes no pattern, in a window that is not in front
    control = PatternlessControl()
    window = RecordingWindow()
    pointer = RecordingPointer()
    element = UiaElement(control, window, pointer=pointer)

    # When the test clicks it
    element.click()

    # Then the window came forward first, so the pointer landed on the control
    assert window.activations == 1, (
        "a mouse click on a background window hits whatever is covering it"
    )
    assert pointer.clicks == [_ITS_CENTRE], (
        "the pointer should jump to the middle of the control, not slide there"
    )


def test_clicking_a_control_whose_invoke_pattern_fails_falls_back_to_the_mouse() -> (
    None
):
    # Given a control that advertises Invoke but whose provider refuses the call
    control = FailingInvokeControl()
    pointer = RecordingPointer()
    element = UiaElement(control, RecordingWindow(), pointer=pointer)

    # When the test clicks it
    element.click()

    # Then the refusal is absorbed and the click still happens
    assert pointer.clicks == [_ITS_CENTRE], (
        "a provider that fails Invoke should not fail the test's click"
    )


def test_a_control_served_by_the_msaa_proxy_is_clicked_with_the_mouse_rather_than_invoked() -> (
    None
):
    # Given a control the generic MSAA proxy speaks for, advertising Invoke
    control = ProxiedControl()
    pointer = RecordingPointer()
    element = UiaElement(control, RecordingWindow(), pointer=pointer)

    # When the test clicks it
    element.click()

    # Then the pattern was never asked, because it would have said yes and done
    # nothing, and the mouse did the work instead
    assert control.invocations == 0, (
        "an Invoke the proxy only pretends to support has to be skipped, not "
        "tried: it succeeds, and the application never hears about it"
    )
    assert pointer.clicks == [_ITS_CENTRE], (
        "synthesised mouse input is the only thing that reaches an owner-drawn "
        "widget the proxy is inventing patterns for"
    )


def test_a_control_served_by_a_real_provider_is_invoked_and_never_touched_by_the_mouse() -> (
    None
):
    # Given a WinForms control, served by the same generic proxy, and backed
    # by a framework that honours the call anyway
    control = WinFormsControl()
    pointer = RecordingPointer()
    element = UiaElement(control, RecordingWindow(), pointer=pointer)

    # When the test clicks it
    element.click()

    # Then it went through the pattern, which needs no focus and steals none
    assert control.invocations == 1, (
        "the proxy marker cannot be the whole rule: WinForms reports it too, "
        "and stripping Invoke from a provider that honours it trades a silent "
        "no-op for a mouse the desktop is free to refuse"
    )
    assert pointer.clicks == [], (
        "nothing that can be invoked should ever be touched by the mouse"
    )


class TogglingCheckbox(PatternlessControl):
    """Test double: a provider-served checkbox, Toggle offered and Invoke absent."""

    ProviderDescription = _REAL_PROVIDER_DESCRIPTION
    FrameworkId = "Win32"

    def __init__(self) -> None:
        super().__init__()
        self.toggles = 0

    def GetPattern(self, patternId: int) -> TogglingCheckbox | None:
        if patternId == auto.PatternId.TogglePattern:
            return self
        return None

    def Toggle(self) -> None:
        self.toggles += 1


class SelectableRadio(PatternlessControl):
    """Test double: a provider-served radio, SelectionItem offered and Invoke absent."""

    ProviderDescription = _REAL_PROVIDER_DESCRIPTION
    FrameworkId = "Win32"

    def __init__(self) -> None:
        super().__init__()
        self.selections = 0

    def GetPattern(self, patternId: int) -> SelectableRadio | None:
        if patternId == auto.PatternId.SelectionItemPattern:
            return self
        return None

    def Select(self) -> None:
        self.selections += 1


class ProxiedToggle(TogglingCheckbox):
    """Test double: a Toggle the generic MSAA proxy is inventing."""

    ProviderDescription = _TK_DESCRIPTION
    FrameworkId = _TK_FRAMEWORK


class FailingToggle(TogglingCheckbox):
    """Test double: a checkbox that advertises Toggle and then refuses it."""

    def Toggle(self) -> None:
        raise _provider_refuses()


def test_a_checkbox_offering_toggle_instead_of_invoke_is_toggled_never_moused() -> None:
    # Given a checkbox whose provider offers Toggle and no Invoke at all,
    # which is what a provider-served Tk checkbox measures as
    control = TogglingCheckbox()
    pointer = RecordingPointer()
    element = UiaElement(control, RecordingWindow(), pointer=pointer)

    # When the test clicks it
    element.click()

    # Then toggling is what the click became: it is what a click means to the
    # one control type that answers this way, and it needs no focus at all
    assert control.toggles == 1, "the Toggle the provider honours was never asked"
    assert pointer.clicks == [], (
        "nothing that can be driven through a pattern should be touched by the mouse"
    )


def test_a_radio_offering_selection_instead_of_invoke_is_selected_never_moused() -> (
    None
):
    # Given a radio whose provider offers SelectionItem and no Invoke,
    # which is what a provider-served Tk radio measures as
    control = SelectableRadio()
    pointer = RecordingPointer()
    element = UiaElement(control, RecordingWindow(), pointer=pointer)

    # When the test clicks it
    element.click()

    # Then selecting is what the click became
    assert control.selections == 1, "the Select the provider honours was never asked"
    assert pointer.clicks == []


def test_a_toggle_the_msaa_proxy_invents_is_skipped_for_the_mouse() -> None:
    # Given a checkbox the generic proxy speaks for, advertising Toggle
    control = ProxiedToggle()
    pointer = RecordingPointer()
    element = UiaElement(control, RecordingWindow(), pointer=pointer)

    # When the test clicks it
    element.click()

    # Then the state patterns obey the same trust rule as Invoke: a call the
    # proxy would accept and drop is never made, and the mouse does the work
    assert control.toggles == 0, (
        "a Toggle the proxy only pretends to support has to be skipped, not tried"
    )
    assert pointer.clicks == [_ITS_CENTRE]


def test_a_toggle_the_provider_refuses_falls_back_to_the_mouse() -> None:
    # Given a checkbox that advertises Toggle and refuses the call
    control = FailingToggle()
    pointer = RecordingPointer()
    element = UiaElement(control, RecordingWindow(), pointer=pointer)

    # When the test clicks it
    element.click()

    # Then the refusal is absorbed and the click still happens
    assert pointer.clicks == [_ITS_CENTRE], (
        "a provider that fails Toggle should not fail the test's click"
    )


class ScrollableOffscreenRow(PatternlessControl):
    """Test double: an offscreen row whose provider can put it on screen."""

    IsOffscreen = True

    def GetPattern(self, patternId: int) -> ScrollableOffscreenRow | None:
        if patternId == auto.PatternId.ScrollItemPattern:
            return self
        return None

    def ScrollIntoView(self) -> None:
        self.IsOffscreen = False


class RowThatOnlyPretendsToScroll(ScrollableOffscreenRow):
    """Test double: a ScrollIntoView that returns cleanly and moves nothing."""

    def ScrollIntoView(self) -> None:
        return


def test_an_offscreen_row_is_scrolled_into_view_through_the_pattern() -> None:
    # Given a row in the tree with no pixels, whose provider can scroll
    control = ScrollableOffscreenRow()
    element = UiaElement(control, RecordingWindow())

    # When the test scrolls it into view
    element.scroll_into_view()

    # Then the provider did the moving: no focus, no foreground, no input
    assert control.IsOffscreen is False


def test_a_visible_control_with_no_scroll_pattern_needs_no_scrolling() -> None:
    # Given a control already on screen, offering no ScrollItemPattern
    element = UiaElement(PatternlessControl(), RecordingWindow())

    # When the test scrolls it into view
    element.scroll_into_view()

    # Then the goal state already held, and holding it is the whole contract


def test_an_offscreen_control_with_no_scroll_pattern_reports_still_offscreen() -> None:
    # Given an offscreen control whose provider offers no way to scroll it
    control = PatternlessControl()
    control.IsOffscreen = True
    element = UiaElement(control, RecordingWindow())

    # When the test scrolls it into view
    with pytest.raises(StillOffscreen) as failure:
        element.scroll_into_view()

    # Then the failure says what was missing, not merely that it failed
    assert "ScrollItemPattern" in str(failure.value)


def test_a_scroll_the_provider_fakes_is_caught_by_the_pixels_it_never_moved() -> None:
    # Given a provider whose ScrollIntoView returns cleanly and does nothing
    element = UiaElement(RowThatOnlyPretendsToScroll(), RecordingWindow())

    # When the test scrolls it into view
    with pytest.raises(StillOffscreen):
        element.scroll_into_view()

    # Then the postcondition caught the lie: this is why no trust rule is
    # needed here, the call is verified by the one thing it exists to change


def test_a_control_served_by_the_msaa_proxy_is_typed_into_by_clicking_it_first_then_typing() -> (
    None
):
    # Given a proxied edit control, advertising the value pattern it cannot
    # honour, and one journal recording everything done to it in order
    journal = JournallingPointer()
    element = UiaElement(ProxiedTextBox(journal), RecordingWindow(), pointer=journal)

    # When the test types into it
    element.type_text(_A_DRAFT)

    # Then the value pattern was left alone, and the caret was put where the
    # keys were about to land, a Tk widget owns focus within its toplevel
    # through Tk's own model, so Win32 focus on its child HWND is not focus,
    # and clicking it is the only thing that gives it the caret
    assert journal.acts == [f"clicked {_ITS_CENTRE}", f"typed {_A_DRAFT!r}"], (
        "an untrusted provider can be read but not driven, so typing into one "
        "has to go the same way OcrElement's does: click, then type"
    )


def test_reading_an_edit_control_whose_provider_offers_no_value_pattern_falls_back_to_its_name() -> (
    None
):
    # Given an edit control that is an edit control and nothing more
    element = UiaElement(UnbackedEditControl(), RecordingWindow())

    # When the test reads it
    read = element.read_text()

    # Then it answers with the only thing the control has to say about itself
    assert read == "Title", (
        "a missing pattern is a None, not an exception, so reading one used to "
        "raise an AttributeError past poll() and out to whoever ran the test"
    )


def test_an_edit_control_whose_value_is_empty_reads_as_empty_rather_than_as_its_label() -> (
    None
):
    # Given an annotated edit control with a value pattern and nothing in it
    element = UiaElement(EmptyEditControl(), RecordingWindow())

    # When the test reads it
    read = element.read_text()

    # Then the empty answer stands: the box really is empty, and its label's
    # name would be a confident report of text nobody ever typed
    assert read == "", (
        "an empty value is an answer; falling back on it would make an empty "
        "box read as 'Title' and a test asserting on that pass for the wrong "
        "reason"
    )


def test_a_mouse_fallback_the_desktop_refuses_is_reported_not_swallowed() -> None:
    # Given a control with no pattern, on a desktop refusing synthetic input
    element = UiaElement(
        PatternlessControl(), RecordingWindow(), pointer=RefusedPointer()
    )

    # When the test clicks it
    with pytest.raises(InputRefused):
        element.click()

    # Then the caller can retry, exactly as it does for an OCR-located click:
    # the accessibility tree protects Invoke, not the mouse behind it


def test_a_click_aimed_at_a_window_that_will_not_come_forward_is_refused() -> None:
    # Given a control with no pattern to invoke, in a window Windows keeps
    # behind whatever is currently in front
    pointer = RecordingPointer()
    element = UiaElement(PatternlessControl(), WindowThatStaysBehind(), pointer=pointer)

    # When the test clicks it
    with pytest.raises(InputRefused):
        element.click()

    # Then the mouse was never aimed at coordinates another application now
    # owns. The refusal is the same class the driver already retries, which is
    # the point: a foreground steal that loses a race is transient, and a click
    # delivered to the window covering this one is not recoverable at all
    assert pointer.clicks == [], (
        "a click on a window that is not in front presses whatever covers it, "
        "which is precisely the misdirected input this project refuses to let "
        "pass for a delivered one"
    )


def test_typing_into_a_window_that_will_not_come_forward_is_refused() -> None:
    # Given a control whose provider offers no value pattern, in a window
    # Windows keeps behind whatever is currently in front
    control = PatternlessControl()
    element = UiaElement(control, WindowThatStaysBehind())

    # When the test types into it
    with pytest.raises(InputRefused):
        element.type_text(_A_DRAFT)

    # Then the keys were never sent, because they land wherever the caret is
    # and the caret is in somebody else's window
    assert control.typed == [], (
        "keystrokes go to whatever window is in front, so typing into one that "
        "would not come forward types into another application"
    )


def test_typing_into_a_control_with_no_value_pattern_falls_back_to_the_keyboard() -> (
    None
):
    # Given an edit control whose provider offers no value pattern
    control = PatternlessControl()
    window = RecordingWindow()
    element = UiaElement(control, window)

    # When the test types into it
    element.type_text("Write the report")

    # Then the window came forward, so the keystrokes had somewhere to land
    assert window.activations == 1, (
        "keys go to whatever window is in front, not to the one under test"
    )
    assert control.typed == [("Write the report", True)], (
        "text must be typed character by character, not read as key names"
    )


def test_typing_into_a_control_whose_value_pattern_fails_falls_back_to_the_keyboard() -> (
    None
):
    # Given a read-only-ish control that advertises a value pattern and refuses it
    control = FailingValueControl()
    window = RecordingWindow()
    element = UiaElement(control, window)

    # When the test types into it
    element.type_text("Write the report")

    # Then the refusal is absorbed and the text is typed the slow way instead
    assert control.typed == [("Write the report", True)], (
        "a provider that refuses SetValue should not swallow the test's text"
    )
