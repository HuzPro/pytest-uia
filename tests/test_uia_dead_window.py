"""Behavioral spec for what the adapter says once the application has exited.

Doubles, because a control that answers nothing at all is not something a live
fixture app can be asked to be. They carry `uiautomation`'s own PascalCase
names on purpose: they stand in for its Controls.
"""

from __future__ import annotations

import sys

import pytest
from comtypes import COMError

from pytest_uia.adapters.uia import UiaElement, UiaWindow
from pytest_uia.domain.errors import ElementNotFound, WindowNotFound

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="UI Automation is a Windows API",
)

# The HRESULT the fixture app really answered with once it had been killed,
# rather than a plausible-looking one.
_THE_PROVIDER_IS_GONE = -2147220991
_ITS_MESSAGE = "An event was unable to invoke any of the subscribers"

_A_DRAFT = "Write the report"


def _the_provider_is_gone() -> COMError:
    """A fresh refusal every time.

    One shared exception instance accumulates the traceback of every raise it
    has ever been through, which makes the next failure report point at the
    previous test.
    """
    return COMError(_THE_PROVIDER_IS_GONE, _ITS_MESSAGE, (None,) * 5)


class DeadControl:
    """Test double: a control whose application exited underneath it.

    Every property is served by a provider that is no longer there, so every
    one of them raises instead of answering, including the name, which is what
    makes a failure message about this window its own kind of problem.
    """

    @property
    def Name(self) -> str:
        raise _the_provider_is_gone()

    @property
    def ProcessId(self) -> int:
        raise _the_provider_is_gone()

    @property
    def ControlType(self) -> int:
        raise _the_provider_is_gone()

    @property
    def BoundingRectangle(self) -> object:
        raise _the_provider_is_gone()

    @property
    def IsOffscreen(self) -> bool:
        raise _the_provider_is_gone()

    @property
    def ProviderDescription(self) -> str:
        raise _the_provider_is_gone()

    def GetPattern(self, patternId: int) -> object:
        raise _the_provider_is_gone()

    def SetActive(self) -> bool:
        raise _the_provider_is_gone()

    def SendKeys(self, text: str, charMode: bool = True) -> None:
        raise _the_provider_is_gone()


def _an_element_of_a_dead_application() -> UiaElement:
    return UiaElement(DeadControl(), DeadControl())


def test_reading_an_element_whose_application_has_exited_is_reported_as_a_miss() -> (
    None
):
    # Given an element of an application that is no longer running
    element = _an_element_of_a_dead_application()

    # When the test reads it
    with pytest.raises(ElementNotFound) as gone:
        element.read_text()

    # Then it is the domain's own kind of absence, which the driver retries and
    # `exists()` can turn into an answer, not an HRESULT out of comtypes
    assert "gone" in str(gone.value), (
        f"the reader has to be told the window went away: {gone.value}"
    )


def test_asking_a_dead_elements_visibility_is_reported_as_a_miss() -> None:
    # Given an element of an application that is no longer running
    element = _an_element_of_a_dead_application()

    # When the test asks whether the user could see it
    with pytest.raises(ElementNotFound):
        element.is_visible()

    # Then a window that is gone is answered as absence rather than as a crash


def test_clicking_an_element_whose_application_has_exited_is_reported_as_a_miss() -> (
    None
):
    # Given an element of an application that is no longer running
    element = _an_element_of_a_dead_application()

    # When the test clicks it
    with pytest.raises(ElementNotFound):
        element.click()

    # Then the implicit wait can retry it and then fail with an honest domain
    # error, which is the whole reason the retry loop distinguishes error types


def test_typing_into_an_element_whose_application_has_exited_is_reported_as_a_miss() -> (
    None
):
    # Given an element of an application that is no longer running
    element = _an_element_of_a_dead_application()

    # When the test types into it
    with pytest.raises(ElementNotFound):
        element.type_text(_A_DRAFT)

    # Then it is a miss, not a COMError raised past a driver that never catches


def test_the_title_of_a_window_whose_application_has_exited_says_the_window_is_gone() -> (
    None
):
    # Given the window of an application that is no longer running
    window = UiaWindow(DeadControl())

    # When the test asks what it is called
    with pytest.raises(WindowNotFound) as gone:
        _ = window.title

    # Then it is a WindowNotFound and not an HRESULT. `app.title` is the
    # simplest question in the API, and it was the one that raised the ugliest
    # answer the moment the application it was about stopped existing
    assert "gone" in str(gone.value), (
        f"the reader has to be told the window went away: {gone.value}"
    )


def test_closing_a_window_whose_application_has_exited_says_the_window_is_gone() -> (
    None
):
    # Given the window of an application that is no longer running
    window = UiaWindow(DeadControl())

    # When teardown asks it to close
    with pytest.raises(WindowNotFound):
        window.close()

    # Then the session's teardown sees a domain error it can report, rather than
    # a COMError it has to guess the meaning of
