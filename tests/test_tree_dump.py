"""Behavioral spec for the text a tree dump renders, and for what it refuses to hide.

Where it plugs in: this is the formatter half of `app.dump()`. It consumes
`TreeNode`s built by hand here, so every string the feature prints is specified
with no Windows, no UI Automation and no window on screen — which is what keeps
the Ubuntu CI lane a real gate on this feature rather than on its imports.

The dump exists to answer one question — *what is my control called, and can
this plugin reach it?* — so the load-bearing assertion in almost every spec
below is the copy-paste query a line carries, or the reason there is not one.
"""

from __future__ import annotations

from itertools import takewhile

from pytest_uia.domain.dump import dump_of
from pytest_uia.domain.query import Role
from pytest_uia.domain.tree import DumpLimits, TreeNode, Walk, WalkEnded

CANVAS_FIXTURE = "pytest-uia Canvas Fixture"
WINFORMS_FIXTURE = "pytest-uia WinForms Fixture"
TK_FIXTURE = "pytest-uia Tk Fixture"
NEW_TASK = "New Task"
CONFIRM = "Confirm"
SETTINGS = "Settings"


def _a_control(
    control_type: str,
    name: str = "",
    *,
    depth: int = 1,
    role: Role | None = None,
    automation_id: str = "",
    driven_by_the_mouse: bool = False,
    offscreen: bool = False,
) -> TreeNode:
    """One walked control, with only the facts a spec cares about spelled out."""
    return TreeNode(
        control_type=control_type,
        name=name,
        depth=depth,
        role=role,
        automation_id=automation_id,
        driven_by_the_mouse=driven_by_the_mouse,
        offscreen=offscreen,
    )


def _a_window(name: str) -> TreeNode:
    return _a_control("WindowControl", name, depth=0)


def _a_walk_of(*nodes: TreeNode) -> Walk:
    return Walk(nodes=nodes)


def _the_tree_of(walk: Walk) -> list[str]:
    """Just the control lines: the header and the footer are other specs' work."""
    past_the_header = str(dump_of(walk)).splitlines()[1:]
    return list(takewhile(lambda line: line.strip(), past_the_header))


def test_a_dump_of_a_window_with_no_controls_in_it_names_the_window_and_says_so() -> (
    None
):
    # Given a walk that found the window and nothing underneath it
    walk = _a_walk_of(_a_window(CANVAS_FIXTURE))

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then the window is named, and its own line says what it is rather than
    # offering a query: `app` already means this window
    assert repr(CANVAS_FIXTURE) in rendered, (
        f"a dump that does not name the window it was taken of is unreadable "
        f"the moment two are printed: {rendered}"
    )
    assert "the window this dump was taken of" in rendered, (
        f"the root needs a tail like every other line, or the load-bearing "
        f"column starts one row late: {rendered}"
    )


def test_a_button_with_an_accessible_name_is_reported_as_the_query_that_would_find_it() -> (
    None
):
    # Given a window with one named button under it
    walk = _a_walk_of(
        _a_window(WINFORMS_FIXTURE),
        _a_control("ButtonControl", NEW_TASK, role=Role.BUTTON),
    )

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then the button's line carries the call that would drive it, verbatim.
    # Naming the control without naming the query leaves the reader to guess
    # the mapping from control type to method, which is the whole thing they
    # came here not knowing
    assert 'app.button("New Task")' in rendered, (
        f"a dump that stops at the control type has answered half the "
        f"question: {rendered}"
    )


def test_a_textbox_and_a_label_are_reported_as_their_own_queries_rather_than_as_buttons() -> (
    None
):
    # Given a window carrying one of each of the other two roles a query has
    walk = _a_walk_of(
        _a_window(WINFORMS_FIXTURE),
        _a_control("EditControl", "Title", role=Role.TEXTBOX),
        _a_control("TextControl", "ready", role=Role.TEXT),
    )

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then each names its own call. Telling a reader to write `app.button` for
    # an edit control is worse than saying nothing: it is a line that will
    # compile, run, and never find anything
    assert 'app.textbox("Title")' in rendered, (
        f"an edit control's query is textbox, not button: {rendered}"
    )
    assert 'app.text("ready")' in rendered, (
        f"a static label's query is text, not button: {rendered}"
    )


def test_a_control_of_a_role_no_query_asks_for_says_no_query_reaches_it_instead_of_being_omitted() -> (
    None
):
    # Given a window whose button sits inside a layout pane, which is a control
    # type this plugin's three roles do not map onto
    walk = _a_walk_of(
        _a_window(WINFORMS_FIXTURE),
        _a_control("PaneControl", "the panel", depth=1),
        _a_control("ButtonControl", NEW_TASK, depth=2, role=Role.BUTTON),
    )

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then the pane is still on the page, saying why nothing addresses it. A
    # dump that printed only what it can reach would be a clean tree that
    # quietly disagrees with the window on screen, and the reader would have no
    # way to tell a control that was skipped from one that is not there
    assert "'the panel'" in rendered, (
        f"a control this plugin cannot query was dropped from a dump whose "
        f"whole promise is that it shows what is there: {rendered}"
    )
    assert "no query: PaneControl is not a role this plugin asks for" in rendered, (
        f"the reason has to name the control type, or the reader cannot tell "
        f"whether it is their app or this plugin that is the limit: {rendered}"
    )


def test_a_control_whose_accessible_name_is_empty_says_it_has_nothing_to_match_on() -> (
    None
):
    # Given a button of exactly the type a query asks for, carrying no name —
    # which is every widget of a Tk window nobody has annotated
    walk = _a_walk_of(
        _a_window(WINFORMS_FIXTURE),
        _a_control("ButtonControl", "", role=Role.BUTTON),
    )

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then it says what is missing, rather than offering `app.button("")`. That
    # line would be a query the reader could paste and watch fail, about a
    # button that is genuinely on screen — the exact confusion this feature
    # exists to end
    assert 'app.button("")' not in rendered, (
        f"a query nothing can match must never be offered as one: {rendered}"
    )
    assert "no query: it has no accessible name to match on" in rendered, (
        f"an unnamed control of a queryable role is the finding, and it has to "
        f"be stated as one: {rendered}"
    )


def test_a_container_with_no_children_says_that_what_it_shows_is_paint() -> None:
    # Given a window whose whole interface is one canvas: a pane of a type no
    # query asks for, with nothing at all underneath it
    walk = _a_walk_of(
        _a_window(CANVAS_FIXTURE),
        _a_control("PaneControl", "", depth=1),
    )

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then it reports the finding rather than the taxonomy. "PaneControl is not
    # a role this plugin asks for" invites the reader to go looking inside it;
    # there is nothing inside it, and that — not the control type — is why no
    # tool that reads names will ever help them here
    assert "no query: nothing inside it, so what it shows is paint" in rendered, (
        f"an empty container is the whole diagnosis for a canvas-drawn window, "
        f"and it has to outrank the generic reason: {rendered}"
    )


def test_two_controls_sharing_a_role_and_a_name_are_both_reported_as_ambiguous() -> (
    None
):
    # Given a window carrying the same button caption twice, which is what a
    # wizard reusing Next, Back and OK looks like from outside
    walk = _a_walk_of(
        _a_window(TK_FIXTURE),
        _a_control("ButtonControl", CONFIRM, role=Role.BUTTON),
        _a_control("ButtonControl", CONFIRM, role=Role.BUTTON),
    )

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then neither line offers the query, and both say how many controls answer
    # it. Printing it twice would hand the reader a line that resolves to
    # whichever control the tree happens to offer first — a passing test about
    # a control nobody chose
    assert rendered.count('ambiguous: 2 controls answer app.button("Confirm")') == 2, (
        f"both halves of a collision have to be marked, or the reader takes "
        f"the unmarked one for the answer: {rendered}"
    )


def test_a_control_inside_a_child_window_is_reported_as_a_query_scoped_to_that_dialog() -> (
    None
):
    # Given a settings dialog open over the main window, with a box in it
    walk = _a_walk_of(
        _a_window(TK_FIXTURE),
        _a_control("WindowControl", SETTINGS, depth=1),
        _a_control("EditControl", "Folder", depth=2, role=Role.TEXTBOX),
    )

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then the box's query says which window it means. The unscoped call would
    # also find it today — a search runs over the main window's whole subtree,
    # and the dialog is inside that — which is exactly why the scoped one is
    # the line worth pasting: it goes on meaning this box when the next step of
    # the wizard reuses the caption
    assert 'app.dialog("Settings").textbox("Folder")' in rendered, (
        f"a control inside a dialog has to be offered as the dialog's, or the "
        f"reader learns the wrong idiom from the tool that taught them: "
        f"{rendered}"
    )


def test_a_dialogs_own_control_is_not_ambiguous_with_one_of_the_same_name_outside_it() -> (
    None
):
    # Given the collision the dialog API exists for: a Confirm in the settings
    # window and a Confirm on the main window underneath it
    walk = _a_walk_of(
        _a_window(TK_FIXTURE),
        _a_control("ButtonControl", CONFIRM, role=Role.BUTTON),
        _a_control("WindowControl", SETTINGS, depth=1),
        _a_control("ButtonControl", CONFIRM, depth=2, role=Role.BUTTON),
    )

    # When the dump is read as text
    tree = _the_tree_of(walk)
    rendered = "\n".join(tree)

    # Then the unscoped call is reported as reaching both, and the scoped one
    # is offered plainly, because it reaches exactly one. Marking the dialog's
    # button ambiguous as well would be the dump contradicting the feature it
    # is documenting: `app.dialog("Settings").button("Confirm")` is not
    # ambiguous, and telling a reader it is sends them back to coordinates
    assert 'ambiguous: 2 controls answer app.button("Confirm")' in rendered, (
        f"the unscoped call reaches into the dialog too, and has to say so: {rendered}"
    )
    assert 'app.dialog("Settings").button("Confirm")' in rendered, (
        f"the scoped call resolves the collision, which is the finding this "
        f"whole line exists to deliver: {rendered}"
    )
    assert rendered.count("ambiguous") == 1, (
        f"only the query that really is ambiguous may be marked: {rendered}"
    )


def test_a_child_window_is_itself_reported_as_the_dialog_call_that_addresses_it() -> (
    None
):
    # Given a settings dialog open over the main window
    walk = _a_walk_of(
        _a_window(TK_FIXTURE),
        _a_control("WindowControl", SETTINGS, depth=1),
    )

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then the dialog's own line is the call that addresses it, not a report
    # that WindowControl is a role nothing asks for. It is the one line the
    # reader needs before any of the scoped lines under it mean anything
    assert 'app.dialog("Settings")' in rendered, (
        f"the dialog is addressable and the dump has to say so: {rendered}"
    )
    assert "no query" not in rendered, (
        f"a control this plugin can reach must never be reported as one it "
        f"cannot: {rendered}"
    )


def test_the_indentation_of_a_line_is_the_depth_of_the_control_it_describes() -> None:
    # Given a window, a dialog inside it, and a box inside that
    walk = _a_walk_of(
        _a_window(TK_FIXTURE),
        _a_control("WindowControl", SETTINGS, depth=1),
        _a_control("EditControl", "Folder", depth=2, role=Role.TEXTBOX),
    )

    # When the dump is read line by line
    lines = _the_tree_of(walk)

    # Then each line is indented by its own depth, which is the only thing that
    # says a control is *inside* another rather than beside it — and what is
    # inside what is half of the answer a reader came for
    assert lines[0].startswith("WindowControl"), f"the root is not indented: {lines}"
    assert lines[1].startswith("  WindowControl"), (
        f"a control one level down is indented one level: {lines}"
    )
    assert lines[2].startswith("    EditControl"), (
        f"a control two levels down is indented two: {lines}"
    )


def test_the_queries_line_up_in_one_column_without_any_name_being_cut_to_fit() -> None:
    # Given controls whose names are nothing like the same length, one of them
    # longer than any sane column
    a_long_name = "Save the document you have been working on for the last hour"
    walk = _a_walk_of(
        _a_window(WINFORMS_FIXTURE),
        _a_control("ButtonControl", "OK", role=Role.BUTTON),
        _a_control("EditControl", "Title", depth=2, role=Role.TEXTBOX),
        _a_control("ButtonControl", a_long_name, role=Role.BUTTON),
    )

    # When the dump is read line by line
    lines = _the_tree_of(walk)

    # Then the queries of the ordinary lines start in the same column, because
    # a column a reader's eye can follow is the whole reason for the padding
    assert lines[1].index("app.") == lines[2].index("app."), (
        f"the load-bearing column has to be a column: {lines}"
    )
    # and the long name is whole. Truncating it would be a wrong answer to the
    # only question this feature exists to answer, and a silent one: nothing on
    # the line would say the name had been shortened
    assert a_long_name in lines[3], (
        f"a name cut to fit the layout is a name that will never be found: {lines[3]}"
    )
    assert lines[3].endswith(f'app.button("{a_long_name}")'), (
        f"an over-long head pushes its query right rather than losing it: {lines[3]}"
    )


def _a_window_with_its_chrome(*controls: TreeNode) -> Walk:
    """The window a real walk sees: the app's controls, then its own title bar."""
    return _a_walk_of(
        _a_window(WINFORMS_FIXTURE),
        *controls,
        _a_control("TitleBarControl", "", depth=1),
        _a_control("ButtonControl", "Minimize", depth=2, role=Role.BUTTON),
        _a_control("ButtonControl", "Maximize", depth=2, role=Role.BUTTON),
        _a_control("ButtonControl", "Close", depth=2, role=Role.BUTTON),
    )


def test_the_window_chrome_is_folded_into_one_line_that_counts_what_it_hid() -> None:
    # Given the window every real walk sees: one control of the application's
    # own, and a title bar carrying three buttons Windows put there
    walk = _a_window_with_its_chrome(
        _a_control("ButtonControl", NEW_TASK, role=Role.BUTTON)
    )

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then the title bar's buttons are one line, not three. Half of a small
    # window's tree is chrome, and a reader looking for their own control
    # should not have to step over Windows' furniture to find it
    assert 'app.button("Minimize")' not in rendered, (
        f"chrome the reader did not write and cannot change is noise in the "
        f"one column they came to read: {rendered}"
    )
    # and the fold is stated, counted, named and reversible — which is what
    # separates trimming noise from quietly omitting. Anything the dump will
    # not show, it says it is not showing
    assert "3 more controls folded" in rendered, (
        f"a fold nobody is told about is an omission: {rendered}"
    )
    assert "Minimize, Maximize, Close" in rendered, (
        f"naming what was folded is what makes it checkable: {rendered}"
    )
    assert "with_window_chrome()" in rendered, (
        f"the fold has to name the call that undoes it: {rendered}"
    )


def test_a_finding_too_long_for_the_line_wraps_where_a_query_of_the_same_length_would_not() -> (
    None
):
    # Given a window whose chrome notice is longer than a terminal line, and a
    # control whose query is longer than one too
    a_long_name = "Save the document you have been working on for the last hour"
    walk = _a_window_with_its_chrome(
        _a_control("ButtonControl", a_long_name, role=Role.BUTTON),
    )

    # When the dump is read line by line
    lines = _the_tree_of(walk)

    # Then the prose is wrapped under its own column, so a reader on an
    # ordinary terminal sees it rather than a wall of soft-wrapped text
    folded = [line for line in lines if "folded" in line or "chrome" in line]
    assert len(folded) > 1, (
        f"a notice that runs off the right of the terminal has told nobody "
        f"anything: {lines}"
    )
    assert all(len(line) <= 88 for line in folded), (
        f"the wrap has to actually fit: {folded}"
    )
    assert folded[1].startswith(" " * (folded[0].index("3 more"))), (
        f"a continuation that does not line up under the column reads as a "
        f"line about a different control: {folded}"
    )
    # and the query is not wrapped, whatever its length. A query broken across
    # two lines cannot be pasted, and this one would break inside its own
    # quoted name — where the break is invisible
    pasteable = [line for line in lines if line.endswith(f'"{a_long_name}")')]
    assert len(pasteable) == 1, (
        f"the one thing on the page that has to survive a copy and paste is "
        f"the query: {lines}"
    )


def test_a_dump_whose_chrome_is_asked_for_lists_every_control_that_was_folded() -> None:
    # Given the same window, whose title bar the default rendering folds away
    walk = _a_window_with_its_chrome(
        _a_control("ButtonControl", NEW_TASK, role=Role.BUTTON)
    )

    # When the reader asks for the chrome back
    rendered = dump_of(walk).with_window_chrome()

    # Then every folded control is a line of its own, with its own query. The
    # fold is a rendering choice and this is the other rendering — which is
    # what makes the fold a fold rather than a deletion
    assert 'app.button("Minimize")' in rendered, (
        f"a fold that cannot be undone is an omission with a footnote: {rendered}"
    )
    assert 'app.button("Close")' in rendered, (
        f"`app.button('Close')` really does match a title bar's X, and that is "
        f"worth knowing: {rendered}"
    )
    assert "folded" not in rendered, (
        f"nothing is folded here, so nothing may claim to be: {rendered}"
    )


def _a_window_of_every_kind() -> Walk:
    """One of each: addressable, twice-ambiguous, unreachable, and chrome."""
    return _a_window_with_its_chrome(
        _a_control("ButtonControl", NEW_TASK, role=Role.BUTTON),
        _a_control("ButtonControl", CONFIRM, role=Role.BUTTON),
        _a_control("ButtonControl", CONFIRM, role=Role.BUTTON),
        _a_control("PaneControl", "", depth=1),
    )


def test_the_header_counts_every_control_walked_across_its_four_categories() -> None:
    # Given a window with one of everything in it
    walk = _a_window_of_every_kind()

    # When the dump is read as text
    header = str(dump_of(walk)).splitlines()[0]

    # Then the first line names the window and accounts for every control it
    # walked. The title bar itself is unreachable, its three buttons are
    # chrome, and both Confirms are ambiguous
    assert header == (
        "'pytest-uia WinForms Fixture' -- 9 controls: 1 addressable, "
        "2 ambiguous, 2 unreachable, 3 chrome"
    ), f"the header is the summary a reader checks the rest against: {header}"
    # and the four categories plus the window itself add up to the total. A
    # count that does not add up is the exact failure this feature exists to
    # avoid: it would mean the dump had walked something it did not report
    counted = [int(word) for word in header.replace(",", " ").split() if word.isdigit()]
    total, categories = counted[0], counted[1:]
    assert total == sum(categories) + 1, (
        f"every control walked is in exactly one category, plus the window "
        f"itself: {header}"
    )


def test_a_window_where_nothing_is_addressable_says_so_instead_of_listing_no_queries() -> (
    None
):
    # Given the canvas fixture: one pane, nothing in it, nothing named
    walk = _a_walk_of(
        _a_window(CANVAS_FIXTURE),
        _a_control("PaneControl", "", depth=1),
    )

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then the list of queries is there and its emptiness is spelled out with
    # what to do instead. A heading over nothing reads like a bug in the tool,
    # and the reader's next move — pixels, or annotating an app they own — is
    # the whole finding here
    assert "queries this window authorises:" in rendered, (
        f"the summary a reader scrolls to has to be there even when it is "
        f"empty: {rendered}"
    )
    assert (
        "(none: nothing in this window carries a name a query can match" in rendered
    ), f"an empty list must say why it is empty: {rendered}"
    assert "tk_uia.enable(root)" in rendered, (
        f"for the commonest cause of an empty list there is a one-line fix, "
        f"and this is where it is worth knowing: {rendered}"
    )


def _the_footer_of(walk: Walk) -> list[str]:
    """The query list only, stripped of its heading and its indent."""
    lines = str(dump_of(walk)).splitlines()
    heading = lines.index("queries this window authorises:")
    return [line.strip() for line in lines[heading + 1 :]]


def test_the_queries_a_window_authorises_are_gathered_at_the_foot_in_tree_order() -> (
    None
):
    # Given a window with a dialog open over it and one caption used twice
    walk = _a_walk_of(
        _a_window(TK_FIXTURE),
        _a_control("ButtonControl", "Open Settings", role=Role.BUTTON),
        _a_control("ButtonControl", CONFIRM, role=Role.BUTTON),
        _a_control("WindowControl", SETTINGS, depth=1),
        _a_control("EditControl", "Folder", depth=2, role=Role.TEXTBOX),
        _a_control("ButtonControl", CONFIRM, depth=2, role=Role.BUTTON),
    )

    # When the dump's closing list is read
    authorised = _the_footer_of(walk)

    # Then it is every unambiguous query, scoped, in the order the tree gave
    # them — and the ambiguous one is not in it, because a list of things that
    # work must not include the one that does not
    assert authorised == [
        'app.button("Open Settings")',
        'app.dialog("Settings")',
        'app.dialog("Settings").textbox("Folder")',
        'app.dialog("Settings").button("Confirm")',
    ], f"the copy-paste list is the deliverable of the whole feature: {authorised}"


def test_a_control_this_plugin_will_drive_with_the_mouse_is_marked_and_the_marker_is_explained() -> (
    None
):
    # Given a Tk button: a control the generic MSAA proxy speaks for, so this
    # plugin declines its Invoke pattern and uses the real pointer instead
    walk = _a_walk_of(
        _a_window(TK_FIXTURE),
        _a_control(
            "ButtonControl", NEW_TASK, role=Role.BUTTON, driven_by_the_mouse=True
        ),
    )

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then the line carries the marker, after the query rather than instead of
    # it — the control is perfectly addressable, and only the way it is driven
    # differs
    assert 'app.button("New Task")  [mouse]' in rendered, (
        f"the marker belongs after the query, not in place of it: {rendered}"
    )
    # and the legend states what *this plugin* will do. Measured, a title bar's
    # buttons are marked and their Invoke works fine, so a dump that said the
    # control did not support it would be making a false statement about
    # somebody's application
    assert "pytest-uia will not act through" in rendered, (
        f"the marker describes this plugin's own rule, and has to be worded as "
        f"one: {rendered}"
    )
    assert "It uses the real pointer and keyboard instead" in rendered, (
        f"the reader needs to know what happens instead, because that is the "
        f"half that a refused foreground can block: {rendered}"
    )


def test_a_marker_nothing_in_the_dump_carries_is_not_explained_at_the_bottom_of_it() -> (
    None
):
    # Given a WinForms window, every control of which this plugin drives
    # through its accessibility patterns
    walk = _a_walk_of(
        _a_window(WINFORMS_FIXTURE),
        _a_control("ButtonControl", NEW_TASK, role=Role.BUTTON),
    )

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then there is no legend, because there is nothing to explain. A paragraph
    # about a marker no line carries is four lines of noise that make a reader
    # hunt the tree for something that is not in it
    assert "[mouse]" not in rendered, (
        f"a legend for an absent marker is an answer to a question nobody "
        f"asked: {rendered}"
    )


def test_a_control_that_is_in_the_tree_but_off_screen_is_marked_as_such() -> None:
    # Given a control the window carries with no pixels of its own — a wizard
    # step not on this page yet, a panel behind a tab
    walk = _a_walk_of(
        _a_window(WINFORMS_FIXTURE),
        _a_control("ButtonControl", NEW_TASK, role=Role.BUTTON, offscreen=True),
    )

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then the query is offered with the warning attached. Being in the tree is
    # not being on screen, and an unmarked line here would send the reader off
    # with a query that resolves to something nobody can click
    assert 'app.button("New Task")  [offscreen]' in rendered, (
        f"a control with no pixels is the confusing case wait_visible exists "
        f"for, and the dump is where it is cheapest to say so: {rendered}"
    )
    assert "wait_visible" in rendered, (
        f"the marker has to name the call that waits it out: {rendered}"
    )


def test_a_control_whose_provider_stopped_answering_is_named_rather_than_dropped() -> (
    None
):
    # Given a control that was walked and then stopped answering — a child
    # window destroyed while the dump was being taken
    walk = _a_walk_of(
        _a_window(WINFORMS_FIXTURE),
        _a_control("ButtonControl", NEW_TASK, role=Role.BUTTON),
        TreeNode(control_type="", name="", depth=1, readable=False),
    )

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then it holds a line of its own saying what happened to it. Dropping it
    # would be the silent omission this whole design refuses, and aborting the
    # dump would throw away every control that did answer
    assert "<unreadable>" in rendered, (
        f"a control that was there and then was not is still a fact about the "
        f"window: {rendered}"
    )
    assert (
        "its provider stopped answering while this dump was being taken" in rendered
    ), (
        f"the reader has to be told this is the dump's problem and not their "
        f"application's: {rendered}"
    )
    assert 'app.button("New Task")' in rendered, (
        f"one dead control must not cost the reader the rest of the window: {rendered}"
    )


def test_an_automation_id_is_shown_beside_the_name_and_never_offered_as_a_query() -> (
    None
):
    # Given a control whose application gave it an automation id of its own
    walk = _a_walk_of(
        _a_window(TK_FIXTURE),
        _a_control("ButtonControl", NEW_TASK, role=Role.BUTTON, automation_id="4207"),
    )

    # When the dump is read line by line
    lines = _the_tree_of(walk)

    # Then the id is on the line, because it is the other identifier a reader
    # may already have from Accessibility Insights
    assert "id=4207" in lines[1], (
        f"an id the application set deliberately is worth reporting: {lines[1]}"
    )
    # and the query is still by name. v1 cannot search by automation id at all,
    # and for WinForms it is HWND-derived and changes on every launch — so a
    # dump that offered one would be handing out a test that passes today
    assert lines[1].endswith('app.button("New Task")'), (
        f"the load-bearing column is the query, and the query is the name: {lines[1]}"
    )


def test_a_dump_that_hit_the_node_cap_says_there_are_more_and_names_the_call_that_raises_it() -> (
    None
):
    # Given a walk that stopped because it had seen as many controls as it was
    # allowed to, with the tree still going
    walk = Walk(
        nodes=(
            _a_window(WINFORMS_FIXTURE),
            _a_control("ButtonControl", NEW_TASK, role=Role.BUTTON),
        ),
        ended=WalkEnded.HIT_THE_NODE_CAP,
        limits=DumpLimits(max_nodes=2),
    )

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then it says the tree went on. A truncated dump that read like a complete
    # one is the one failure this feature cannot afford: the reader would
    # conclude their control does not exist
    assert "stopped after 2 controls and there are more" in rendered, (
        f"a cap that bit in silence turns a diagnostic into a wrong answer: {rendered}"
    )
    # and it names the call that lifts it, because "there are more" without the
    # cure is a dead end
    assert "app.dump(limits=DumpLimits(max_nodes=20))" in rendered, (
        f"the notice has to carry the line that gets the rest: {rendered}"
    )


def test_a_dump_that_ran_out_of_time_says_which_window_was_answering_slowly() -> None:
    # Given a walk that ran out of wall clock rather than out of allowance —
    # measured, `Program Manager` answers five controls in 4.1 seconds, so this
    # is what a node cap cannot catch
    walk = Walk(
        nodes=(
            _a_window(WINFORMS_FIXTURE),
            _a_control("ButtonControl", NEW_TASK, role=Role.BUTTON),
        ),
        ended=WalkEnded.RAN_OUT_OF_TIME,
        limits=DumpLimits(budget=5.0),
    )

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then it blames the right thing. Two controls in five seconds is not a big
    # window and the reader must not go looking for one; it is a provider that
    # is slow to answer, and that is a different problem with a different cure
    assert "stopped after 5.0s and 2 controls" in rendered, (
        f"a time budget that bit has to say it was time, not size: {rendered}"
    )
    assert "this window's provider is answering slowly" in rendered, (
        f"the reader needs the diagnosis, not just the symptom: {rendered}"
    )
    assert "app.dump(limits=DumpLimits(budget=30.0))" in rendered, (
        f"and the call that gives it longer: {rendered}"
    )


def test_a_dump_offers_its_queries_as_data_so_a_test_can_assert_on_them_without_reading_text() -> (
    None
):
    # Given a window with a dialog and a collision in it
    walk = _a_walk_of(
        _a_window(TK_FIXTURE),
        _a_control("ButtonControl", "Open Settings", role=Role.BUTTON),
        _a_control("ButtonControl", CONFIRM, role=Role.BUTTON),
        _a_control("WindowControl", SETTINGS, depth=1),
        _a_control("ButtonControl", CONFIRM, depth=2, role=Role.BUTTON),
    )

    # When a caller asks for the queries rather than the page
    queries = dump_of(walk).queries

    # Then they arrive as values. A test asserting on a rendered tree pins
    # column positions and breaks the next time a word changes; this is the
    # promise, and the layout stays free to move
    assert queries == (
        'app.button("Open Settings")',
        'app.dialog("Settings")',
        'app.dialog("Settings").button("Confirm")',
    ), f"the structure behind the text has to be reachable: {queries}"


def test_the_dumps_own_words_stay_ascii_while_an_applications_name_passes_through() -> (
    None
):
    # Given a control named in a language the developer's console may not be
    # able to encode
    walk = _a_walk_of(
        _a_window("Fixture"),
        _a_control("ButtonControl", "Speichern (überschreiben)", role=Role.BUTTON),
    )

    # When the dump is read as text
    rendered = str(dump_of(walk))

    # Then the name is passed through exactly as the application gave it
    assert "Speichern (überschreiben)" in rendered, (
        f"the accessible name is the application's word and the answer to the "
        f"question being asked; it is not the dump's to normalise: {rendered}"
    )
    # and everything the dump wrote itself is ASCII. A console under cp1252, or
    # stdout redirected to a file, raises UnicodeEncodeError on an arrow or an
    # em dash — which would turn a diagnostic into a crash on exactly the
    # machines this plugin targets
    ours = rendered.replace("Speichern (überschreiben)", "")
    assert ours.isascii(), (
        f"the plugin's own furniture has to survive a cp1252 console: {ours!r}"
    )
