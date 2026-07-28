"""Behavioral spec for the fluent driver a test actually writes against.

Everything here runs against doubles: no window, no desktop, no waiting. The
driver's whole job is deciding *when* to ask a locator for an element and what
to do with the answer, and that decision is worth testing in milliseconds
rather than in seconds of real screen time.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from pytest_uia.application.driver import App, UIElement
from pytest_uia.domain.errors import (
    DialogNotFound,
    DialogStillOpen,
    ElementNotFound,
    InputRefused,
    TextNeverSettled,
)
from pytest_uia.domain.query import Query, Role
from pytest_uia.domain.tree import DumpLimits, TreeNode, Walk
from pytest_uia.domain.waiting import RetryPolicy

NEW_TASK_BUTTON = Query(role=Role.BUTTON, name="New Task")
TITLE_TEXTBOX = Query(role=Role.TEXTBOX, name="Title")
TASK_CREATED_LABEL = Query(role=Role.TEXT, name="task created")

# The collision the whole dialog feature exists for: a caption a wizard reuses
# on every step, which also sits on the window underneath it.
CONFIRM = "Confirm"
SETTINGS = "Settings"
NEW_TASK = "New Task"
FOLDER = "Folder"

_DEFAULT_WAIT = RetryPolicy()

# No pause between looks: the dialog specs are about what is waited *for*, not
# about how long a real desktop takes to paint a window.
_NO_PAUSE = RetryPolicy(timeout=5.0, interval=0.0)

# What the pointer adapter raises: a bare reason the driver has to carry
# through, because it is the only thing that names the culprit.
_WHY_THE_DESKTOP_REFUSED = (
    "the foreground is held by 'GameInputServiceWindow' (pid 6680)"
)
_NEVER = 10_000

# What a test types, and what the box still reads out of the tree for a moment
# afterwards: the application re-announces the new value on its own message
# pump, so the old one survives the call that replaced it.
A_TYPED_DRAFT = "Buy milk"
A_STALE_READING = ""


class RecordingControl:
    """Test double: an on-screen control that remembers what was done to it."""

    def __init__(self) -> None:
        self.clicks = 0
        self.typed: list[str] = []
        self.checked = False

    def click(self) -> None:
        self.clicks += 1

    def type_text(self, text: str) -> None:
        self.typed.append(text)

    def read_text(self) -> str:
        return "New Task"

    def is_checked(self) -> bool:
        return self.checked

    def is_visible(self) -> bool:
        return True


class UnpaintedControl(RecordingControl):
    """Test double: a control that is in the tree but occupies no pixels yet."""

    def is_visible(self) -> bool:
        return False


class ControlTheDesktopRefusesInputFor(RecordingControl):
    """Test double: a control Windows will not let this process touch yet.

    The refusal belongs to the desktop rather than to the control (while a
    higher-integrity window holds the foreground, nothing this process injects
    reaches anything) but it surfaces at exactly this seam.
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


class ControlShowing(RecordingControl):
    """Test double: a control reading whatever the application last announced."""

    def __init__(self, shown: str) -> None:
        super().__init__()
        self._shown = shown

    def read_text(self) -> str:
        return self._shown


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


class ChainThatCatchesUpOnAttempt:
    """Test double: a UI that only re-announces a typed value after N looks.

    A brand-new control every lookup, because that is what a window which has
    repainted hands back, an element held across a wait would go on reading
    the value the application has already replaced.
    """

    def __init__(self, settles_on_attempt: int) -> None:
        self._settles_on_attempt = settles_on_attempt
        self.resolved: list[RecordingControl] = []

    def find(self, query: Query) -> RecordingControl:
        control = ControlShowing(self._what_it_shows_on_this_look())
        self.resolved.append(control)
        return control

    def _what_it_shows_on_this_look(self) -> str:
        has_caught_up = len(self.resolved) + 1 >= self._settles_on_attempt
        return A_TYPED_DRAFT if has_caught_up else A_STALE_READING


class ChainThatNeverFinds:
    """Test double: a chain whose every locator missed, and says so."""

    def __init__(self) -> None:
        self.queries: list[Query] = []

    def find(self, query: Query) -> RecordingControl:
        self.queries.append(query)
        raise ElementNotFound(f"{query} -- nothing on screen matches")


class ChainThatFindsOnAttempt:
    """Test double: a chain that misses until the app has painted the control."""

    def __init__(self, succeeds_on_attempt: int) -> None:
        self._succeeds_on_attempt = succeeds_on_attempt
        self.queries: list[Query] = []

    def find(self, query: Query) -> RecordingControl:
        self.queries.append(query)
        if len(self.queries) < self._succeeds_on_attempt:
            raise ElementNotFound(f"{query} -- not painted yet")
        return RecordingControl()


def _a_button(name: str) -> TreeNode:
    return TreeNode(control_type="ButtonControl", name=name, depth=1, role=Role.BUTTON)


def _a_textbox(name: str) -> TreeNode:
    return TreeNode(control_type="EditControl", name=name, depth=1, role=Role.TEXTBOX)


class FakeDialog:
    """Test double: a child window with a search of its own inside it."""

    def __init__(
        self, title: str, contents: object, *, controls: Sequence[TreeNode] = ()
    ) -> None:
        self.title = title
        self.contents = contents
        self.closes = 0
        self._controls = tuple(controls)

    def dialog_titled(self, title: str) -> FakeDialog:
        raise DialogNotFound(f"no window titled {title!r} inside {self.title!r}")

    def walk(self, limits: DumpLimits) -> Walk:
        return Walk(nodes=(_the_window_control(self.title), *self._controls))

    def close(self) -> None:
        self.closes += 1


class FakeWindow:
    """Test double: a top-level window that remembers being asked to close."""

    def __init__(
        self, title: str = "Fixture", *, dialogs: Sequence[FakeDialog] = ()
    ) -> None:
        self.title = title
        self.closes = 0
        self.dialogs_looked_up: list[str] = []
        self.limits_walked_with: list[DumpLimits] = []
        self._dialogs = {dialog.title: dialog for dialog in dialogs}

    def dialog_titled(self, title: str) -> FakeDialog:
        self.dialogs_looked_up.append(title)
        return self._whatever_is_open(title)

    def walk(self, limits: DumpLimits) -> Walk:
        self.limits_walked_with.append(limits)
        return Walk(nodes=(_the_window_control(self.title),))

    def close(self) -> None:
        self.closes += 1

    def _whatever_is_open(self, title: str) -> FakeDialog:
        if title not in self._dialogs:
            raise DialogNotFound(f"no window titled {title!r} inside {self.title!r}")
        return self._dialogs[title]


class WindowWithControls(FakeWindow):
    """Test double: a window with something in it worth dumping."""

    def __init__(
        self,
        *controls: TreeNode,
        title: str = "Fixture",
        dialogs: Sequence[FakeDialog] = (),
    ) -> None:
        super().__init__(title, dialogs=dialogs)
        self._controls = controls

    def walk(self, limits: DumpLimits) -> Walk:
        self.limits_walked_with.append(limits)
        return Walk(nodes=(_the_window_control(self.title), *self._controls))


def _the_window_control(title: str) -> TreeNode:
    return TreeNode(control_type="WindowControl", name=title, depth=0)


class WindowAlreadyGone(FakeWindow):
    """Test double: a window whose provider died before teardown reached it.

    The everyday case, not an edge case: an app that crashed, or one a test
    closed itself, leaves a window handle that answers nothing.
    """

    def close(self) -> None:
        raise RuntimeError("the window is not there any more")


class WindowWhoseDialogOpensOnAttempt(FakeWindow):
    """Test double: a window whose dialog is only on screen from the Nth look.

    The ordinary case, not an edge case: a dialog opens on the application's
    own message pump, so the click that asks for one returns before the window
    behind it exists.
    """

    def __init__(self, dialog: FakeDialog, *, opens_on_attempt: int) -> None:
        super().__init__(dialogs=[dialog])
        self._opens_on_attempt = opens_on_attempt

    def _whatever_is_open(self, title: str) -> FakeDialog:
        if len(self.dialogs_looked_up) < self._opens_on_attempt:
            raise DialogNotFound(f"no window titled {title!r} inside {self.title!r}")
        return super()._whatever_is_open(title)


class WindowWhoseDialogClosesOnAttempt(FakeWindow):
    """Test double: a window whose dialog is gone from the Nth look onwards.

    A dialog is destroyed on the same message pump that opened it, so it
    outlives the click that dismissed it by exactly as long as the application
    takes to notice.
    """

    def __init__(self, dialog: FakeDialog, *, closes_on_attempt: int) -> None:
        super().__init__(dialogs=[dialog])
        self._closes_on_attempt = closes_on_attempt

    def _whatever_is_open(self, title: str) -> FakeDialog:
        if len(self.dialogs_looked_up) >= self._closes_on_attempt:
            raise DialogNotFound(f"no window titled {title!r} inside {self.title!r}")
        return super()._whatever_is_open(title)


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


def _app_whose_window_is(window: FakeWindow, policy: RetryPolicy = _NO_PAUSE) -> App:
    """An app that can find nothing itself, so only a dialog's search can answer."""
    return App(
        ChainThatNeverFinds(), window=window, process=FakeProcess(), policy=policy
    )


# Every role a test can ask for: the enum member, the control type the UIA
# adapter maps it to, and the call a test writes. One list, because the three
# drift the moment they live in three places.
EVERY_ROLE_A_TEST_CAN_ASK_FOR = [
    ("CHECKBOX", "CheckBoxControl", "checkbox"),
    ("RADIO", "RadioButtonControl", "radio"),
    ("SLIDER", "SliderControl", "slider"),
    ("SPINBOX", "SpinnerControl", "spinbox"),
    ("COMBOBOX", "ComboBoxControl", "combobox"),
    ("LISTBOX", "ListControl", "listbox"),
    ("TREE", "TreeControl", "tree"),
    ("PROGRESSBAR", "ProgressBarControl", "progressbar"),
    ("SCROLLBAR", "ScrollBarControl", "scrollbar"),
    ("GROUP", "GroupControl", "group"),
    ("IMAGE", "ImageControl", "image"),
    ("SPLIT_BUTTON", "SplitButtonControl", "split_button"),
    ("SEPARATOR", "SeparatorControl", "separator"),
    ("THUMB", "ThumbControl", "thumb"),
    ("TAB_STRIP", "TabControl", "tab_strip"),
]


@pytest.mark.parametrize(
    ("member", "_control_type", "call"), EVERY_ROLE_A_TEST_CAN_ASK_FOR
)
def test_each_kind_of_control_is_asked_for_by_a_call_named_after_it(
    member: str, _control_type: str, call: str
) -> None:
    # Given an application whose window holds one of every kind of control
    chain = ChainThatFinds(RecordingControl())
    app = _app_looking_things_up_in(chain)

    # When the test asks for one by the name it carries
    getattr(app, call)("Quantity").click()

    # Then it was looked up as that kind. Every one of these was announced
    # correctly to a screen reader and unreachable from a test until now: a
    # control type with no role to ask for it is findable by nothing.
    assert chain.queries == [Query(role=Role[member], name="Quantity")], (
        f"app.{call}(...) asked for {chain.queries}"
    )


def test_asking_for_a_notebook_tab_searches_for_a_tab_rather_than_a_button() -> None:
    # Given an application whose window has a notebook in it
    chain = ChainThatFinds(RecordingControl())
    app = _app_looking_things_up_in(chain)

    # When the test asks for one of its tabs and clicks it
    app.tab("Database").click()

    # Then it was looked up as a tab. A notebook's tabs are the one control a
    # test has to reach before it can reach anything on the page behind them,
    # and they are neither buttons nor text: asking for the wrong role finds
    # nothing at all, however well the tab is named.
    assert chain.queries == [Query(role=Role.TAB, name="Database")], (
        f"asked for {chain.queries}"
    )


def test_reading_whether_a_checkbox_is_checked_asks_the_control_it_resolves_to() -> (
    None
):
    # Given a checkbox that is currently on
    control = RecordingControl()
    control.checked = True
    checkbox = UIElement(
        Query(role=Role.CHECKBOX, name="Notify me"), ChainThatFinds(control)
    )

    # When the test asks whether it is checked
    # Then it answers from the control, not from what the test last did to it.
    # A suite that clicked and assumed is a suite that passes when the click
    # went nowhere, which on Tk it silently can.
    assert checkbox.is_checked() is True


def test_a_checkbox_that_is_not_checked_says_so_rather_than_raising() -> None:
    # Given a checkbox that is off
    control = RecordingControl()
    control.checked = False
    checkbox = UIElement(
        Query(role=Role.CHECKBOX, name="Notify me"), ChainThatFinds(control)
    )

    # When the test asks
    # Then it is False. Both directions of the assertion have to be usable, or
    # half of every checkbox test has to be written as a `pytest.raises`.
    assert checkbox.is_checked() is False


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


def test_an_element_that_never_appears_says_how_long_it_was_waited_for() -> None:
    # Given a chain that never finds the element, and a two-second implicit wait
    chain = ChainThatNeverFinds()
    button = UIElement(
        NEW_TASK_BUTTON,
        chain,
        RetryPolicy(timeout=2.0, interval=0.0),
        clock=TickingClock(step=0.5),
        sleep=lambda _seconds: None,
    )

    # When the test clicks it
    with pytest.raises(ElementNotFound) as miss:
        button.click()

    # Then the failure says how long it kept looking, which only the driver
    # knows, as well as where it looked, which only the chain can say. Both
    # `DialogNotFound` and `InputRefused` already carry the deadline, and a
    # reader who is not told it cannot tell a control that never appears from
    # one that was simply given a tenth of a second to
    reason = str(miss.value)
    assert "2.0s" in reason, (
        f"the reader has to be told how long the element was waited for: {reason}"
    )
    assert "nothing on screen matches" in reason, (
        f"the chain's own explanation was swallowed: {reason}"
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


def test_waiting_for_text_returns_as_soon_as_the_element_already_reads_it() -> None:
    # Given a button whose control already shows the words the test expects
    chain = ChainThatFinds(RecordingControl())
    button = UIElement(NEW_TASK_BUTTON, chain, RetryPolicy(timeout=5.0, interval=0.0))

    # When the test waits for that text
    button.wait_until_text_is("New Task")

    # Then it came straight back, instead of spending a wait on a screen that
    # was already showing what was asked for
    assert len(chain.queries) == 1, (
        f"a settled value must cost one look, not {len(chain.queries)}"
    )


def test_waiting_for_text_keeps_re_resolving_until_the_application_catches_up() -> None:
    # Given a box the app only re-announces the typed value in on the third look
    chain = ChainThatCatchesUpOnAttempt(3)
    title = UIElement(TITLE_TEXTBOX, chain, RetryPolicy(timeout=5.0, interval=0.0))

    # When the test waits for what it typed to come back out of the tree
    title.wait_until_text_is(A_TYPED_DRAFT)

    # Then it kept looking, and looked at a freshly resolved control each time:
    # a stale value read once out of a control held across the wait would never
    # change, however long the wait was
    assert len(chain.resolved) == 3, (
        f"a value the app has not re-announced yet must be waited for, not "
        f"accepted after {len(chain.resolved)} look(s)"
    )


def test_waiting_for_text_reports_what_it_read_and_what_it_expected_when_time_runs_out() -> (
    None
):
    # Given a box that stays empty however long the test waits for it
    chain = ChainThatFinds(ControlShowing(A_STALE_READING))
    title = UIElement(TITLE_TEXTBOX, chain, RetryPolicy(timeout=0.0))

    # When the test waits for the value it typed
    with pytest.raises(TextNeverSettled) as unsettled:
        title.wait_until_text_is(A_TYPED_DRAFT)

    # Then the failure carries both readings. A gui failure usually leaves
    # nothing behind but this string, and "the text is wrong" without the two
    # values tells whoever reads it nothing they can act on
    reason = str(unsettled.value)
    assert repr(A_STALE_READING) in reason, (
        f"the wait must say what the element actually read: {reason}"
    )
    assert repr(A_TYPED_DRAFT) in reason, (
        f"the wait must say what it was waiting to read: {reason}"
    )
    # and how long it gave the application to catch up, exactly as every other
    # failure the driver raises against a deadline now does
    assert "0.0s" in reason, (
        f"the reader has to be told how long the text was waited for: {reason}"
    )


def test_waiting_for_text_honours_a_per_call_timeout_over_the_implicit_wait() -> None:
    # Given an element with a long implicit wait behind it, over a box the app
    # has not typed into yet
    chain = ChainThatFinds(ControlShowing(A_STALE_READING))
    title = UIElement(
        TITLE_TEXTBOX,
        chain,
        RetryPolicy(timeout=30.0, interval=0.0),
        clock=TickingClock(step=0.5),
        sleep=lambda _seconds: None,
    )

    # When the test says how long this one wait is worth
    with pytest.raises(TextNeverSettled):
        title.wait_until_text_is(A_TYPED_DRAFT, timeout=0.0)

    # Then only that wait gave up early, exactly as `exists` and `wait_visible`
    # already let a caller decide
    assert len(chain.queries) == 1, (
        "a wait a test has budgeted for itself must not cost the whole implicit wait"
    )


def test_waiting_for_text_hands_back_the_element_so_an_interaction_can_follow_it() -> (
    None
):
    # Given a box already reading what the test was waiting for
    control = ControlShowing(A_TYPED_DRAFT)
    title = UIElement(
        TITLE_TEXTBOX, ChainThatFinds(control), RetryPolicy(timeout=5.0, interval=0.0)
    )

    # When the test waits for the text and acts on the result in one breath
    title.wait_until_text_is(A_TYPED_DRAFT).click()

    # Then the click landed, because the wait returned the element itself,
    # the same shape `wait_visible` already has
    assert control.clicks == 1, (
        "wait_until_text_is has to be chainable, or every use of it needs a temporary"
    )


def test_waiting_for_text_treats_a_control_that_has_not_painted_yet_as_a_reason_to_look_again() -> (
    None
):
    # Given a label the app only paints on the third look
    chain = ChainThatFindsOnAttempt(3)
    status = UIElement(
        TASK_CREATED_LABEL, chain, RetryPolicy(timeout=5.0, interval=0.0)
    )

    # When the test waits for the words it is supposed to end up showing
    status.wait_until_text_is("New Task")

    # Then a control that was not there yet was a miss rather than a failure:
    # the same click that changes a label's text is often the one that creates
    # it, so the two kinds of lateness share one deadline
    assert len(chain.queries) == 3, (
        f"an element that has not been painted yet must be waited for, not "
        f"failed on after {len(chain.queries)} look(s)"
    )


def test_waiting_for_text_blames_the_missing_element_when_nothing_ever_resolves() -> (
    None
):
    # Given a chain that never resolves the element at all
    chain = ChainThatNeverFinds()
    status = UIElement(TASK_CREATED_LABEL, chain, RetryPolicy(timeout=0.0))

    # When the test waits for text on it
    with pytest.raises(ElementNotFound) as miss:
        status.wait_until_text_is("task created")

    # Then the failure names the thing that was actually absent. Reporting an
    # unsettled text about a control that was never on screen would send the
    # reader looking at the wrong half of the problem
    assert "task created" in str(miss.value), (
        f"a wait that never found its element has to say so: {miss.value}"
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


def test_a_dialogs_queries_are_answered_inside_it_and_not_in_the_window_underneath() -> (
    None
):
    # Given a dialog and the window it opened over, each carrying a Confirm
    in_the_dialog = RecordingControl()
    under_the_dialog = RecordingControl()
    window = FakeWindow(dialogs=[FakeDialog(SETTINGS, ChainThatFinds(in_the_dialog))])
    app = App(ChainThatFinds(under_the_dialog), window=window, process=FakeProcess())

    # When the test drives the Confirm inside the dialog
    app.dialog(SETTINGS).button(CONFIRM).click()

    # Then the dialog's own button ran, and the identically named one beneath it
    # was never touched. A search that started from the main window would reach
    # both, and answer with whichever the tree happened to offer first
    assert in_the_dialog.clicks == 1, "the dialog's own button never got the click"
    assert under_the_dialog.clicks == 0, (
        "the click went to the window underneath the dialog, which is the "
        "ambiguity addressing a dialog by name exists to remove"
    )


def test_addressing_a_dialog_waits_for_the_application_to_finish_opening_it() -> None:
    # Given a window whose dialog is only on screen from the third look
    confirm = RecordingControl()
    window = WindowWhoseDialogOpensOnAttempt(
        FakeDialog(SETTINGS, ChainThatFinds(confirm)), opens_on_attempt=3
    )
    app = _app_whose_window_is(window)

    # When the test addresses it in the line after the click that opens it
    app.dialog(SETTINGS).button(CONFIRM).click()

    # Then it kept looking until the window appeared, instead of failing on the
    # gap between a click returning and a dialog being painted
    assert len(window.dialogs_looked_up) == 3, (
        f"a dialog that has not opened yet must be waited for, not failed on "
        f"after {len(window.dialogs_looked_up)} look(s)"
    )
    assert confirm.clicks == 1, "the dialog that finally opened was never driven"


def test_a_dialog_that_never_opens_says_which_one_and_how_long_it_was_waited_for() -> (
    None
):
    # Given a window that never shows the dialog a test is expecting
    window = FakeWindow("pytest-uia Tk Fixture")
    app = _app_whose_window_is(window, RetryPolicy(timeout=2.0, interval=0.0))

    # When the test addresses it
    with pytest.raises(DialogNotFound) as never_opened:
        app.dialog(SETTINGS)

    # Then the failure carries both halves of what a reader needs: how long the
    # driver kept looking, which is the only place that is known, and where it
    # looked, which only the window that was searched can say. A gui failure
    # usually leaves nothing behind but this string
    reason = str(never_opened.value)
    assert "2.0s" in reason, (
        f"the reader has to be told how long the dialog was waited for: {reason}"
    )
    assert SETTINGS in reason, f"the caption that never appeared is missing: {reason}"
    assert "pytest-uia Tk Fixture" in reason, (
        f"the window that was searched is what says the caption was wrong "
        f"rather than the step that opens it: {reason}"
    )


def test_a_per_call_timeout_overrides_the_implicit_wait_for_a_dialog_to_open() -> None:
    # Given an app whose default wait is far longer than this one lookup deserves
    window = FakeWindow()
    app = _app_whose_window_is(window, RetryPolicy(timeout=30.0, interval=0.0))

    # When the test asserts a dialog it already expects to be absent
    with pytest.raises(DialogNotFound):
        app.dialog(SETTINGS, timeout=0.0)

    # Then only that lookup gave up early, exactly as every element wait allows
    assert len(window.dialogs_looked_up) == 1, (
        "proving no dialog opened must not cost the whole implicit wait"
    )


def test_waiting_for_a_dialog_to_close_returns_once_the_application_has_dismissed_it() -> (
    None
):
    # Given a dialog the application only takes off screen by the third look
    window = WindowWhoseDialogClosesOnAttempt(
        FakeDialog(SETTINGS, ChainThatNeverFinds()), closes_on_attempt=3
    )
    settings = _app_whose_window_is(window).dialog(SETTINGS)

    # When the test waits for the wizard step to end
    settings.wait_closed()

    # Then it kept looking until the window went away, rather than believing the
    # click that dismissed it, the dialog outlives that click by however long
    # the application takes to notice
    assert len(window.dialogs_looked_up) == 3, (
        f"a dialog still closing must be waited out, not failed on after "
        f"{len(window.dialogs_looked_up)} look(s)"
    )


def test_a_dialog_that_never_closes_says_which_one_and_how_long_it_was_waited_for() -> (
    None
):
    # Given a dialog that stays on screen however long the test waits
    window = FakeWindow(
        "pytest-uia Tk Fixture", dialogs=[FakeDialog(SETTINGS, ChainThatNeverFinds())]
    )
    app = _app_whose_window_is(window, RetryPolicy(timeout=2.0, interval=0.0))
    settings = app.dialog(SETTINGS)

    # When the test waits for it to go away
    with pytest.raises(DialogStillOpen) as still_there:
        settings.wait_closed()

    # Then the failure names the dialog that would not leave and how long it was
    # given to. "the assert failed" about a boolean says nothing anyone can act on
    reason = str(still_there.value)
    assert SETTINGS in reason, f"the dialog that stayed is not named: {reason}"
    assert "2.0s" in reason, (
        f"the reader has to be told how long it was waited out for: {reason}"
    )


def test_asking_whether_a_dialog_is_open_answers_rather_than_raising() -> None:
    # Given an application with nothing over its main window
    app = _app_whose_window_is(FakeWindow(), RetryPolicy(timeout=0.0, interval=0.0))

    # When the test asks whether the wizard's step is up
    up = app.has_dialog(SETTINGS)

    # Then it gets something to assert on, not an exception to catch
    assert up is False, (
        "`assert not app.has_dialog(...)` has to be writable without try/except"
    )


def test_dumping_an_app_walks_the_window_it_was_launched_against() -> None:
    # Given an app whose window holds a button, and a search that finds nothing
    window = WindowWithControls(_a_button(NEW_TASK))
    app = App(ChainThatNeverFinds(), window=window, process=FakeProcess())

    # When the test dumps it
    dump = app.dump()

    # Then the dump is of that window's own controls. The locator chain is not
    # consulted at all, a dump answers what is *there*, which is exactly the
    # question a reader has when the chain has just failed them
    assert 'app.button("New Task")' in dump.queries, (
        f"the app must dump the window it was launched against: {dump.queries}"
    )


def test_dumping_a_dialog_walks_that_dialog_and_not_the_window_underneath_it() -> None:
    # Given an app showing a settings dialog, each window with its own control
    dialog = FakeDialog(SETTINGS, ChainThatNeverFinds(), controls=(_a_textbox(FOLDER),))
    window = WindowWithControls(_a_button(NEW_TASK), dialogs=[dialog])
    app = App(
        ChainThatNeverFinds(), window=window, process=FakeProcess(), policy=_NO_PAUSE
    )

    # When the test dumps the dialog
    dump = app.dialog(SETTINGS).dump()

    # Then it covers exactly the subtree that dialog's own queries search, and
    # no more. A dialog whose dump showed the window underneath would be
    # describing a scope its `button` and `textbox` do not have
    assert any(FOLDER in query for query in dump.queries), (
        f"the dialog's own control is missing from its own dump: {dump.queries}"
    )
    assert not any(NEW_TASK in query for query in dump.queries), (
        f"the dump reached past the dialog's edge, which is the ambiguity "
        f"addressing a dialog by name exists to remove: {dump.queries}"
    )


def test_a_dialogs_dump_offers_its_controls_as_queries_scoped_to_that_dialog() -> None:
    # Given an app showing a settings dialog with a box in it
    dialog = FakeDialog(SETTINGS, ChainThatNeverFinds(), controls=(_a_textbox(FOLDER),))
    window = WindowWithControls(_a_button(NEW_TASK), dialogs=[dialog])
    app = App(
        ChainThatNeverFinds(), window=window, process=FakeProcess(), policy=_NO_PAUSE
    )

    # When the test dumps the dialog
    dump = app.dialog(SETTINGS).dump()

    # Then the lines it hands back are scoped to the dialog. A reader who ran
    # `dialog.dump()` is holding a Dialog, and an unscoped `app.textbox(...)`
    # would teach them the very idiom that breaks the moment the next wizard
    # step reuses the caption
    assert dump.queries == ('app.dialog("Settings").textbox("Folder")',), (
        f"a dump taken through a dialog has to answer in that dialog's own "
        f"calls: {dump.queries}"
    )


def test_a_dump_passes_the_callers_limits_through_to_the_walk_instead_of_its_own() -> (
    None
):
    # Given an app, and a caller who has read the truncation notice and wants
    # the rest of a big window
    window = WindowWithControls(_a_button(NEW_TASK))
    app = App(ChainThatNeverFinds(), window=window, process=FakeProcess())
    generously = DumpLimits(max_nodes=5000, budget=30.0)

    # When the test dumps it with those limits
    app.dump(limits=generously)

    # Then the walk was given them. The notice tells a reader to raise the cap
    # with exactly this call, and a limit that stopped at the driver would make
    # that instruction a lie
    assert window.limits_walked_with == [generously], (
        f"the caller's limits have to reach the thing doing the work: "
        f"{window.limits_walked_with}"
    )


def test_asking_about_a_dialog_that_is_open_says_so() -> None:
    # Given an application showing the dialog
    window = FakeWindow(dialogs=[FakeDialog(SETTINGS, ChainThatNeverFinds())])
    app = _app_whose_window_is(window)

    # When the test asks whether it is up
    up = app.has_dialog(SETTINGS)

    # Then the answer is yes, so the question is worth asking in both directions
    assert up is True, "a dialog that is plainly on screen was reported absent"
