"""Behavioral spec for `python -m pytest_uia --title "..."`.

Where it plugs in: the newcomer this whole feature is for has an application on
screen and no test yet, so the answer to "what is my control called" cannot
begin with "first write a test". This is that shell.

No desktop anywhere. Parsing is a pure function of `argv`, and the run itself
takes the screen as a collaborator, so both halves are specified here and only
the composition root touches Windows.
"""

from __future__ import annotations

import pytest

from pytest_uia.__main__ import Request, parsed, run
from pytest_uia.domain.dump import Dump, dump_of
from pytest_uia.domain.errors import WindowNotFound
from pytest_uia.domain.query import Role
from pytest_uia.domain.tree import DumpLimits, TreeNode, Walk

A_WINDOW_ON_SCREEN = "pytest-uia WinForms Fixture"
_A_USAGE_ERROR = 2


def test_the_command_line_requires_the_title_of_the_window_to_dump() -> None:
    # Given a command line with no window named on it
    argv: list[str] = []

    # When it is parsed
    with pytest.raises(SystemExit) as refused:
        parsed(argv)

    # Then it is refused with argparse's own usage exit rather than guessing.
    # There is no sensible default: dumping "whatever is in front" would
    # photograph the terminal the command was typed into
    assert refused.value.code == _A_USAGE_ERROR, (
        f"a missing title is a usage error, not a run: {refused.value.code}"
    )


def test_the_command_line_asks_for_the_window_that_was_named_on_it() -> None:
    # Given a command line naming a window
    argv = ["--title", A_WINDOW_ON_SCREEN]

    # When it is parsed
    request = parsed(argv)

    # Then that is what will be attached to, matched exactly as `gui.attach`
    # matches — the same call a test would make
    assert request == Request(title=A_WINDOW_ON_SCREEN), (
        f"everything else has a default; the window does not: {request}"
    )


class ScreenShowing:
    """Test double: a desktop with some windows on it and none of them ours."""

    def __init__(self, *captions: str) -> None:
        self._captions = captions

    def attach(self, title: str, timeout: float) -> object:
        raise WindowNotFound(f"no visible top-level window titled {title!r}")

    def captions(self) -> tuple[str, ...]:
        return self._captions


def test_the_command_line_prints_the_captions_on_screen_when_no_window_matches_the_title(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given a desktop showing a window whose caption is close but not exact
    screen = ScreenShowing("Untitled - Notepad", A_WINDOW_ON_SCREEN)

    # When the command line is run against a caption nothing carries
    code = run(Request(title="Notepad"), screen)

    # Then it says so and lists what is there. Captions are matched exactly, so
    # the overwhelmingly likely cause of a miss is a title that is nearly right
    # — and "no such window" alone leaves the reader with nothing to correct
    reported = capsys.readouterr().out
    assert "no visible top-level window titled 'Notepad'" in reported, (
        f"the caption that missed has to be quoted back: {reported}"
    )
    assert "'Untitled - Notepad'" in reported, (
        f"the caption they almost certainly meant is the whole answer: {reported}"
    )
    assert code == 1, f"a window that is not there is a failed run: {code}"


class AppOnScreen:
    """Test double: an attached app that knows what is in its own window."""

    def __init__(self, *controls: TreeNode) -> None:
        self._controls = controls
        self.limits_dumped_with: list[DumpLimits] = []

    def dump(self, *, limits: DumpLimits) -> Dump:
        self.limits_dumped_with.append(limits)
        return dump_of(
            Walk(
                nodes=(
                    TreeNode(
                        control_type="WindowControl",
                        name=A_WINDOW_ON_SCREEN,
                        depth=0,
                    ),
                    *self._controls,
                ),
                limits=limits,
            )
        )


class ScreenShowingOurWindow:
    """Test double: a desktop with the window that was asked for on it."""

    def __init__(self, app: AppOnScreen) -> None:
        self._app = app

    def attach(self, title: str, timeout: float) -> AppOnScreen:
        return self._app

    def captions(self) -> tuple[str, ...]:
        return (A_WINDOW_ON_SCREEN,)


def _a_button(name: str) -> TreeNode:
    return TreeNode(control_type="ButtonControl", name=name, depth=1, role=Role.BUTTON)


def _a_title_bar() -> tuple[TreeNode, ...]:
    return (
        TreeNode(control_type="TitleBarControl", name="", depth=1),
        TreeNode(control_type="ButtonControl", name="Close", depth=2, role=Role.BUTTON),
    )


def test_the_command_line_prints_the_dump_of_the_window_it_attached_to(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given the window that was asked for, with a button in it
    app = AppOnScreen(_a_button("New Task"))

    # When the command line is run
    code = run(Request(title=A_WINDOW_ON_SCREEN), ScreenShowingOurWindow(app))

    # Then the tree is on stdout, with the query a reader came for. This is the
    # one place the dump does print itself: there is no test to attach it to
    # and no captured output to lose it in
    printed = capsys.readouterr().out
    assert 'app.button("New Task")' in printed, (
        f"the command line exists to put this line in front of somebody: {printed}"
    )
    assert code == 0, f"a window that was dumped is a successful run: {code}"


def test_the_command_line_can_ask_for_the_window_chrome_the_dump_folds_away(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given a window whose title bar the default rendering folds into one line
    app = AppOnScreen(_a_button("New Task"), *_a_title_bar())

    # When the command line is run the way `--all` asks for it
    run(parsed(["--title", A_WINDOW_ON_SCREEN, "--all"]), ScreenShowingOurWindow(app))

    # Then the folded controls are lines of their own. The fold names the
    # method that undoes it, and a reader at a terminal has no object to call
    # it on — so the flag is what makes that promise true for them
    printed = capsys.readouterr().out
    assert 'app.button("Close")' in printed, (
        f"a fold a command-line reader cannot undo is not reversible: {printed}"
    )
    assert "folded" not in printed, (
        f"nothing is folded here, so nothing may claim to be: {printed}"
    )
