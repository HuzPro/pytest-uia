"""Behavioral spec for the walk that turns a real window into TreeNodes.

Where it plugs in: this is the half of `app.dump()` that touches Windows. The
formatter's own spec (`tests/test_tree_dump.py`) builds `TreeNode`s by hand;
this one proves the adapter builds the same shape out of UI Automation, and
that nothing `comtypes` raises escapes past it.

Named `test_uia_*` because it imports `uiautomation` at module scope for
`auto.ControlType`, which `tests/conftest.py` excludes off Windows.

The doubles carry `uiautomation`'s own PascalCase names on purpose: they stand
in for its Controls, exactly as `tests/test_uia_dead_window.py`'s `DeadControl`
does. Between them they answer `GetFirstChildControl` and
`GetNextSiblingControl`, which is all `auto.WalkControl` ever calls — so the
*real* walk runs over a tree assembled here, and the adapter's translation is
specified with no desktop at all.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

import pytest
import uiautomation as auto
from comtypes import COMError

from pytest_uia.adapters.uia import UiaWindow, visible_top_level_titles
from pytest_uia.domain.errors import WindowNotFound
from pytest_uia.domain.query import Role
from pytest_uia.domain.tree import DumpLimits, WalkEnded

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="UI Automation is a Windows API",
)

WINFORMS_FIXTURE = "pytest-uia WinForms Fixture"
NEW_TASK = "New Task"

# What a provider that answers for itself looks like, so a double is trusted
# unless a spec deliberately makes it otherwise.
_ITS_OWN_PROVIDER = "Annotation Provider"
_A_FRAMEWORK_THAT_ANSWERS_FOR_ITSELF = "WinForm"


class FakeControl:
    """Test double: one UIA control, and the two calls a walk makes of it."""

    def __init__(
        self,
        control_type_name: str,
        name: str = "",
        control_type: int = auto.ControlType.CustomControl,
        *,
        automation_id: str = "",
        children: Sequence[FakeControl] = (),
        framework: str = _A_FRAMEWORK_THAT_ANSWERS_FOR_ITSELF,
        provider: str = _ITS_OWN_PROVIDER,
        offscreen: bool = False,
    ) -> None:
        self.ControlTypeName = control_type_name
        self.Name = name
        self.ProcessId = 4242
        self.ControlType = control_type
        self.AutomationId = automation_id
        self.FrameworkId = framework
        self.ProviderDescription = provider
        self.IsOffscreen = offscreen
        self._children = list(children)
        self._next: FakeControl | None = None
        for older, younger in zip(self._children, self._children[1:]):
            older._next = younger

    def GetFirstChildControl(self) -> FakeControl | None:
        return self._children[0] if self._children else None

    def GetNextSiblingControl(self) -> FakeControl | None:
        return self._next


def _a_window(*children: FakeControl) -> FakeControl:
    return FakeControl(
        "WindowControl",
        WINFORMS_FIXTURE,
        auto.ControlType.WindowControl,
        children=children,
    )


def test_walking_a_window_reports_its_own_control_first_and_at_depth_zero() -> None:
    # Given a window with a control in it
    window = _a_window(FakeControl("ButtonControl", NEW_TASK))

    # When the adapter walks it
    walk = UiaWindow(window).walk(DumpLimits())

    # Then the window itself is the first thing reported, at the top. Every
    # rule the formatter applies is relative to that root — the scoping, the
    # indentation, the "this is the window you dumped" line — so a walk that
    # started at the first child would silently shift all of them
    assert walk.nodes[0].depth == 0, (
        f"the window under test is the root of its own dump: {walk.nodes[0]}"
    )
    assert walk.nodes[0].name == WINFORMS_FIXTURE, (
        f"the root is the window, not whatever it holds: {walk.nodes[0]}"
    )


def test_walking_a_window_reports_a_childs_control_type_name_accessible_name_and_automation_id() -> (
    None
):
    # Given a window with a text box in it, of the kind a WinForms app has
    window = _a_window(
        FakeControl(
            "EditControl", "Title", auto.ControlType.EditControl, automation_id="198966"
        )
    )

    # When the adapter walks it
    walk = UiaWindow(window).walk(DumpLimits())

    # Then all three identifiers a reader might already have in front of them —
    # from Accessibility Insights, or from inspect.exe — come back, one level
    # below the window
    box = walk.nodes[1]
    assert box.control_type == "EditControl", f"the control type is the head: {box}"
    assert box.name == "Title", f"the accessible name is the whole question: {box}"
    assert box.automation_id == "198966", f"the id is the other identifier: {box}"
    assert box.depth == 1, f"a child of the window sits one level down: {box}"


def test_a_button_control_is_walked_as_the_role_the_button_query_asks_for() -> None:
    # Given a window with a button in it
    window = _a_window(
        FakeControl("ButtonControl", NEW_TASK, auto.ControlType.ButtonControl)
    )

    # When the adapter walks it
    walk = UiaWindow(window).walk(DumpLimits())

    # Then it carries the role the locator searches by, resolved here rather
    # than in the formatter. The mapping from role to control type is already
    # in this module and single-sourced, so widening what a query can find and
    # widening what a dump can offer stay the same edit
    assert walk.nodes[1].role is Role.BUTTON, (
        f"a control the dump offers `app.button(...)` for has to be the same "
        f"control `app.button(...)` would find: {walk.nodes[1]}"
    )


def test_a_control_type_no_role_maps_to_is_walked_with_no_role_rather_than_skipped() -> (
    None
):
    # Given a window whose layout pane is of a type no query asks for
    window = _a_window(
        FakeControl("PaneControl", "the panel", auto.ControlType.PaneControl)
    )

    # When the adapter walks it
    walk = UiaWindow(window).walk(DumpLimits())

    # Then it is in the walk with nothing claimed about it. Filtering it out
    # here would put the omission below the formatter, where no wording can
    # rescue it — and the formatter's whole job is to say why it is unreachable
    assert len(walk.nodes) == 2, (
        f"the walk reports what is there, and decides nothing: {walk.nodes}"
    )
    assert walk.nodes[1].role is None, (
        f"no role is an answer; guessing one would be worse: {walk.nodes[1]}"
    )


def test_a_control_the_generic_proxy_speaks_for_is_walked_as_one_this_plugin_drives_by_mouse() -> (
    None
):
    # Given a Tk button — no provider of its own, so Windows fabricates one out
    # of MSAA — beside a control of a framework that answers for itself
    window = _a_window(
        FakeControl(
            "ButtonControl",
            NEW_TASK,
            auto.ControlType.ButtonControl,
            framework="Win32",
            provider="Microsoft: MSAA Proxy",
        )
    )

    # When the adapter walks it
    walk = UiaWindow(window).walk(DumpLimits())

    # Then the Tk button is marked and the window is not. It is the same rule
    # the element adapter already applies before it decides whether to invoke
    # or to click, asked here for reporting rather than for acting — so the
    # dump cannot drift from what a test will actually do
    assert walk.nodes[1].driven_by_the_mouse is True, (
        f"a control this plugin will reach for the pointer to drive is worth "
        f"saying so about: {walk.nodes[1]}"
    )
    assert walk.nodes[0].driven_by_the_mouse is False, (
        f"a provider that answers for itself must not be marked, or the marker "
        f"means nothing: {walk.nodes[0]}"
    )


def test_a_control_in_the_tree_with_no_pixels_is_walked_as_being_off_screen() -> None:
    # Given a control the window carries without showing
    window = _a_window(
        FakeControl(
            "ButtonControl", NEW_TASK, auto.ControlType.ButtonControl, offscreen=True
        )
    )

    # When the adapter walks it
    walk = UiaWindow(window).walk(DumpLimits())

    # Then the walk carries that, because being findable and being visible are
    # different states and only one of them can be clicked
    assert walk.nodes[1].offscreen is True, (
        f"a query that resolves to something nobody can see is the confusing "
        f"case, and the walk is where the fact comes from: {walk.nodes[1]}"
    )


def _a_window_of_three() -> FakeControl:
    return _a_window(
        FakeControl("ButtonControl", NEW_TASK, auto.ControlType.ButtonControl),
        FakeControl("ButtonControl", "Confirm", auto.ControlType.ButtonControl),
    )


def test_a_walk_stops_at_the_node_cap_and_reports_that_the_tree_went_on() -> None:
    # Given a window of three controls and an allowance for two
    window = _a_window_of_three()

    # When the adapter walks it
    walk = UiaWindow(window).walk(DumpLimits(max_nodes=2))

    # Then it stopped at two and knows the tree had not ended. The cap is
    # tested by taking one control too many and dropping it, so "there are
    # more" is something the walk saw rather than something it inferred
    assert len(walk.nodes) == 2, f"the cap is a cap: {walk.nodes}"
    assert walk.ended is WalkEnded.HIT_THE_NODE_CAP, (
        f"a truncation nobody is told about is the one failure a dump cannot "
        f"afford: {walk.ended}"
    )
    assert walk.limits.max_nodes == 2, (
        f"the limits ride along so the notice can name the call that lifts "
        f"them: {walk.limits}"
    )


def test_a_walk_that_fits_inside_its_cap_reports_that_it_saw_the_whole_window() -> None:
    # Given a window of three controls and an allowance for three
    window = _a_window_of_three()

    # When the adapter walks it
    walk = UiaWindow(window).walk(DumpLimits(max_nodes=3))

    # Then nothing claims to have been cut. A cap that reported itself whenever
    # a window happened to be exactly full would put a truncation notice on a
    # complete dump, and a notice that cries wolf is one nobody reads
    assert walk.ended is WalkEnded.FINISHED, (
        f"a window that fits was not truncated: {walk.ended}"
    )


def test_a_walk_reports_the_window_itself_however_small_the_allowance_it_was_given() -> (
    None
):
    # Given an allowance too small for even one control
    window = _a_window_of_three()

    # When the adapter walks it
    walk = UiaWindow(window).walk(DumpLimits(max_nodes=0))

    # Then the window is still there, and the truncation is still reported. A
    # dump of nothing at all is not a smaller dump, it is a different thing:
    # the whole page is written relative to a root, and there would be no
    # window to name in the header of one that had none
    assert len(walk.nodes) == 1, (
        f"the window under test is always in its own dump: {walk.nodes}"
    )
    assert walk.nodes[0].depth == 0, f"and it is the root of it: {walk.nodes}"
    assert walk.ended is WalkEnded.HIT_THE_NODE_CAP, (
        f"keeping the root is not a reason to stop saying what was cut: {walk.ended}"
    )


def test_a_walk_that_outlives_its_budget_stops_and_reports_that_it_ran_out_of_time() -> (
    None
):
    # Given a window of three controls and no time at all to read them
    window = _a_window_of_three()

    # When the adapter walks it
    walk = UiaWindow(window).walk(DumpLimits(budget=0.0, max_nodes=500))

    # Then it stopped on the clock rather than on the allowance. This is what a
    # node cap cannot do: measured, `Program Manager` answers five controls in
    # 4.1 seconds, all of it inside one call, so a cap of 500 would bound
    # nothing about how long that dump takes
    assert len(walk.nodes) == 1, (
        f"a budget that has run out stops the walk between controls: {walk.nodes}"
    )
    assert walk.ended is WalkEnded.RAN_OUT_OF_TIME, (
        f"the reader must be sent to the clock and not to the size of their "
        f"window: {walk.ended}"
    )


# The HRESULT the WinForms fixture really answered with once it had been
# killed, rather than a plausible-looking one.
_THE_PROVIDER_IS_GONE = -2147220991
_ITS_MESSAGE = "An event was unable to invoke any of the subscribers"


def _the_provider_is_gone() -> COMError:
    # A fresh refusal every time: one shared instance accumulates the traceback
    # of every raise it has been through, and the next failure report then
    # points at the previous test.
    return COMError(_THE_PROVIDER_IS_GONE, _ITS_MESSAGE, (None,) * 5)


class ControlOfAnApplicationThatHasExited:
    """Test double: a window whose provider went away underneath the walk.

    Measured against the WinForms fixture after `taskkill /t /f`: iterating it
    raised out of `GetFirstChildControl` — from the walk itself, not from a
    property read — and every individual property answered the same HRESULT.
    """

    @property
    def ControlTypeName(self) -> str:
        raise _the_provider_is_gone()

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
    def AutomationId(self) -> str:
        raise _the_provider_is_gone()

    @property
    def IsOffscreen(self) -> bool:
        raise _the_provider_is_gone()

    @property
    def ProviderDescription(self) -> str:
        raise _the_provider_is_gone()

    def GetFirstChildControl(self) -> object:
        raise _the_provider_is_gone()


def test_walking_a_window_whose_application_has_exited_is_reported_as_the_window_being_gone() -> (
    None
):
    # Given the window of an application that is no longer running
    window = ControlOfAnApplicationThatHasExited()

    # When a test dumps it
    with pytest.raises(WindowNotFound) as gone:
        UiaWindow(window).walk(DumpLimits())

    # Then it is the domain's own kind of absence, as `App.title` has answered
    # since 0.4.1 — not an HRESULT out of comtypes, raised past a driver that
    # never catches one. WindowNotFound rather than ElementNotFound because
    # nothing was being looked for
    assert "gone" in str(gone.value), (
        f"the reader has to be told the window went away: {gone.value}"
    )


class ControlWhosePropertiesDied:
    """Test double: a control the walk can still step over, and cannot read.

    The narrower half of the same accident — a child window destroyed while the
    dump was being taken — where the iteration goes on answering after an
    individual property has stopped.
    """

    def __init__(self) -> None:
        self._next: object | None = None

    @property
    def ControlTypeName(self) -> str:
        raise _the_provider_is_gone()

    @property
    def Name(self) -> str:
        raise _the_provider_is_gone()

    @property
    def ControlType(self) -> int:
        raise _the_provider_is_gone()

    @property
    def AutomationId(self) -> str:
        raise _the_provider_is_gone()

    @property
    def IsOffscreen(self) -> bool:
        raise _the_provider_is_gone()

    @property
    def ProviderDescription(self) -> str:
        raise _the_provider_is_gone()

    def GetFirstChildControl(self) -> object:
        return None

    def GetNextSiblingControl(self) -> object:
        return self._next


def test_a_control_that_stops_answering_mid_walk_is_reported_as_unreadable_rather_than_ending_the_walk() -> (
    None
):
    # Given a window whose middle control stops answering part-way through
    window = _a_window(
        FakeControl("ButtonControl", NEW_TASK, auto.ControlType.ButtonControl),
        ControlWhosePropertiesDied(),
        FakeControl("ButtonControl", "Confirm", auto.ControlType.ButtonControl),
    )

    # When the adapter walks it
    walk = UiaWindow(window).walk(DumpLimits())

    # Then it is kept and marked, and the walk carried on past it. Dropping it
    # would be the silent omission this whole feature refuses; aborting would
    # throw away every control that did answer, over one that stopped
    assert len(walk.nodes) == 4, (
        f"one control that went away must not cost the reader the window: {walk.nodes}"
    )
    assert walk.nodes[2].readable is False, (
        f"a control that cannot be read is a fact to report, not one to hide: "
        f"{walk.nodes[2]}"
    )
    assert walk.nodes[3].name == "Confirm", (
        f"everything after it is still there: {walk.nodes}"
    )


def test_the_captions_on_screen_leave_out_the_unnamed_the_hidden_and_the_nested() -> (
    None
):
    # Given a desktop with four top-level windows on it, two of which no user
    # could pick out by name, and one of which holds a window of its own
    desktop = FakeControl(
        "PaneControl",
        "Desktop",
        auto.ControlType.PaneControl,
        children=(
            FakeControl(
                "WindowControl",
                "Untitled - Notepad",
                auto.ControlType.WindowControl,
                children=(
                    FakeControl(
                        "WindowControl", "Find", auto.ControlType.WindowControl
                    ),
                ),
            ),
            FakeControl("WindowControl", "", auto.ControlType.WindowControl),
            FakeControl(
                "WindowControl",
                "Left On A Hidden Desktop",
                auto.ControlType.WindowControl,
                offscreen=True,
            ),
            FakeControl(
                "WindowControl", WINFORMS_FIXTURE, auto.ControlType.WindowControl
            ),
        ),
    )

    # When the command line asks what is on screen
    captions = visible_top_level_titles(desktop)

    # Then it is exactly the list a user could have typed after `--title`, and
    # the same filter `resolve_main_window` already applies. A child dialog in
    # that list would be a caption `--title` cannot match, offered as one it can
    assert captions == ("Untitled - Notepad", WINFORMS_FIXTURE), (
        f"the point of the list is that every line in it would have worked: {captions}"
    )
