"""What a walked control is, and how much of a window a walk is allowed to cost.

Where it plugs in: the adapter walks a real window and answers with a `Walk` of
these; `domain/dump.py` turns that into the text a reader sees. Stdlib only, on
purpose — nothing here knows that UI Automation exists, so the whole of the
dump's reasoning is testable with no desktop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from pytest_uia.domain.query import Role


@dataclass(frozen=True)
class TreeNode:
    """One control a walk saw, and everything the dump reasons about it from."""

    control_type: str
    name: str
    depth: int
    role: Role | None = None
    # Shown, never queried. v1 searches by name and role only, and measured,
    # a WinForms control's id is HWND-derived and different on every launch.
    automation_id: str = ""
    # What pytest-uia will *do* with it, never what its provider advertises.
    # Measured: a title bar's buttons answer to this rule and their Invoke
    # works perfectly, so the two are genuinely different statements.
    driven_by_the_mouse: bool = False
    # In the window's tree with no pixels on screen. Being findable and being
    # visible are different states, and only one of them can be clicked.
    offscreen: bool = False
    # False when a property read raised part-way through the walk. Kept in the
    # walk rather than dropped: a control that was there and then was not is
    # still a fact about the window.
    readable: bool = True


@dataclass(frozen=True)
class DumpLimits:
    """How much of a window a dump is allowed to cost.

    Both are needed, and neither replaces the other. A node cap bounds how much
    there is to read; only a wall clock bounds how long it takes, because one
    call into a hostile provider can block for seconds on its own — measured,
    `Program Manager` answers five nodes in 4.1 seconds.

    Deliberately no depth limit. `uiautomation`'s own `maxDepth` gives no
    signal that it pruned anything, so a depth cut is exactly the silent
    omission this feature exists to refuse: measured, a browser window at depth
    8 yields 1486 of its 5437 controls and says nothing about the other 3951.
    Both limits here know when they bit, and both say so.
    """

    max_nodes: int = 500
    budget: float = 5.0


DEFAULT_LIMITS = DumpLimits()
"""What a dump costs unless a caller has a window that needs more."""


class WalkEnded(Enum):
    """Why a walk stopped, which decides whether the dump is the whole window."""

    FINISHED = auto()
    HIT_THE_NODE_CAP = auto()
    RAN_OUT_OF_TIME = auto()


@dataclass(frozen=True)
class Walk:
    """Every control a walk saw, in the pre-order the tree was read in."""

    nodes: tuple[TreeNode, ...]
    ended: WalkEnded = WalkEnded.FINISHED
    # Carried rather than looked up, so the notice that a limit bit can name
    # the call that raises the one that did.
    limits: DumpLimits = field(default=DEFAULT_LIMITS)
