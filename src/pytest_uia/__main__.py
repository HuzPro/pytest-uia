"""`python -m pytest_uia --title "..."`: dump a window that is already on screen.

A thin shell over the same `attach` and `dump` a test makes. No console-script
entry point on purpose: `python -m` always runs in the virtual environment the
user is already in.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from pytest_uia.application.session import session_on_this_desktop
from pytest_uia.domain.dump import Dump
from pytest_uia.domain.errors import WindowNotFound
from pytest_uia.domain.tree import DEFAULT_LIMITS, DumpLimits

_A_TEST_WOULD_WAIT_THIS_LONG = 10.0
_FINE = 0
_NO_SUCH_WINDOW = 1


@dataclass(frozen=True)
class Request:
    """What one run of the command line was asked for."""

    title: str
    limits: DumpLimits = DEFAULT_LIMITS
    attach_timeout: float = _A_TEST_WOULD_WAIT_THIS_LONG
    everything: bool = False

    def rendering_of(self, dump: Dump) -> str:
        """Which of the dump's two renderings this run asked for.

        Asked of the request rather than passed as a flag to a function: the
        choice is data about what was typed, and the caller that renders should
        not have to know there are two.
        """
        if self.everything:
            return dump.with_window_chrome()
        return str(dump)


class Screen(Protocol):
    """As much of the desktop as a command line needs.

    A port rather than a direct call, so both halves of the run are specified
    with no desktop at all.
    """

    def attach(self, title: str, timeout: float) -> Dumpable: ...

    def captions(self) -> tuple[str, ...]: ...


class Dumpable(Protocol):
    """The one thing the command line does with what it attached to."""

    def dump(self, *, limits: DumpLimits) -> Dump: ...


def run(request: Request, screen: Screen) -> int:
    """Dump the window that was asked for, or say what is on screen instead."""
    try:
        app = screen.attach(request.title, request.attach_timeout)
    except WindowNotFound:
        print(_nothing_is_called_that(request.title, screen.captions()))
        return _NO_SUCH_WINDOW
    # The one place the dump prints itself: there is no failing test to attach
    # it to here, and no captured output for it to disappear into.
    print(request.rendering_of(app.dump(limits=request.limits)))
    return _FINE


def _nothing_is_called_that(title: str, on_screen: Sequence[str]) -> str:
    # The captions are listed because titles are matched exactly, so the
    # likely cause of a miss is one that is nearly right.
    return "\n".join(
        [
            f"no visible top-level window titled {title!r}. On screen right now:",
            *(f"  {caption!r}" for caption in on_screen),
        ]
    )


def parsed(argv: Sequence[str] | None = None) -> Request:
    """Read the command line, or exit the way argparse exits on a bad one."""
    read = _the_arguments().parse_args(argv)
    return Request(
        title=read.title,
        limits=DumpLimits(max_nodes=read.max_nodes, budget=read.budget),
        attach_timeout=read.attach_timeout,
        everything=read.all,
    )


class ThisDesktop:
    """Composition root: the real session, and the real list of windows.

    The UIA adapter is reached only through deferred imports, so importing
    this module, and `--help` with it, needs no Windows at all.

    `attach` is deliberately the same call a test makes, and a session that did
    not start a process never ends one: this command dumps applications people
    are using.
    """

    def attach(self, title: str, timeout: float) -> Dumpable:
        return session_on_this_desktop().attach(title=title, timeout=timeout)

    def captions(self) -> tuple[str, ...]:
        from pytest_uia.adapters.uia import the_desktop, visible_top_level_titles

        return visible_top_level_titles(the_desktop())


def main(argv: Sequence[str] | None = None) -> int:
    return run(parsed(argv), ThisDesktop())


def _the_arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pytest_uia",
        description="Print the accessibility tree of a window already on screen.",
    )
    parser.add_argument(
        "--title",
        required=True,
        help="the exact caption of the window to dump, as `gui.attach` matches it",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="list the window chrome the dump otherwise folds into one line",
    )
    parser.add_argument(
        "--max-nodes",
        type=int,
        default=DEFAULT_LIMITS.max_nodes,
        help="how many controls to read before stopping and saying there are more",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=DEFAULT_LIMITS.budget,
        help="how long to spend walking before stopping and saying so",
    )
    parser.add_argument(
        "--attach-timeout",
        type=float,
        default=_A_TEST_WOULD_WAIT_THIS_LONG,
        help="how long to wait for the window to appear",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
