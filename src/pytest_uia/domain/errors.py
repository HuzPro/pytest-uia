"""Failures the domain raises when the desktop does not match what a test asked for.

Every adapter translates its own technology's misses into these, so a test never
has to read a comtypes HRESULT or a WinRT exception.
"""

from __future__ import annotations


class ElementNotFound(Exception):
    """No locator in the chain could resolve the query to an on-screen element."""


class WindowNotFound(Exception):
    """A launched application owns no visible top-level window (yet)."""
