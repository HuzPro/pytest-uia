"""Spec for what `import pytest_uia` gives a user without further ceremony.

A conftest that builds its own session, or a helper that type-annotates an
`App`, should not have to know which sub-package a name lives in.
"""

from __future__ import annotations

import pytest_uia


def test_the_package_exports_the_types_a_user_writes_a_conftest_against() -> None:
    # When a user imports the package and nothing else
    exported = set(pytest_uia.__all__)

    # Then the names their own code has to spell are already there
    assert {"App", "UIElement", "GuiSession", "ElementNotFound"} <= exported, (
        f"the public surface hides names a user has to import anyway: {exported}"
    )
    assert all(hasattr(pytest_uia, name) for name in exported), (
        "a name in __all__ that is not actually bound breaks `from pytest_uia import *`"
    )
