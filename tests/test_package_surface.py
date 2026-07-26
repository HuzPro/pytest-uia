"""Spec for what `import pytest_uia` gives a user without further ceremony.

A conftest that builds its own session, or a helper that type-annotates an
`App`, should not have to know which sub-package a name lives in.
"""

from __future__ import annotations

from pathlib import Path

import pytest_uia


def test_the_package_exports_the_types_a_user_writes_a_conftest_against() -> None:
    # When a user imports the package and nothing else
    exported = set(pytest_uia.__all__)

    # Then the names their own code has to spell are already there, including
    # every failure a test might reasonably want to catch by name
    assert {
        "App",
        "UIElement",
        "GuiSession",
        "ElementNotFound",
        "InputRefused",
        "TextNeverSettled",
    } <= exported, (
        f"the public surface hides names a user has to import anyway: {exported}"
    )
    assert all(hasattr(pytest_uia, name) for name in exported), (
        "a name in __all__ that is not actually bound breaks `from pytest_uia import *`"
    )


def test_the_installed_package_carries_the_marker_that_publishes_its_types() -> None:
    # When a type checker looks beside the package for PEP 561's marker
    marker = Path(pytest_uia.__file__).parent / "py.typed"

    # Then it is there, because without it every annotation in this package is
    # invisible downstream however complete it is
    assert marker.is_file(), (
        "a package with no py.typed is treated as untyped, and the `Typing :: "
        "Typed` classifier then advertises something that is not true"
    )
