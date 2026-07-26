"""Behavioral spec for the fluent driver a test actually writes against.

Everything here runs against doubles: no window, no desktop, no waiting. The
driver's whole job is deciding *when* to ask a locator for an element and what
to do with the answer, and that decision is worth testing in milliseconds
rather than in seconds of real screen time.
"""

from __future__ import annotations

import pytest

from pytest_uia.application.driver import App, UIElement
from pytest_uia.domain.errors import ElementNotFound, InputRefused
from pytest_uia.domain.query import Query, Role
from pytest_uia.domain.waiting import RetryPolicy

NEW_TASK_BUTTON = Query(role=Role.BUTTON, name="New Task")
TITLE_TEXTBOX = Query(role=Role.TEXTBOX, name="Title")
TASK_CREATED_LABEL = Query(role=Role.TEXT, name="task created")

_DEFAULT_WAIT = RetryPolicy()

# What the pointer adapter raises: a bare reason the driver has to carry
# through, because it is the only thing that names the culprit.
_WHY_THE_DESKTOP_REFUSED = (
    "the foreground is held by 'GameInputServiceWindow' (pid 6680)"
)
_NEVER = 10_000


class RecordingControl:
    """Test double: an on-screen control that remembers what was done to it."""

    def __init__(self) -> None:
        self.clicks = 0
        self.typed: list[str] = []

    def click(self) -> None:
        self.clicks += 1

    def type_text(self, text: str) -> None:
        self.typed.append(text)

    def read_text(self) -> str:
        return "New Task"

    def is_visible(self) -> bool:
        return True


class UnpaintedControl(RecordingControl):
    """Test double: a control that is in the tree but occupies no pixels yet."""

    def is_visible(self) -> bool:
        return False


class ControlTheDesktopRefusesInputFor(RecordingControl):
    """Test double: a control Windows will not let this process touch yet.

    The refusal belongs to the desktop rather than to the control — while a
    higher-integrity window holds the foreground, nothing this process injects
    reaches anything — but it surfaces at exactly this seam.
    """

    def __init__(self, accepted_from_attempt: int) -> None:
        super().__init__()
        self.attempts = 0
        self._accepted_from_attempt = accepted_from_attempt

    def click(self) -> None:
        if self._refused():
            raise InputRefused(_WHY_THE_DESKTOP_REFUSED)
        super().click()

    def type_text(self, text: str) -> None:
        if self._refused():
            raise InputRefused(_WHY_THE_DESKTOP_REFUSED)
        super().type_text(text)

    def _refused(self) -> bool:
        self.attempts += 1
        return self.attempts < self._accepted_from_attempt


class ChainThatFinds:
    """Test double: a locator chain that resolves, and records every lookup."""

    def __init__(self, element: RecordingControl) -> None:
        self._element = element
        self.queries: list[Query] = []

    def find(self, query: Query) -> RecordingControl:
        self.queries.append(query)
        return self._element


class RebuildingChain:
    """Test double: a UI that hands back a brand-new control on every lookup.

    Not a contrivance. A WinForms label that repaints, or a Tk dialog rebuilt
    between interactions, looks exactly like this from the outside.
    """

    def __init__(self) -> None:
        self.resolved: list[RecordingControl] = []

    def find(self, query: Query) -> RecordingControl:
        control = RecordingControl()
        self.resolved.append(control)
        return control


class ChainThatNeverFinds:
    """Test double: a chain whose every locator missed, and says so."""

    def __init__(self) -> None:
        self.queries: list[Query] = []

    def find(self, query: Query) -> RecordingControl:
        self.queries.append(query)
        raise ElementNotFound(f"{query} — nothing on screen matches")


class ChainThatFindsOnAttempt:
    """Test double: a chain that misses until the app has painted the control."""

    def __init__(self, succeeds_on_attempt: int) -> None:
        self._succeeds_on_attempt = succeeds_on_attempt
        self.queries: list[Query] = []

    def find(self, query: Query) -> RecordingControl:
        self.queries.append(query)
        if len(self.queries) < self._succeeds_on_attempt:
            raise ElementNotFound(f"{query} — not painted yet")
        return RecordingControl()


class FakeWindow:
    """Test double: a top-level window that remembers being asked to close."""

    def __init__(self, title: str = "Fixture") -> None:
        self.title = title
        self.closes = 0

    def close(self) -> None:
        self.closes += 1


class WindowAlreadyGone(FakeWindow):
    """Test double: a window whose provider died before teardown reached it.

    The everyday case, not an edge case: an app that crashed, or one a test
    closed itself, leaves a window handle that answers nothing.
    """

    def close(self) -> None:
        raise RuntimeError("the window is not there any more")


class FakeProcess:
    """Test double: a launched process that counts how often it was ended."""

    def __init__(self) -> None:
        self.pid = 4242
        self.terminations = 0

    def terminate(self) -> None:
        self.terminations += 1


class TickingClock:
    """Test double: a clock that jumps a fixed step every time it is read.

    Lets a multi-second implicit wait elapse in no real time at all.
    """

    def __init__(self, step: float) -> None:
        self._step = step
        self._now = 0.0

    def __call__(self) -> float:
        reading = self._now
        self._now += self._step
        return reading


def _app_looking_things_up_in(
    chain: object, policy: RetryPolicy = _DEFAULT_WAIT
) -> App:
    """An app whose window and process are stand-ins: these specs only search."""
    return App(chain, window=FakeWindow(), process=FakeProcess(), policy=policy)


def test_clicking_an_element_resolves_its_query_through_the_chain_first() -> None:
    # Given a driver element standing in for a button nobody has looked up yet
    control = RecordingControl()
    chain = ChainThatFinds(control)
    button = UIElement(NEW_TASK_BUTTON, chain)

    # When the test clicks it
    button.click()

    # Then the query went to the chain, and the click reached what came back
    assert chain.queries == [NEW_TASK_BUTTON], (
        "the element must be resolved through the chain at interaction time"
    )
    assert control.clicks == 1, "the resolved control never received the click"


def test_typing_into_an_element_resolves_it_again_instead_of_reusing_the_clicked_control() -> (
    None
):
    # Given an element of a UI that rebuilds its controls between interactions
    chain = RebuildingChain()
    title = UIElement(TITLE_TEXTBOX, chain)
    title.click()

    # When the test types into it after that click
    title.type_text("Buy milk")

    # Then the text went to the control that exists now, not the one clicked
    assert len(chain.resolved) == 2, (
        "an element cached from an earlier interaction is stale by the next one"
    )
    assert chain.resolved[-1].typed == ["Buy milk"], (
        "the text landed on a control the user can no longer see"
    )


def test_reading_an_elements_text_returns_what_the_resolved_control_shows() -> None:
    # Given an element over a control showing a label the user can read
    control = RecordingControl()
    button = UIElement(NEW_TASK_BUTTON, ChainThatFinds(control))

    # When the test reads it
    shown = button.read_text()

    # Then it gets the control's own text back, not the name it searched by
    assert shown == "New Task", "reading an element must go to the live control"


def test_element_resolution_retries_until_the_implicit_wait_expires_then_raises() -> (
    None
):
    # Given a chain that never finds the element, and a two-second implicit wait
    chain = ChainThatNeverFinds()
    clock = TickingClock(step=0.5)
    slept: list[float] = []
    button = UIElement(
        NEW_TASK_BUTTON,
        chain,
        RetryPolicy(timeout=2.0, interval=0.5),
        clock=clock,
        sleep=slept.append,
    )

    # When the test clicks it
    with pytest.raises(ElementNotFound) as miss:
        button.click()

    # Then it kept looking until the wait ran out, instead of giving up at once
    assert len(chain.queries) > 1, (
        "a control that has not painted yet must be waited for, not failed on"
    )
    assert slept == [0.5, 0.5, 0.5], (
        f"looks should be spaced by the configured interval, not by {slept}"
    )
    # and the reason the chain gave survives, since that is all the test reports
    assert "nothing on screen matches" in str(miss.value), (
        f"the chain's own explanation was swallowed: {miss.value}"
    )


def test_a_click_the_desktop_refuses_is_tried_again_until_the_foreground_frees_up() -> (
    None
):
    # Given a desktop dropping this process's input until its third attempt
    control = ControlTheDesktopRefusesInputFor(accepted_from_attempt=3)
    slept: list[float] = []
    button = UIElement(
        NEW_TASK_BUTTON,
        ChainThatFinds(control),
        RetryPolicy(timeout=5.0, interval=0.25),
        clock=TickingClock(step=0.5),
        sleep=slept.append,
    )

    # When the test clicks it
    button.click()

    # Then the click eventually landed: a foreground thief is transient, and
    # failing on the first refusal makes every suite that meets one flaky
    assert control.attempts == 3, (
        f"a refused click must be retried inside the implicit wait, not once: "
        f"{control.attempts} attempt(s)"
    )
    assert control.clicks == 1, "the click that Windows finally allowed was lost"
    assert slept == [0.25, 0.25], (
        f"retries should be spaced by the configured interval, not by {slept}"
    )


def test_a_click_refused_for_the_whole_wait_blames_the_desktop_not_the_element() -> (
    None
):
    # Given a desktop that never lets this process's input through
    control = ControlTheDesktopRefusesInputFor(accepted_from_attempt=_NEVER)
    button = UIElement(
        NEW_TASK_BUTTON,
        ChainThatFinds(control),
        RetryPolicy(timeout=2.0, interval=0.5),
        clock=TickingClock(step=0.5),
        sleep=lambda _seconds: None,
    )

    # When the test clicks it
    with pytest.raises(InputRefused) as refusal:
        button.click()

    # Then the failure says how long it kept trying and who was in the way,
    # instead of reporting a missing element that was on screen the whole time
    reason = str(refusal.value)
    assert "synthetic mouse input was refused for 2.0s" in reason, (
        f"the reader has to be told this was the desktop refusing, and for how "
        f"long: {reason}"
    )
    assert _WHY_THE_DESKTOP_REFUSED in reason, (
        f"the adapter's own explanation was swallowed: {reason}"
    )


def test_typing_the_desktop_refuses_is_tried_again_inside_the_same_wait() -> None:
    # Given a desktop dropping this process's input until its second attempt
    control = ControlTheDesktopRefusesInputFor(accepted_from_attempt=2)
    title = UIElement(
        TITLE_TEXTBOX,
        ChainThatFinds(control),
        RetryPolicy(timeout=5.0, interval=0.0),
        clock=TickingClock(step=0.5),
        sleep=lambda _seconds: None,
    )

    # When the test types into it
    title.type_text("Buy milk")

    # Then the text arrived, because keystrokes are refused for the same reason
    # clicks are, and the fix cannot be for clicks alone
    assert control.typed == ["Buy milk"], (
        "a refused keystroke silently loses the text the test meant to enter"
    )


def test_app_button_queries_for_a_button_role_with_the_given_name() -> None:
    # Given an app over a chain that records everything it is asked for
    chain = ChainThatFinds(RecordingControl())
    app = _app_looking_things_up_in(chain)

    # When the test asks for a button by the name the user reads on it
    app.button("New Task").click()

    # Then the chain was asked for a button carrying that accessible name
    assert chain.queries == [Query(role=Role.BUTTON, name="New Task")], (
        "the facade must translate a button name into a role-bearing query"
    )


def test_app_textbox_queries_for_an_editable_role_with_the_given_name() -> None:
    # Given an app over a recording chain
    chain = ChainThatFinds(RecordingControl())
    app = _app_looking_things_up_in(chain)

    # When the test types into a box named after the label beside it
    app.textbox("Title").type_text("Buy milk")

    # Then the chain was asked for an editable control, not for a label
    assert chain.queries == [Query(role=Role.TEXTBOX, name="Title")], (
        "a textbox lookup must carry the role that tells an edit from its label"
    )


def test_app_text_queries_for_a_static_text_role_showing_the_given_value() -> None:
    # Given an app over a recording chain
    chain = ChainThatFinds(RecordingControl())
    app = _app_looking_things_up_in(chain)

    # When the test looks for a message the app is supposed to be showing
    app.text("task created").read_text()

    # Then the chain was asked for static text whose name is that message
    assert chain.queries == [Query(role=Role.TEXT, name="task created")], (
        "a label is found by the words it shows, which are also its name"
    )


def test_elements_inherit_the_implicit_wait_the_app_was_configured_with() -> None:
    # Given an app configured to give up immediately
    chain = ChainThatNeverFinds()
    app = _app_looking_things_up_in(chain, RetryPolicy(timeout=0.0, interval=0.25))

    # When the test asks for something the window does not show
    with pytest.raises(ElementNotFound):
        app.button("Delete Everything").click()

    # Then it looked exactly once, because that is the wait it was given
    assert len(chain.queries) == 1, (
        "an app whose configured wait is ignored spends the built-in default "
        "on every expected miss"
    )


def test_a_per_call_timeout_overrides_the_apps_default_implicit_wait() -> None:
    # Given an app whose default wait is far longer than this one lookup deserves
    chain = ChainThatNeverFinds()
    app = _app_looking_things_up_in(chain, RetryPolicy(timeout=30.0, interval=0.25))

    # When the test asks for something it already expects to be absent
    with pytest.raises(ElementNotFound):
        app.button("Delete Everything", timeout=0.0).click()

    # Then only that lookup gave up early; the app's default was not consulted
    assert len(chain.queries) == 1, (
        "asserting a control is absent should not cost the full implicit wait"
    )


def test_exists_returns_false_instead_of_raising_when_nothing_matches() -> None:
    # Given an element the chain will never resolve
    chain = ChainThatNeverFinds()
    status = UIElement(TASK_CREATED_LABEL, chain, RetryPolicy(timeout=0.0))

    # When the test asks whether it is on screen
    present = status.exists()

    # Then it gets an answer to assert on, not an exception to catch
    assert present is False, (
        "`assert not app.text(...).exists()` has to be writable without try/except"
    )


def test_exists_waits_for_a_control_that_has_not_painted_yet_before_answering() -> None:
    # Given a label the app only paints on the third look
    chain = ChainThatFindsOnAttempt(3)
    status = UIElement(
        TASK_CREATED_LABEL, chain, RetryPolicy(timeout=5.0, interval=0.0)
    )

    # When the test asks whether it is on screen
    present = status.exists()

    # Then the answer is yes, because a miss is a reason to look again
    assert present is True, (
        "an app repaints after the click that caused it, so exists() has to wait"
    )
    assert len(chain.queries) == 3, "exists() gave up before its deadline"


def test_exists_honours_a_per_call_timeout_when_asserting_something_is_absent() -> None:
    # Given an element with a long implicit wait behind it
    chain = ChainThatNeverFinds()
    error = UIElement(
        TASK_CREATED_LABEL, chain, RetryPolicy(timeout=30.0, interval=0.0)
    )

    # When the test asserts it is not there, and says how long to bother looking
    present = error.exists(timeout=0.0)

    # Then it looked once and said no
    assert present is False
    assert len(chain.queries) == 1, (
        "proving a control is absent must not cost the whole implicit wait"
    )


def test_wait_visible_raises_element_not_found_once_the_deadline_passes() -> None:
    # Given an element the chain will never resolve
    chain = ChainThatNeverFinds()
    dialog = UIElement(TASK_CREATED_LABEL, chain, RetryPolicy(timeout=0.0))

    # When the test waits for it to appear
    with pytest.raises(ElementNotFound) as miss:
        dialog.wait_visible()

    # Then the wait ends in a failure naming what never showed up
    assert "task created" in str(miss.value), (
        f"a wait that times out has to say what it was waiting for: {miss.value}"
    )


def test_wait_visible_hands_back_the_element_so_an_interaction_can_follow_it() -> None:
    # Given a button the app only paints on the third look
    control = RecordingControl()
    chain = ChainThatFinds(control)
    button = UIElement(NEW_TASK_BUTTON, chain, RetryPolicy(timeout=5.0, interval=0.0))

    # When the test waits for it and clicks the result in one breath
    button.wait_visible().click()

    # Then the click landed, because the wait returned the element itself
    assert control.clicks == 1, (
        "wait_visible has to be chainable, or every use of it needs a temporary"
    )


def test_wait_visible_keeps_waiting_while_the_control_is_in_the_tree_but_unpainted() -> (
    None
):
    # Given a control that is already in the tree yet occupies no pixels
    chain = ChainThatFinds(UnpaintedControl())
    dialog = UIElement(TASK_CREATED_LABEL, chain, RetryPolicy(timeout=0.0))

    # When the test waits for the user to be able to see it
    with pytest.raises(ElementNotFound):
        dialog.wait_visible()

    # Then the wait timed out: being findable is not the same as being on screen
    assert len(chain.queries) == 1, (
        "a control can sit in a window's tree long before it is painted"
    )


def test_the_apps_title_is_whatever_its_window_currently_shows() -> None:
    # Given an app whose window carries the caption the user can read
    window = FakeWindow("pytest-uia WinForms Fixture")
    app = App(ChainThatFinds(RecordingControl()), window=window, process=FakeProcess())

    # When the test reads the app's title
    title = app.title

    # Then it is the window's own caption, asked for afresh
    assert title == "pytest-uia WinForms Fixture", (
        "the facade must report the live window caption, not a launch-time copy"
    )


def test_closing_an_app_asks_its_window_first_and_then_ends_the_process() -> None:
    # Given a running app whose window still answers
    window = FakeWindow()
    process = FakeProcess()
    app = App(ChainThatFinds(RecordingControl()), window=window, process=process)

    # When the test closes it
    app.close()

    # Then it was asked to shut itself down, and then made sure of
    assert window.closes == 1, (
        "an app that closes its own window runs whatever it runs on the way out"
    )
    assert process.terminations == 1, (
        "asking politely is not enough: a wedged app still has to be ended"
    )


def test_closing_an_app_whose_window_has_already_died_still_ends_the_process() -> None:
    # Given an app that crashed, leaving a window handle that answers nothing
    process = FakeProcess()
    app = App(
        ChainThatFinds(RecordingControl()),
        window=WindowAlreadyGone(),
        process=process,
    )

    # When teardown closes it
    app.close()

    # Then the dead window did not stop the process from being ended
    assert process.terminations == 1, (
        "a failure on the polite path is exactly when the forceful one matters"
    )


def test_an_app_reports_the_pid_of_the_process_it_is_driving() -> None:
    # Given an app over a process with a pid of its own
    process = FakeProcess()
    app = App(ChainThatFinds(RecordingControl()), window=FakeWindow(), process=process)

    # When a test asks which process it is driving
    pid = app.pid

    # Then it is the launched process's own, so a test can outlive the app and
    # still check that nothing was left running
    assert pid == process.pid, "an app that hides its pid cannot be proven dead"
