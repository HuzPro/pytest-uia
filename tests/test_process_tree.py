"""Behavioral spec for treating a launched application as the tree it really is.

The motivating failure is everyday rather than exotic: on Windows the
`python.exe` inside a virtual environment is a launcher that starts the real
interpreter as a *child*, so the pid a launch reports owns no window at all and
the window that appears belongs to a pid nobody ever returned. Anything started
through a shim — a console script, a `.bat`, a launcher — behaves the same way.
"""

from __future__ import annotations

from pytest_uia.adapters.process_tree import family_of

_LAUNCHER = 1480
_INTERPRETER = 18220
_A_WORKER = 20304
_SOMETHING_ELSE = 999


def test_a_process_that_started_nothing_is_a_family_of_one() -> None:
    # Given a snapshot in which nobody was started by the launched process
    parents = {_LAUNCHER: 4, _SOMETHING_ELSE: 4}

    # When its family is worked out
    family = family_of(_LAUNCHER, parents)

    # Then it is just itself, so the ordinary case costs nothing
    assert family == {_LAUNCHER}, (
        "a process with no children still has to own its own window"
    )


def test_the_family_of_a_launcher_includes_the_interpreter_it_started() -> None:
    # Given the shape every `.venv\\Scripts\\python.exe app.py` launch has
    parents = {_LAUNCHER: 4, _INTERPRETER: _LAUNCHER}

    # When the launcher's family is worked out
    family = family_of(_LAUNCHER, parents)

    # Then the process that will own the window is in it
    assert family == {_LAUNCHER, _INTERPRETER}, (
        "the pid a launch reports is the launcher's; the window is the child's"
    )


def test_a_grandchild_belongs_to_the_family_however_the_snapshot_is_ordered() -> None:
    # Given a snapshot listing the grandchild before the child that owns it,
    # which is what an OS-ordered walk of the process table routinely hands back
    parents = {_A_WORKER: _INTERPRETER, _INTERPRETER: _LAUNCHER}

    # When the launcher's family is worked out
    family = family_of(_LAUNCHER, parents)

    # Then descent is followed to the end rather than one generation deep
    assert family == {_LAUNCHER, _INTERPRETER, _A_WORKER}, (
        "a single pass over the snapshot only finds the children it happens to "
        "meet after their parent"
    )


def test_a_process_started_by_somebody_else_is_not_part_of_the_family() -> None:
    # Given another application entirely, running beside the one under test
    parents = {_INTERPRETER: _LAUNCHER, _SOMETHING_ELSE: 4}

    # When the launcher's family is worked out
    family = family_of(_LAUNCHER, parents)

    # Then it does not sweep in the developer's own windows
    assert _SOMETHING_ELSE not in family, (
        "a family that grows past the launched app makes 'its window' meaningless"
    )


def test_a_process_listed_as_its_own_parent_does_not_loop_forever() -> None:
    # Given the real process table, in which the idle process parents itself
    parents = {0: 0, _LAUNCHER: 0}

    # When a family is worked out from it
    family = family_of(0, parents)

    # Then the walk terminates, because a snapshot is not a guaranteed tree
    assert family == {0, _LAUNCHER}, "a cycle in the snapshot must not hang a lookup"
