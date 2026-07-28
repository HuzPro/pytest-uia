"""pytest-uia: Windows GUI acceptance testing through the accessibility tree.

The names re-exported here are the whole public surface. Everything they are
built from (locators, adapters, retry policies) is an implementation detail
that a test should never have to name. Importing this module pulls in no
Windows-only dependency: the UIA adapter is loaded when a session is first
wired to a real desktop, not before.
"""

from pytest_uia.application.driver import App, Dialog, UIElement
from pytest_uia.application.session import GuiSession
from pytest_uia.domain.dump import Dump
from pytest_uia.domain.errors import (
    DialogNotFound,
    DialogStillOpen,
    ElementNotFound,
    InputRefused,
    LaunchFailed,
    ProcessStillRunning,
    TextNeverSettled,
    WindowNotFound,
)
from pytest_uia.domain.query import Query, Role
from pytest_uia.domain.tree import DumpLimits, TreeNode, WalkEnded

__version__ = "0.7.1"

__all__ = [
    "App",
    "Dialog",
    "DialogNotFound",
    "DialogStillOpen",
    "Dump",
    "DumpLimits",
    "ElementNotFound",
    "GuiSession",
    "InputRefused",
    "LaunchFailed",
    "ProcessStillRunning",
    "Query",
    "Role",
    "TextNeverSettled",
    "TreeNode",
    "UIElement",
    "WalkEnded",
    "WindowNotFound",
    "__version__",
]
