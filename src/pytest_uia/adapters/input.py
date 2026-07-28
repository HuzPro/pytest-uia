"""Adapter over Win32 synthetic input: the mouse, and Windows' answer about it.

Windows can silently drop injected input while another window holds the
foreground, so every send checks the return value and raises `InputRefused`
naming the foreground holder; the driver retries it inside the implicit wait.
`ctypes.windll` is reached lazily so the module imports off Windows.
"""

from __future__ import annotations

import ctypes
from typing import Protocol

from pytest_uia.domain.errors import InputRefused

_MOUSE_EVENT = 0
_LEFT_BUTTON_DOWN = 0x0002
_LEFT_BUTTON_UP = 0x0004
_A_PRESS_AND_A_RELEASE = 2
_LONGEST_WINDOW_CLASS_NAME = 256


class PointerInput(Protocol):
    """The mouse, as the only elements that need one are allowed to see it."""

    def click(self, x: int, y: int) -> None: ...


class SyntheticMouse(Protocol):
    """Win32's mouse, kept behind a seam so refusal is testable without one."""

    def click_at(self, x: int, y: int) -> bool: ...

    def foreground_holder(self) -> str: ...


class CheckedPointer:
    """Adapter presenting a synthetic mouse as the pointer elements act through."""

    def __init__(self, mouse: SyntheticMouse) -> None:
        self._mouse = mouse

    def click(self, x: int, y: int) -> None:
        if not self._mouse.click_at(x, y):
            raise InputRefused(self._why_windows_dropped_it())

    def _why_windows_dropped_it(self) -> str:
        # A bare reason, not a sentence: the caller that owns the deadline
        # prefixes it with how long it kept trying before giving up.
        return (
            f"the foreground is held by {self._mouse.foreground_holder()}, which "
            "runs at a higher integrity level than this process, so Windows "
            "drops every event this process injects; close that window, stop "
            "the service behind it, or run the suite elevated"
        )


class Win32Mouse:
    """The user32 calls a click is made of, with the answers they hand back.

    Humble object: no decision worth a unit test, only ctypes plumbing. The
    refusal is specified against :class:`CheckedPointer` with doubles.
    """

    def click_at(self, x: int, y: int) -> bool:
        if not self._cursor_moved_to(x, y):
            # Checked on its own, and first: a refused move injects nothing, so
            # there is no half-pressed button to undo before the next attempt.
            return False
        return self._left_button_pressed_and_released()

    def foreground_holder(self) -> str:
        window = _foreground_window()
        if window is None:
            # Windows answers NULL while no window on this desktop is active:
            # mid-switch, or with a secure desktop (UAC, the lock screen) up.
            return "a window this process cannot see (the workstation may be locked)"
        return f"{_class_name_of(window)!r} (pid {_process_behind(window)})"

    def _cursor_moved_to(self, x: int, y: int) -> bool:
        return bool(_user32().SetCursorPos(int(x), int(y)))

    def _left_button_pressed_and_released(self) -> bool:
        events = (_InputEvent * _A_PRESS_AND_A_RELEASE)(
            _button_event(_LEFT_BUTTON_DOWN),
            _button_event(_LEFT_BUTTON_UP),
        )
        inserted = _user32().SendInput(
            _A_PRESS_AND_A_RELEASE,
            ctypes.byref(events),
            ctypes.sizeof(_InputEvent),
        )
        # SendInput reports how many events reached the queue; UIPI blocks the
        # whole batch, so anything short of both is a refusal.
        return inserted == _A_PRESS_AND_A_RELEASE


class _MouseEvent(ctypes.Structure):
    """Win32's MOUSEINPUT."""

    _fields_ = (
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouse_data", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        # ULONG_PTR: pointer-sized, and the reason INPUT is 40 bytes on 64-bit.
        ("extra_info", ctypes.c_size_t),
    )


class _InputEvent(ctypes.Structure):
    """Win32's INPUT, in its only shape this module ever sends.

    The real type holds a union of mouse, keyboard and hardware events, but
    MOUSEINPUT is the largest member, so a struct naming it directly has the
    same size and alignment as the union does.
    """

    _fields_ = (
        ("type", ctypes.c_ulong),
        ("mouse", _MouseEvent),
    )


def _button_event(flags: int) -> _InputEvent:
    # No MOUSEEVENTF_MOVE and no coordinates: the button acts wherever the
    # cursor already is, which SetCursorPos has just been told about.
    return _InputEvent(_MOUSE_EVENT, _MouseEvent(0, 0, 0, flags, 0, 0))


def _foreground_window() -> int | None:
    user32 = _user32()
    # Without this, ctypes truncates a 64-bit handle to a C int and every
    # question asked about the window afterwards is about a different one.
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    return user32.GetForegroundWindow() or None


def _class_name_of(window: int) -> str:
    name = ctypes.create_unicode_buffer(_LONGEST_WINDOW_CLASS_NAME)
    _user32().GetClassNameW(ctypes.c_void_p(window), name, _LONGEST_WINDOW_CLASS_NAME)
    return name.value


def _process_behind(window: int) -> int:
    pid = ctypes.c_ulong()
    _user32().GetWindowThreadProcessId(ctypes.c_void_p(window), ctypes.byref(pid))
    return pid.value


def _user32() -> ctypes.WinDLL:
    # Resolved per call rather than at import: `ctypes.windll` does not exist
    # off Windows, and this module still has to import there.
    return ctypes.windll.user32


WINDOWS_POINTER: PointerInput = CheckedPointer(Win32Mouse())
"""The pointer every adapter uses unless a spec hands it a double instead."""
