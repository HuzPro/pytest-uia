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
from typing import Protocol

from pytest_uia.domain.errors import ElementNotFound
from pytest_uia.domain.locator import Element, Locator
from pytest_uia.domain.query import Query, Role
from pytest_uia.domain.waiting import RetryPolicy, poll

DEFAULT_POLICY = RetryPolicy()


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
        self._resolve().click()

    def type_text(self, text: str) -> None:
        self._resolve().type_text(text)

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
        self._keep_looking_for(self._one_that_is_painted, timeout)
        return self

    def _one_that_is_painted(self) -> Element:
        # Being in the tree is not being on screen: a WinForms control exists
        # for a while before it has any pixels, and a click aimed at it then
        # lands on whatever is underneath.
        element = self._locator.find(self._query)
        if not element.is_visible():
            raise ElementNotFound(f"{self._query} — found, but not yet painted")
        return element

    def _resolve(self, timeout: float | None = None) -> Element:
        return self._keep_looking_for(self._one_that_matches, timeout)

    def _one_that_matches(self) -> Element:
        return self._locator.find(self._query)

    def _keep_looking_for(
        self, look: Callable[[], Element], timeout: float | None
    ) -> Element:
        return poll(
            look,
            waiting_at_most(self._policy, timeout),
            retry_on=ElementNotFound,
            clock=self._clock,
            sleep=self._sleep,
        )


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
