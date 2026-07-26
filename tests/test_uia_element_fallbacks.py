"""Behavioral spec for what UiaElement does when the UIA patterns let it down.

Plenty of apps worth testing expose a half-built accessibility tree: a control
with no InvokePattern, an edit box whose provider fails the call. These specs
use doubles, because a control that misbehaves exactly when asked is not
something a real fixture app can offer.

The doubles carry uiautomation's own PascalCase method names on purpose: they
stand in for its Control objects, and renaming them would hide that.
"""

from __future__ import annotations

import sys

import pytest
from comtypes import COMError

from pytest_uia.adapters.uia import UiaElement

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="UI Automation is a Windows API",
)

_E_FAIL = -2147467259


def _provider_refuses() -> COMError:
    """A fresh refusal every time.

    One shared exception instance accumulates the traceback of every raise it
    has ever been through, which makes the next failure report point at the
    previous test.
    """
    return COMError(_E_FAIL, "Unspecified error", (None,) * 5)


class PatternlessControl:
    """Test double: a control whose provider supports no pattern at all."""

    def __init__(self) -> None:
        self.clicks: list[bool] = []
        self.typed: list[tuple[str, bool]] = []

    def GetPattern(self, patternId: int) -> None:
        return None

    def Click(self, simulateMove: bool = True) -> None:
        self.clicks.append(simulateMove)

    def SendKeys(self, text: str, charMode: bool = True) -> None:
        self.typed.append((text, charMode))


class FailingInvokeControl(PatternlessControl):
    """Test double: a control that advertises Invoke and then refuses it."""

    def GetPattern(self, patternId: int) -> FailingInvokeControl:
        return self

    def Invoke(self) -> None:
        raise _provider_refuses()


class FailingValueControl(PatternlessControl):
    """Test double: a control that advertises a value pattern and refuses it."""

    def GetPattern(self, patternId: int) -> FailingValueControl:
        return self

    def SetValue(self, value: str) -> None:
        raise _provider_refuses()


class RecordingWindow:
    """Test double: a window that remembers being brought to the front."""

    def __init__(self) -> None:
        self.activations = 0

    def SetActive(self) -> None:
        self.activations += 1


def test_clicking_a_control_with_no_invoke_pattern_falls_back_to_the_mouse() -> None:
    # Given a control that exposes no pattern, in a window that is not in front
    control = PatternlessControl()
    window = RecordingWindow()
    element = UiaElement(control, window)

    # When the test clicks it
    element.click()

    # Then the window came forward first, so the pointer landed on the control
    assert window.activations == 1, (
        "a mouse click on a background window hits whatever is covering it"
    )
    assert control.clicks == [False], (
        "the pointer should jump to the control, not slide across other windows"
    )


def test_clicking_a_control_whose_invoke_pattern_fails_falls_back_to_the_mouse() -> (
    None
):
    # Given a control that advertises Invoke but whose provider refuses the call
    control = FailingInvokeControl()
    window = RecordingWindow()
    element = UiaElement(control, window)

    # When the test clicks it
    element.click()

    # Then the refusal is absorbed and the click still happens
    assert control.clicks == [False], (
        "a provider that fails Invoke should not fail the test's click"
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
