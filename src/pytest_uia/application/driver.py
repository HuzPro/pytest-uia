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
    StillOffscreen,
    TextNeverSettled,
)
from pytest_uia.domain.locator import Element, Locator, ScopedLocator
from pytest_uia.domain.name_match import NameMatch
from pytest_uia.domain.query import Query, Role
from pytest_uia.domain.tree import DEFAULT_LIMITS, DumpLimits, Walk
from pytest_uia.domain.waiting import RetryPolicy, poll

DEFAULT_POLICY = RetryPolicy()

T = TypeVar("T")

# All of these mean "the screen is not ready yet", and all clear on their
# own: not painted yet, input dropped while another window held the
# foreground, a control still reading its pre-keystroke value, or a row a
# provider has not yet managed to scroll onto the screen.
_WORTH_ANOTHER_ATTEMPT = (
    ElementNotFound,
    InputRefused,
    StillOffscreen,
    TextNeverSettled,
)


def waiting_at_most(policy: RetryPolicy, timeout: float | None) -> RetryPolicy:
    """Narrow a policy to a caller's deadline, leaving the interval alone.

    How often to look is a property of how fast a desktop repaints; how long to
    keep looking is the caller's business.
    """
    if timeout is None:
        return policy
    return replace(policy, timeout=timeout)


class ElementQueries:
    """The query vocabulary every scope offers: a window, a dialog, an element.

    Template Method over `_element_for`: each subclass decides which locator a
    query is answered from, and that decision is the whole difference between
    searching a window and searching inside one row of it.
    """

    def button(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        return self._element_for(Role.BUTTON, name, timeout)

    def textbox(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        return self._element_for(Role.TEXTBOX, name, timeout)

    def text(
        self, value: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        return self._element_for(Role.TEXT, value, timeout)

    def tab(self, name: str | NameMatch, *, timeout: float | None = None) -> UIElement:
        """One tab of a notebook, which `click()` selects.

        The control a test reaches before it can reach anything on the page
        behind it: a notebook shows one page at a time and unmaps the rest, so
        until this can be clicked, a test can only read whichever page the
        application happened to open with.
        """
        return self._element_for(Role.TAB, name, timeout)

    # Every other kind of control, one call each. Spelled out rather than
    # generated from the role table: these are the whole vocabulary a test
    # author has, and a name an editor cannot complete is a name nobody finds.
    def checkbox(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        return self._element_for(Role.CHECKBOX, name, timeout)

    def radio(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        return self._element_for(Role.RADIO, name, timeout)

    def slider(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        return self._element_for(Role.SLIDER, name, timeout)

    def spinbox(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        return self._element_for(Role.SPINBOX, name, timeout)

    def combobox(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        return self._element_for(Role.COMBOBOX, name, timeout)

    def listbox(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        """A list. Rows a provider exposes are `list_item`; Tk's are not in the tree."""
        return self._element_for(Role.LISTBOX, name, timeout)

    def tree(self, name: str | NameMatch, *, timeout: float | None = None) -> UIElement:
        """A tree. Nodes a provider exposes are `tree_item`; Tk's are not in the tree."""
        return self._element_for(Role.TREE, name, timeout)

    def progressbar(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        return self._element_for(Role.PROGRESSBAR, name, timeout)

    def scrollbar(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        return self._element_for(Role.SCROLLBAR, name, timeout)

    def group(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        """A frame or labelled group; the usual scope a row query starts from."""
        return self._element_for(Role.GROUP, name, timeout)

    def image(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        """A picture or drawing surface. What it *shows* is paint: see the OCR path."""
        return self._element_for(Role.IMAGE, name, timeout)

    def split_button(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        """A button with a menu attached."""
        return self._element_for(Role.SPLIT_BUTTON, name, timeout)

    def separator(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        return self._element_for(Role.SEPARATOR, name, timeout)

    def thumb(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        """A drag handle: a `ttk.Sizegrip`, or the thumb of a scrollbar."""
        return self._element_for(Role.THUMB, name, timeout)

    def tab_strip(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        """The strip a notebook's tabs sit on. Its tabs are `app.tab(...)`."""
        return self._element_for(Role.TAB_STRIP, name, timeout)

    def list_item(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        """One row of a list, where the list's provider exposes its rows."""
        return self._element_for(Role.LIST_ITEM, name, timeout)

    def tree_item(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        """One node of a tree, where the tree's provider exposes its nodes."""
        return self._element_for(Role.TREE_ITEM, name, timeout)

    def menu_item(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        return self._element_for(Role.MENU_ITEM, name, timeout)

    def data_item(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        """One cell or row of a data grid."""
        return self._element_for(Role.DATA_ITEM, name, timeout)

    def hyperlink(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        return self._element_for(Role.HYPERLINK, name, timeout)

    def document(
        self, name: str | NameMatch, *, timeout: float | None = None
    ) -> UIElement:
        """A document surface: what a browser calls its whole web area."""
        return self._element_for(Role.DOCUMENT, name, timeout)

    def _element_for(
        self, role: Role, name: str | NameMatch, timeout: float | None
    ) -> UIElement:
        raise NotImplementedError


class UIElement(ElementQueries):
    """Proxy for an on-screen element, standing in for one that may not exist yet.

    Holds the query rather than the control, and resolves it again on every
    interaction: a cached control goes stale on any repaint. Resolution is
    where the implicit wait lives, and the only place it lives.

    Carries the query vocabulary itself, scoped to its own inside: the element
    `app.group("record 23256").text("1m 8s")` means is searched for under the
    row, resolved fresh alongside it on every look.
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

    def is_checked(self) -> bool:
        """Whether a checkbox or radio button is currently on.

        A read, so it is never gated on provider trust: only *actions* are
        guesses about a control the MSAA proxy cannot really reach.
        """
        return self._resolve().is_checked()

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

    def scroll_into_view(self, *, timeout: float | None = None) -> UIElement:
        """Put the element's pixels on screen, where a click can land.

        Provider calls only: no mouse wheel, no keyboard, no foreground change.
        """
        self._within_the_implicit_wait(
            lambda: self._one_that_matches().scroll_into_view(), timeout
        )
        return self

    def wait_until_text_is(
        self, expected: str, *, timeout: float | None = None
    ) -> UIElement:
        self._within_the_implicit_wait(lambda: self._one_that_reads(expected), timeout)
        return self

    def _one_that_reads(self, expected: str) -> Element:
        # Resolved inside the wait rather than once in front of it: a control
        # held across the polls goes on reading the replaced value. A control
        # not there yet stays an ElementNotFound; both latenesses share this
        # deadline.
        element = self._one_that_matches()
        read = element.read_text()
        if read != expected:
            raise TextNeverSettled(f"{self._query} -- reads {read!r}, not {expected!r}")
        return element

    def _one_that_is_painted(self) -> Element:
        # Being in the tree is not being on screen: a WinForms control exists
        # for a while before it has any pixels, and a click aimed at it then
        # lands on whatever is underneath.
        element = self._locator.find(self._query)
        if not element.is_visible():
            raise ElementNotFound(f"{self._query} -- found, but not yet painted")
        return element

    def _resolve(self, timeout: float | None = None) -> Element:
        return self._within_the_implicit_wait(self._one_that_matches, timeout)

    def _one_that_matches(self) -> Element:
        return self._locator.find(self._query)

    def _element_for(
        self, role: Role, name: str | NameMatch, timeout: float | None
    ) -> UIElement:
        return UIElement(
            Query(role=role, name=name),
            ScopedLocator(self._locator, self._query),
            waiting_at_most(self._policy, timeout),
            clock=self._clock,
            sleep=self._sleep,
        )

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
        except StillOffscreen as offscreen:
            raise StillOffscreen(
                f"still offscreen after {policy.timeout}s; {offscreen}"
            ) from offscreen


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


class ElementSource(ElementQueries):
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

        Deliberately does not print: under pytest that would vanish into
        captured output anyway. `print(app.dump())` with `-s`, or the failure
        message, or the command line.
        """
        return dump_of(
            self._tree.walk(limits), inside_the_dialog=self._inside_the_dialog
        )

    def _element_for(
        self, role: Role, name: str | NameMatch, timeout: float | None
    ) -> UIElement:
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
        whichever the tree offers first, which is the whole ambiguity a wizard
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

    Deliberately not an App: a dialog has no process of its own to end, so
    `close()` and `pid` would be borrowed semantics. What it does share is the
    way in, which is why both are ElementSources.
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
