"""The fluent surface a test drives an application through.

Composes the domain's locator chain and waiting core with whatever adapters a
session wired up. Imports pytest nowhere: the driver is usable from a plain
script, and `hooks.py` only has to hand it a session.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace
from typing import Protocol, TypeVar

from pytest_uia.domain.errors import ElementNotFound, InputRefused, TextNeverSettled
from pytest_uia.domain.locator import Element, Locator
from pytest_uia.domain.query import Query, Role
from pytest_uia.domain.waiting import RetryPolicy, poll

DEFAULT_POLICY = RetryPolicy()

T = TypeVar("T")

# All three mean "the screen is not ready yet", and all three clear on their
# own. A control that has not painted is the obvious one; a desktop that is
# dropping this process's synthetic input because a higher-integrity window
# holds the foreground is the one that used to make gui suites flaky, because it
# looked exactly like a click the application had ignored; and a control still
# reading the value it showed before the keys landed is the same lateness one
# property further in.
_WORTH_ANOTHER_ATTEMPT = (ElementNotFound, InputRefused, TextNeverSettled)


def waiting_at_most(policy: RetryPolicy, timeout: float | None) -> RetryPolicy:
    """Narrow a policy to a caller's deadline, leaving the interval alone.

    How often to look is a property of how fast a desktop repaints; how long to
    keep looking is the caller's business.
    """
    if timeout is None:
        return policy
    return replace(policy, timeout=timeout)


class UIElement:
    """Proxy for an on-screen element, standing in for one that may not exist yet.

    Holds the query rather than the control, and resolves it again on every
    interaction. Caching the control instead was the motivating failure: a
    WinForms status label that had been repainted, or a Tk dialog rebuilt after
    a redraw, hands back a stale UIA element whose every property access fails
    long after the test had legitimately found it.

    Resolution is where the implicit wait lives, and the only place it lives:
    locators look once, and this retries them.
    """

    def __init__(
        self,
        query: Query,
        locator: Locator,
        policy: RetryPolicy = DEFAULT_POLICY,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._query = query
        self._locator = locator
        self._policy = policy
        self._clock = clock
        self._sleep = sleep

    def click(self) -> None:
        # Resolving and clicking share one deadline rather than nesting two:
        # the element is looked up again on every attempt, so a refused click
        # costs a fresh lookup and never twice the configured wait.
        self._within_the_implicit_wait(lambda: self._one_that_matches().click())

    def type_text(self, text: str) -> None:
        self._within_the_implicit_wait(lambda: self._one_that_matches().type_text(text))

    def read_text(self) -> str:
        return self._resolve().read_text()

    def exists(self, *, timeout: float | None = None) -> bool:
        """Answer instead of raising, so a test can assert either way."""
        try:
            self._resolve(timeout)
        except ElementNotFound:
            return False
        return True

    def wait_visible(self, *, timeout: float | None = None) -> UIElement:
        self._within_the_implicit_wait(self._one_that_is_painted, timeout)
        return self

    def wait_until_text_is(
        self, expected: str, *, timeout: float | None = None
    ) -> UIElement:
        self._within_the_implicit_wait(lambda: self._one_that_reads(expected), timeout)
        return self

    def _one_that_reads(self, expected: str) -> Element:
        # Resolved inside the wait rather than once in front of it: a control
        # held across the polls goes on reading the value the application has
        # already replaced, which is the exact lateness this method exists for.
        # A control that is not there yet stays an ElementNotFound, because the
        # click that sets a label's text is usually the one that creates it —
        # both kinds of lateness share this deadline, and each is still
        # reported as what it is.
        element = self._one_that_matches()
        read = element.read_text()
        if read != expected:
            raise TextNeverSettled(f"{self._query} — reads {read!r}, not {expected!r}")
        return element

    def _one_that_is_painted(self) -> Element:
        # Being in the tree is not being on screen: a WinForms control exists
        # for a while before it has any pixels, and a click aimed at it then
        # lands on whatever is underneath.
        element = self._locator.find(self._query)
        if not element.is_visible():
            raise ElementNotFound(f"{self._query} — found, but not yet painted")
        return element

    def _resolve(self, timeout: float | None = None) -> Element:
        return self._within_the_implicit_wait(self._one_that_matches, timeout)

    def _one_that_matches(self) -> Element:
        return self._locator.find(self._query)

    def _within_the_implicit_wait(
        self, attempt: Callable[[], T], timeout: float | None = None
    ) -> T:
        policy = waiting_at_most(self._policy, timeout)
        try:
            return poll(
                attempt,
                policy,
                retry_on=_WORTH_ANOTHER_ATTEMPT,
                clock=self._clock,
                sleep=self._sleep,
            )
        except InputRefused as refusal:
            # The adapter knows who is in the way; only this knows how long the
            # test was willing to wait for them, and both belong in the report.
            raise InputRefused(
                f"synthetic mouse input was refused for {policy.timeout}s; {refusal}"
            ) from refusal


class Window(Protocol):
    """The slice of a top-level window the driver depends on."""

    @property
    def title(self) -> str: ...

    def close(self) -> None: ...


class RunningProcess(Protocol):
    """The slice of a launched process the driver depends on."""

    @property
    def pid(self) -> int: ...

    def terminate(self) -> None: ...


class App:
    """Facade over one running application: its process, its window, the way in.

    A test says `app.button("New Task").click()` and never learns that a
    locator chain, a retry policy and an accessibility tree were involved.
    """

    def __init__(
        self,
        locator: Locator,
        *,
        window: Window,
        process: RunningProcess,
        policy: RetryPolicy = DEFAULT_POLICY,
    ) -> None:
        self._locator = locator
        self._window = window
        self._process = process
        self._policy = policy

    def button(self, name: str, *, timeout: float | None = None) -> UIElement:
        return self._element_for(Role.BUTTON, name, timeout)

    def textbox(self, name: str, *, timeout: float | None = None) -> UIElement:
        return self._element_for(Role.TEXTBOX, name, timeout)

    def text(self, value: str, *, timeout: float | None = None) -> UIElement:
        return self._element_for(Role.TEXT, value, timeout)

    def _element_for(self, role: Role, name: str, timeout: float | None) -> UIElement:
        return UIElement(
            Query(role=role, name=name),
            self._locator,
            waiting_at_most(self._policy, timeout),
        )

    @property
    def pid(self) -> int:
        return self._process.pid

    @property
    def title(self) -> str:
        return self._window.title

    def close(self) -> None:
        """Ask the app to go away, then make sure it did."""
        self._ask_the_window_to_close()
        self._process.terminate()

    def _ask_the_window_to_close(self) -> None:
        # Best effort by design, and deliberately blind to what went wrong. A
        # window whose provider has already died raises here, and that is
        # precisely the run where the process behind it most needs killing.
        with suppress(Exception):
            self._window.close()
