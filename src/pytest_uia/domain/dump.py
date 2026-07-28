"""How a walked tree reads: the text `print(app.dump())` puts on a terminal.

Where it plugs in: `ElementSource.dump()` hands a `Walk` to `dump_of` and
returns the `Dump` it answers with. Every string a user of this feature ever
sees is decided here, and nothing here has ever heard of Windows.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum, auto
from textwrap import wrap
from typing import Protocol

from pytest_uia.domain.query import Role
from pytest_uia.domain.tree import (
    DEFAULT_LIMITS,
    DumpLimits,
    TreeNode,
    Walk,
    WalkEnded,
)

_ROOT_DEPTH = 0
_ONE = 1
_NONE_AT_ALL = 0
_THE_APP = "app"
_A_WINDOW = "WindowControl"
_A_TITLE_BAR = "TitleBarControl"
_NO_DIALOG = ""
_A_LEVEL = "  "
_A_GAP = "  "
_THE_WIDEST_COLUMN_WORTH_HAVING = 52
_THE_WIDTH_OF_A_TERMINAL = 88
_THE_NARROWEST_TAIL = 20
# What to suggest when a limit bit. Nodes are cheap, so the suggestion is
# generous; seconds are a person waiting at a terminal, so that one is not.
_A_LOT_MORE = 10
_A_LOT_LONGER = 6

_THE_ROOT = "the window this dump was taken of"
_NO_ROLE_LIKE_IT = "no query: {control_type} is not a role this plugin asks for"
_NOTHING_TO_MATCH_ON = "no query: it has no accessible name to match on"
_ONLY_PAINT = "no query: nothing inside it, so what it shows is paint"
_UNREADABLE = "<unreadable>"
_IT_STOPPED_ANSWERING = "its provider stopped answering while this dump was being taken"
_AMBIGUOUS = "ambiguous: {how_many} controls answer {query}"
_THE_HEADING = "queries this window authorises:"
_NOTHING_AT_ALL = (
    "(none: nothing in this window carries a name a query can match. If it "
    "draws its own controls, the pixel fallback is what is left -- see the "
    "README's OCR section. If it is a Tk app you own, one tk_uia.enable(root) "
    "names them.)"
)
_THE_FOLD = (
    "{how_many} more controls folded: this window's own chrome ({named}). "
    "They are queryable; dump.with_window_chrome() lists them."
)


class _Kind(Enum):
    """What a line's load-bearing column turned out to say.

    Both the counts in the header and the query list at the foot are read off
    these, so a control cannot be counted in one place and rendered as
    something else in another.
    """

    THE_ROOT = auto()
    ADDRESSABLE = auto()
    AMBIGUOUS = auto()
    UNREACHABLE = auto()
    FOLDED = auto()


@dataclass(frozen=True)
class _Tail:
    """The copy-paste query, or the reason there is not one."""

    text: str
    kind: _Kind

    @property
    def is_a_paragraph(self) -> bool:
        """Whether it may be wrapped, which only the folded-chrome notice may.

        Wrapping any other tail can split a query inside its own quoted name,
        where the break is invisible.
        """
        return self.kind is _Kind.FOLDED


@dataclass(frozen=True)
class _Marker:
    """A fact about a control worth flagging, and the paragraph explaining it."""

    badge: str
    meaning: str
    applies_to: Callable[[TreeNode], bool]


def _is_driven_by_the_mouse(node: TreeNode) -> bool:
    # Only where there is a role, because only there is there anything this
    # plugin would drive: how a pane no query reaches would be clicked is not a
    # fact about anything.
    return node.driven_by_the_mouse and node.role is not None


_MARKERS = (
    # Worded as what pytest-uia will do, never as what the control supports:
    # a title-bar button is proxy-served and its Invoke works perfectly.
    _Marker(
        badge="[mouse]",
        meaning=(
            "[mouse]  pytest-uia will not act through this control's "
            "Invoke/Value patterns -- the generic MSAA proxy answers for it, "
            "where those calls return cleanly and reach nothing. It uses the "
            "real pointer and keyboard instead, which is what a refused "
            "foreground can block."
        ),
        applies_to=_is_driven_by_the_mouse,
    ),
    _Marker(
        badge="[offscreen]",
        meaning=(
            "[offscreen]  this control is in the window's tree with nothing on "
            "screen, so a query finds it and anything aimed at it lands on "
            "whatever is underneath. element.wait_visible() is the call that "
            "waits it out."
        ),
        applies_to=lambda node: node.offscreen,
    ),
)


@dataclass(frozen=True)
class _Reading:
    """One walked control, plus what its place in the tree says about it.

    Both facts are derived from the pre-order sequence rather than asked of the
    application: that costs no further calls into a provider which may already
    be answering slowly, and it keeps the walker ignorant of what the dump will
    make of what it saw.
    """

    node: TreeNode
    has_nothing_inside_it: bool
    # Whether it is one of the controls Windows puts on every window, and, for
    # the title bar itself, the names of the ones folded underneath it.
    is_window_chrome: bool
    folds: tuple[str, ...]
    # Every child window it sits in, outermost first. The last of them decides
    # whether a reader is handed `app.button(...)` or
    # `app.dialog("Settings").button(...)`; the whole list decides which other
    # controls a scoped query would also reach.
    enclosed_by: tuple[str, ...]

    @property
    def inside_the_dialog(self) -> str:
        return self.enclosed_by[-1] if self.enclosed_by else _NO_DIALOG


@dataclass(frozen=True)
class Dump:
    """One window's controls, and the queries they authorise."""

    nodes: tuple[TreeNode, ...]
    ended: WalkEnded = WalkEnded.FINISHED
    limits: DumpLimits = DEFAULT_LIMITS
    # The caption of the child window this dump was taken *through*, if any.
    # A reader who ran `dialog.dump()` is holding a Dialog, and an unscoped
    # `app.textbox(...)` would teach them the idiom that breaks the moment the
    # next wizard step reuses the caption.
    inside_the_dialog: str = _NO_DIALOG

    def __str__(self) -> str:
        return "\n".join(_the_page_of(self, _FOLDING_THE_CHROME))

    @property
    def queries(self) -> tuple[str, ...]:
        """Every query this window authorises, in tree order.

        The same list the page ends with, as values. A spec that asserted on
        the rendered tree would pin column positions and break the next time a
        word changed; this is the promise, and the layout stays free to move.
        """
        readings = _read(self.nodes, self.inside_the_dialog)
        return tuple(
            _the_queries_of(readings, _how_many_controls_answer_each(readings))
        )

    def with_window_chrome(self) -> str:
        """The same tree with nothing folded, so the fold can be checked.

        A second method rather than an argument to `dump()`: which controls to
        show is a rendering choice made after the walk, and a walk that had to
        be taken again to answer it would be a second look at a window that may
        have moved on.
        """
        return "\n".join(_the_page_of(self, _SHOWING_EVERY_CONTROL))


def dump_of(walk: Walk, *, inside_the_dialog: str = _NO_DIALOG) -> Dump:
    """Read a walk as a tree a person can act on."""
    return Dump(
        nodes=walk.nodes,
        ended=walk.ended,
        limits=walk.limits,
        inside_the_dialog=inside_the_dialog,
    )


def _the_page_of(dump: Dump, folding: _Folding) -> list[str]:
    readings = _read(dump.nodes, dump.inside_the_dialog)
    answering = _how_many_controls_answer_each(readings)
    return [
        _the_header_over(readings, answering),
        *_whether_a_limit_bit(dump),
        *_the_lines_of(readings, answering, folding),
        *_the_legend_for(readings, folding),
        "",
        *_the_queries_under(readings, answering),
    ]


def _whether_a_limit_bit(dump: Dump) -> list[str]:
    """Said directly under the count, because it is what the count means.

    A truncated dump that read like a complete one is the one failure this
    feature cannot afford: a reader who took it at its word would conclude the
    control they came looking for does not exist.
    """
    notice = _WHY_IT_STOPPED.get(dump.ended)
    if notice is None:
        return []
    return _a_paragraph(notice(dump))


def _the_node_cap_bit(dump: Dump) -> str:
    return (
        f"stopped after {_however_many(len(dump.nodes))} and there are more: "
        f"raise it with app.dump(limits=DumpLimits("
        f"max_nodes={dump.limits.max_nodes * _A_LOT_MORE}))."
    )


def _the_time_ran_out(dump: Dump) -> str:
    # Names the clock rather than the size, because two controls in five
    # seconds is not a big window and a reader must not go looking for one.
    return (
        f"stopped after {dump.limits.budget}s and "
        f"{_however_many(len(dump.nodes))}: this window's provider is answering "
        f"slowly, so the rest of its tree is not in this dump. Raise it with "
        f"app.dump(limits=DumpLimits(budget={dump.limits.budget * _A_LOT_LONGER}))."
    )


_WHY_IT_STOPPED: dict[WalkEnded, Callable[[Dump], str]] = {
    WalkEnded.HIT_THE_NODE_CAP: _the_node_cap_bit,
    WalkEnded.RAN_OUT_OF_TIME: _the_time_ran_out,
}


def _the_legend_for(readings: Sequence[_Reading], folding: _Folding) -> list[str]:
    """What the markers mean, said once, and only for markers that appear.

    Keyed off what this rendering *shows*, not off the whole walk: a legend
    counted over the walk can explain a badge the fold took off the page.
    """
    on_the_page = [reading for reading in readings if folding.shows(reading)]
    explained = [
        marker
        for marker in _MARKERS
        if any(marker.applies_to(reading.node) for reading in on_the_page)
    ]
    if not explained:
        return []
    return [
        "",
        *(line for marker in explained for line in _a_paragraph(marker.meaning)),
    ]


def _the_queries_under(
    readings: Sequence[_Reading], answering: Sequence[int]
) -> list[str]:
    """Every query this window authorises, gathered where a reader can copy them.

    The empty case is replaced by the finding rather than left blank: a
    heading over nothing reads like a bug in the tool, when it is the answer.
    """
    found = _the_queries_of(readings, answering)
    if not found:
        return [_THE_HEADING, *_a_paragraph(_NOTHING_AT_ALL)]
    return [_THE_HEADING, *_indented(found)]


def _the_queries_of(
    readings: Sequence[_Reading], answering: Sequence[int]
) -> list[str]:
    return [
        tail.text
        for tail in (
            _a_tail_for(reading, how_many)
            for reading, how_many in zip(readings, answering)
            if not reading.is_window_chrome
        )
        if tail.kind is _Kind.ADDRESSABLE
    ]


def _a_paragraph(prose: str) -> list[str]:
    """Prose, wrapped to a terminal and indented under whatever introduced it."""
    return _indented(wrap(prose, _THE_WIDTH_OF_A_TERMINAL - len(_A_LEVEL)))


def _indented(lines: Sequence[str]) -> list[str]:
    return [f"{_A_LEVEL}{line}" for line in lines]


def _the_header_over(readings: Sequence[_Reading], answering: Sequence[int]) -> str:
    """The window, and where every control it holds ended up.

    Counted over the walk rather than over what is rendered: the folded chrome
    is in this arithmetic, so a reader can check the four categories and the
    window itself against the total and find nothing missing. A count that did
    not add up would mean the dump had walked something it never reported,
    which is the one failure this feature cannot afford.
    """
    chrome = sum(1 for reading in readings if reading.is_window_chrome)
    kinds = Counter(
        _a_tail_for(reading, how_many).kind
        for reading, how_many in zip(readings, answering)
        if not reading.is_window_chrome
    )
    return (
        f"{readings[0].node.name!r} -- {_however_many(len(readings))}: "
        f"{kinds[_Kind.ADDRESSABLE]} addressable, "
        f"{kinds[_Kind.AMBIGUOUS]} ambiguous, "
        f"{kinds[_Kind.UNREACHABLE]} unreachable, "
        f"{chrome} chrome"
    )


def _however_many(controls: int) -> str:
    return f"{controls} control" if controls == _ONE else f"{controls} controls"


def _the_lines_of(
    readings: Sequence[_Reading], answering: Sequence[int], folding: _Folding
) -> list[str]:
    shown = [
        (reading, how_many)
        for reading, how_many in zip(readings, answering)
        if folding.shows(reading)
    ]
    heads = [_a_head_for(reading.node) for reading, _ in shown]
    column = _where_the_tails_start(heads)
    lines: list[str] = []
    for head, (reading, how_many) in zip(heads, shown):
        tail = folding.what_it_says(reading, _a_tail_for(reading, how_many))
        lines.extend(_laid_out(head, column, tail))
        lines[-1] += _the_markers_on(reading.node)
    return lines


def _the_markers_on(node: TreeNode) -> str:
    return "".join(
        f"{_A_GAP}{marker.badge}" for marker in _MARKERS if marker.applies_to(node)
    )


def _laid_out(head: str, column: int, tail: _Tail) -> list[str]:
    if not tail.is_a_paragraph:
        return [f"{head:<{column}}{_A_GAP}{tail.text}"]
    room = max(_THE_WIDTH_OF_A_TERMINAL - column - len(_A_GAP), _THE_NARROWEST_TAIL)
    pieces = wrap(tail.text, room) or [""]
    beneath_it = ""
    return [
        f"{head if at == 0 else beneath_it:<{column}}{_A_GAP}{piece}"
        for at, piece in enumerate(pieces)
    ]


class _Folding(Protocol):
    """Strategy: how much of the window's own chrome a rendering shows."""

    def shows(self, reading: _Reading) -> bool: ...

    def what_it_says(self, reading: _Reading, otherwise: _Tail) -> _Tail: ...


class _FoldingTheChrome:
    """The default: a title bar's descendants become one counted line under it."""

    def shows(self, reading: _Reading) -> bool:
        return not reading.is_window_chrome

    def what_it_says(self, reading: _Reading, otherwise: _Tail) -> _Tail:
        if not reading.folds:
            return otherwise
        return _Tail(
            _THE_FOLD.format(how_many=len(reading.folds), named=_named(reading.folds)),
            _Kind.FOLDED,
        )


class _ShowingEveryControl:
    """What `with_window_chrome()` renders: the walk, entire."""

    def shows(self, reading: _Reading) -> bool:
        return True

    def what_it_says(self, reading: _Reading, otherwise: _Tail) -> _Tail:
        return otherwise


_FOLDING_THE_CHROME: _Folding = _FoldingTheChrome()
_SHOWING_EVERY_CONTROL: _Folding = _ShowingEveryControl()


def _named(folded: Sequence[str]) -> str:
    # Deduplicated in tree order: a title bar carries its system menu twice,
    # under the same name, and saying so twice reads as a mistake.
    return ", ".join(dict.fromkeys(name for name in folded if name))


def _where_the_tails_start(heads: Sequence[str]) -> int:
    """The column the queries line up in: the widest head, within reason.

    Capped so one control with a paragraph for a name cannot push every query
    off the terminal. Over-long heads keep their whole name and take the gap
    alone: a name cut to fit the layout is a silent wrong answer.
    """
    return min(max(len(head) for head in heads), _THE_WIDEST_COLUMN_WORTH_HAVING)


def _read(nodes: Sequence[TreeNode], inside_the_dialog: str) -> list[_Reading]:
    enclosing = _the_dialogs_enclosing_each(nodes, inside_the_dialog)
    chrome = _which_are_window_chrome(nodes)
    return [
        _Reading(
            node=node,
            has_nothing_inside_it=_is_a_leaf(nodes, at),
            enclosed_by=enclosing[at],
            is_window_chrome=chrome[at],
            folds=_what_it_folds(nodes, at),
        )
        for at, node in enumerate(nodes)
    ]


def _which_are_window_chrome(nodes: Sequence[TreeNode]) -> list[bool]:
    """Which controls belong to a title bar rather than to the application.

    Structural, never a name heuristic: a control is chrome because Windows
    parented it under a `TitleBarControl`, not because it happens to be called
    Close. An application's own Close button is its own business.
    """
    chrome: list[bool] = []
    a_title_bar_at: int | None = None
    for node in nodes:
        if a_title_bar_at is not None and node.depth <= a_title_bar_at:
            a_title_bar_at = None
        chrome.append(a_title_bar_at is not None)
        if node.control_type == _A_TITLE_BAR:
            a_title_bar_at = node.depth
    return chrome


def _what_it_folds(nodes: Sequence[TreeNode], at: int) -> tuple[str, ...]:
    """The names of everything in this title bar's own subtree, in tree order.

    Stops at the first node back up at its depth rather than filtering on the
    chrome flag: a dialog further down the window has a title bar of its own,
    and its buttons are that one's to account for.
    """
    if nodes[at].control_type != _A_TITLE_BAR:
        return ()
    folded: list[str] = []
    for node in nodes[at + 1 :]:
        if node.depth <= nodes[at].depth:
            break
        folded.append(node.name)
    return tuple(folded)


def _the_dialogs_enclosing_each(
    nodes: Sequence[TreeNode], inside_the_dialog: str
) -> list[tuple[str, ...]]:
    """Which child windows each control sits in, recovered with one stack.

    A pre-order walk makes this free: a dialog's frame stays on the stack until
    a node arrives at its depth or above, and everything seen in between is
    inside it.

    A dump taken through a dialog seeds that stack with the dialog itself, so
    the scoping rule needs no second case: every control in it is inside one
    child window more than the tree alone would say.
    """
    outermost = (inside_the_dialog,) if inside_the_dialog else ()
    open_dialogs: list[tuple[int, str]] = []
    enclosing: list[tuple[str, ...]] = []
    for node in nodes:
        while open_dialogs and open_dialogs[-1][0] >= node.depth:
            open_dialogs.pop()
        enclosing.append(outermost + tuple(caption for _depth, caption in open_dialogs))
        if _is_a_child_window(node):
            open_dialogs.append((node.depth, node.name))
    return enclosing


def _is_a_child_window(node: TreeNode) -> bool:
    # Structural, and named: the root is a window too, and everything under it
    # is already scoped by `app` itself.
    return (
        node.control_type == _A_WINDOW and node.depth != _ROOT_DEPTH and bool(node.name)
    )


def _is_a_leaf(nodes: Sequence[TreeNode], at: int) -> bool:
    # A walk visits parents before children, so the node after a childless one
    # is never deeper than it.
    beyond_the_last = at + 1 == len(nodes)
    return beyond_the_last or nodes[at + 1].depth <= nodes[at].depth


def _how_many_controls_answer_each(readings: Sequence[_Reading]) -> list[int]:
    """How many controls each reading's own query would resolve to.

    Not a count of matching names: it is a count of what that *particular*
    query reaches. An unscoped `app.button("Confirm")` searches the whole
    window, dialogs included, so it collides with a control three branches
    away; `app.dialog("Settings").button("Confirm")` searches one window and
    reaches exactly one. Counting names alone would mark the scoped call
    ambiguous too, which is the dump contradicting the API it documents.
    """
    by_name: dict[tuple[Role, str], list[_Reading]] = defaultdict(list)
    for reading in readings:
        if reading.node.role is not None and reading.node.name:
            by_name[(reading.node.role, reading.node.name)].append(reading)
    return [_how_many_answer(reading, by_name) for reading in readings]


def _how_many_answer(
    reading: _Reading, by_name: dict[tuple[Role, str], list[_Reading]]
) -> int:
    if reading.node.role is None or not reading.node.name:
        return _NONE_AT_ALL
    same_name = by_name[(reading.node.role, reading.node.name)]
    return sum(1 for other in same_name if _within_the_same_scope(reading, other))


def _within_the_same_scope(reading: _Reading, other: _Reading) -> bool:
    scope = reading.inside_the_dialog
    return not scope or scope in other.enclosed_by


def _a_head_for(node: TreeNode) -> str:
    if not node.readable:
        return f"{_A_LEVEL * node.depth}{_UNREADABLE}"
    return f"{_A_LEVEL * node.depth}{node.control_type} {node.name!r}{_the_id_of(node)}"


def _the_id_of(node: TreeNode) -> str:
    if not node.automation_id:
        return ""
    return f"{_A_GAP}id={node.automation_id}"


def _a_tail_for(reading: _Reading, how_many_answer: int) -> _Tail:
    """The copy-paste query, or the reason there is not one. Never both, never neither."""
    node = reading.node
    if not node.readable:
        return _Tail(_IT_STOPPED_ANSWERING, _Kind.UNREACHABLE)
    if node.depth == _ROOT_DEPTH:
        return _Tail(_THE_ROOT, _Kind.THE_ROOT)
    if _is_a_child_window(node):
        # Ahead of every rule below it: a dialog is a WindowControl, which is
        # not a role any query asks for, so the generic reason would fire on
        # the one control the reader most needs a call for. Unscoped even when
        # it is nested, because `dialog_titled` searches at any depth.
        return _Tail(_the_scope(node.name), _Kind.ADDRESSABLE)
    if node.role is None:
        return _Tail(_why_no_query_reaches(reading), _Kind.UNREACHABLE)
    if not node.name:
        return _Tail(_NOTHING_TO_MATCH_ON, _Kind.UNREACHABLE)
    query = _the_query_for(node, reading.inside_the_dialog)
    if how_many_answer > _ONE:
        return _Tail(
            _AMBIGUOUS.format(how_many=how_many_answer, query=query), _Kind.AMBIGUOUS
        )
    return _Tail(query, _Kind.ADDRESSABLE)


def _why_no_query_reaches(reading: _Reading) -> str:
    if reading.has_nothing_inside_it:
        return _ONLY_PAINT
    return _NO_ROLE_LIKE_IT.format(control_type=reading.node.control_type)


def _the_query_for(node: TreeNode, inside_the_dialog: str = _NO_DIALOG) -> str:
    # The method's name is the role's, spelled the way a test writes it: the
    # reader is being handed a line to paste, not a description of one.
    return (
        f"{_the_scope(inside_the_dialog)}"
        f".{node.role.name.lower()}({_as_written_in_a_test(node.name)})"
    )


def _the_scope(inside_the_dialog: str) -> str:
    if not inside_the_dialog:
        return _THE_APP
    return f"{_THE_APP}.dialog({_as_written_in_a_test(inside_the_dialog)})"


def _as_written_in_a_test(name: str) -> str:
    return f'"{name}"'
