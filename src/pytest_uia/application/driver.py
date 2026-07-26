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

from pytest_uia.domain.dump import Dump, dump_of
from pytest_uia.domain.errors import (
    DialogNotFound,
    DialogStillOpen,
    ElementNotFound,
    InputRefused,
    TextNeverSettled,
)
from pytest_uia.domain.locator import Element, Locator
from pytest_uia.domain.query import Query, Role
from pytest_uia.domain.tree import DEFAULT_LIMITS, DumpLimits, Walk
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
        except ElementNotFound as miss:
            # Same bargain, and the symmetry matters: without the deadline, a
            # control that was never going to appear reads exactly like one
            # that was given a tenth of a second to.
            raise ElementNotFound(
                f"not on screen after {policy.timeout}s; {miss}"
            ) from miss
        except TextNeverSettled as unsettled:
            # And the same again for the value that never arrived, so that no
            # failure this method raises leaves out how long it was waited for.
            raise TextNeverSettled(
                f"still not reading it after {policy.timeout}s; {unsettled}"
            ) from unsettled


class Window(Protocol):
    """The slice of a top-level window the driver depends on."""

    @property
    def title(self) -> str: ...

    @property
    def contents(self) -> Locator: ...

    def dialog_titled(self, title: str) -> Window: ...

    def close(self) -> None: ...


class WindowTree(Protocol):
    """The one thing a dump needs of a window: the controls under it.

    Deliberately not folded into `Window`. That port is also depended on by the
    session, which has no business with a dump, and a dump has no business with
    `close()`.
    """

    def walk(self, limits: DumpLimits) -> Walk: ...


class RunningProcess(Protocol):
    """The slice of a launched process the driver depends on."""

    @property
    def pid(self) -> int: ...

    def terminate(self) -> None: ...


class ElementSource:
    """The widgets of exactly one window, and the implicit wait they inherit.

    Shared by App and Dialog so that `button`, `textbox` and `text` mean the
    same thing in both. The only difference between the two is which window's
    subtree their queries are answered from, and that difference is the whole
    point of `App.dialog`.
    """

    def __init__(
        self,
        locator: Locator,
        policy: RetryPolicy = DEFAULT_POLICY,
        *,
        tree: WindowTree,
        inside_the_dialog: str = "",
    ) -> None:
        self._locator = locator
        self._policy = policy
        self._tree = tree
        # The caption, not a rendered call: how a scope is spelled is the
        # domain's business, and this layer has no quoting rules of its own.
        self._inside_the_dialog = inside_the_dialog

    def dump(self, *, limits: DumpLimits = DEFAULT_LIMITS) -> Dump:
        """Every control in this window, and the query that would find each one.

        Deliberately does not print. Printing from a library call is a side
        effect a diagnostic should not have, and under pytest it would vanish
        into captured output anyway — so `print(app.dump())` with `-s`, or the
        failure message, or the command line.
        """
        return dump_of(
            self._tree.walk(limits), inside_the_dialog=self._inside_the_dialog
        )

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


class App(ElementSource):
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
        super().__init__(locator, policy, tree=window)
        self._window = window
        self._process = process

    def dialog(self, title: str, *, timeout: float | None = None) -> Dialog:
        """Address a child window by its caption, and search only inside it.

        Scoped by searching from the dialog's own control rather than from the
        main window: the main window's subtree *contains* the dialog, so a
        query answered there reaches both windows' controls and returns
        whichever the tree offers first — which is the whole ambiguity a wizard
        reusing captions runs into.

        Waited for, because a dialog opens on the application's own message
        pump: the click that asks for one has returned long before the window
        exists.
        """
        dialog_window = self._child_window_titled(
            title, waiting_at_most(self._policy, timeout)
        )
        return Dialog(
            dialog_window.contents,
            title=title,
            opened_over=self._window,
            # The dialog's own window, never the one underneath: a dialog's
            # dump has to cover exactly the subtree its own queries search.
            tree=dialog_window,
            policy=self._policy,
        )

    def has_dialog(self, title: str, *, timeout: float | None = None) -> bool:
        """Answer instead of raising, so a test can assert either way."""
        try:
            self.dialog(title, timeout=timeout)
        except DialogNotFound:
            return False
        return True

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

    def _child_window_titled(self, title: str, policy: RetryPolicy) -> Window:
        try:
            return poll(
                lambda: self._window.dialog_titled(title),
                policy,
                retry_on=DialogNotFound,
            )
        except DialogNotFound as never_opened:
            # The window that was searched knows where it looked; only this
            # knows how long the test was willing to wait, and both belong in
            # the report.
            raise DialogNotFound(
                f"no dialog titled {title!r} opened within {policy.timeout}s; "
                f"{never_opened}"
            ) from never_opened

    def _ask_the_window_to_close(self) -> None:
        # Best effort by design, and deliberately blind to what went wrong. A
        # window whose provider has already died raises here, and that is
        # precisely the run where the process behind it most needs killing.
        with suppress(Exception):
            self._window.close()


class Dialog(ElementSource):
    """A child window a test addressed by caption, and the queries scoped to it.

    Deliberately not an App. A dialog has no process of its own to end and no
    lifecycle a test may take over — `close()` and `pid` would be borrowed
    semantics that fit the window underneath it and not this one. What it does
    share is the way in, which is why both are ElementSources.
    """

    def __init__(
        self,
        locator: Locator,
        *,
        title: str,
        opened_over: Window,
        tree: WindowTree,
        policy: RetryPolicy = DEFAULT_POLICY,
    ) -> None:
        super().__init__(locator, policy, tree=tree, inside_the_dialog=title)
        self._title = title
        self._opened_over = opened_over

    def wait_closed(self, *, timeout: float | None = None) -> None:
        """Block until the application has taken this dialog off screen."""
        policy = waiting_at_most(self._policy, timeout)
        try:
            poll(self._no_longer_on_screen, policy, retry_on=DialogStillOpen)
        except DialogStillOpen as lingering:
            raise DialogStillOpen(f"{lingering} after {policy.timeout}s") from lingering

    def _no_longer_on_screen(self) -> None:
        # Asked of the window underneath rather than of the control this dialog
        # was found through: a window that has been destroyed leaves a handle
        # whose every property access fails, and "it raised" is not the same
        # answer as "it is gone".
        try:
            self._opened_over.dialog_titled(self._title)
        except DialogNotFound:
            return
        raise DialogStillOpen(f"dialog {self._title!r} is still on screen")
