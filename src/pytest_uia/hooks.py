"""The only module in this package that imports pytest.

Loads through the ``pytest11`` entry point (:mod:`pytest_uia.plugin`) once the
package is installed. Everything below is a thin shell: options are read here
and handed to :mod:`pytest_uia.application.session`, which owns the behaviour.

Responsibilities, in order:

* register ``--uia-timeout``, the implicit wait every element lookup inherits;
* register the ``gui`` marker in :func:`pytest_configure`, so a project using
  this plugin gets it without adding anything to its own ini file;
* provide the function-scoped :func:`gui` fixture, which hands out a
  :class:`~pytest_uia.application.session.GuiSession` and, whatever the test
  did with it, shuts down everything that session started.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

import pytest

from pytest_uia.application.driver import DEFAULT_POLICY
from pytest_uia.application.session import GuiSession, session_on_this_desktop
from pytest_uia.domain.waiting import RetryPolicy

_TIMEOUT_OPTION = "--uia-timeout"

GUI_MARKER = (
    "gui: spawns and drives real windows on the local desktop "
    "(deselect with '-m \"not gui\"')"
)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("uia", "Windows GUI testing through the accessibility tree")
    group.addoption(
        _TIMEOUT_OPTION,
        action="store",
        type=float,
        default=DEFAULT_POLICY.timeout,
        metavar="SECONDS",
        help=(
            "How long every element lookup keeps retrying before it fails, in "
            "seconds. Raise it for applications that are slow to repaint; "
            "individual lookups can still override it with timeout=."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    # Registered here rather than expecting every downstream project to add it
    # to its own ini file, which would make --strict-markers error on a marker
    # this plugin is the only source of.
    config.addinivalue_line("markers", GUI_MARKER)


@pytest.fixture
def gui(request: pytest.FixtureRequest) -> Iterator[GuiSession]:
    """A session that owns every app the test launches, and outlives none of them."""
    session = session_on_this_desktop(policy=_implicit_wait_from(request.config))
    try:
        yield session
    finally:
        # Unconditional: a test that fails halfway through is exactly the test
        # that leaves a window on screen for every run after it.
        session.shutdown_all()


def _implicit_wait_from(config: pytest.Config) -> RetryPolicy:
    return replace(DEFAULT_POLICY, timeout=config.getoption(_TIMEOUT_OPTION))
