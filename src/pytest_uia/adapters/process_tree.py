"""Adapter over Win32's process snapshot: who a launched application really is.

Where it plugs in: :func:`pytest_uia.adapters.uia.resolve_main_window` asks for
the family of the pid a launch reported, and accepts a window owned by any
member of it.

The motivating failure: `subprocess` reports the pid of what it started, which
is not always what runs. On Windows the `python.exe` inside a virtual
environment is a copy of CPython's launcher — it starts the real interpreter as
a child and waits — so `gui.launch([sys.executable, "app.py"])` hands back a pid
that owns no window, forever. Every console-script shim and `.bat` wrapper has
the same shape. Matching a window against the whole family is what makes the
obvious call work.

`ctypes.windll` is reached lazily so the pure walk above can be specified — and
run in CI — on a machine with no Windows on it.
"""

from __future__ import annotations

import ctypes
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

_ALL_PROCESSES = 0x00000002  # TH32CS_SNAPPROCESS
_NOT_A_SNAPSHOT = -1  # INVALID_HANDLE_VALUE
_LONGEST_IMAGE_NAME = 260  # MAX_PATH


def process_family(pid: int) -> frozenset[int]:
    """The launched process and everything it has started, as of right now."""
    return family_of(pid, running_processes())


def family_of(pid: int, parents: Mapping[int, int]) -> frozenset[int]:
    """The process itself, plus everything descending from it.

    Walks downwards from the root rather than upwards from every process: a
    snapshot of a live machine is not a guaranteed tree — the idle process
    parents itself, and a pid reused after its parent died can close a loop —
    and only the visited set makes either of those terminate.
    """
    children = _children_by_parent(parents)
    family: set[int] = set()
    unexplored = [pid]
    while unexplored:
        process = unexplored.pop()
        if process in family:
            continue
        family.add(process)
        unexplored.extend(children.get(process, ()))
    return frozenset(family)


def _children_by_parent(parents: Mapping[int, int]) -> dict[int, list[int]]:
    children: dict[int, list[int]] = {}
    for child, parent in parents.items():
        children.setdefault(parent, []).append(child)
    return children


def running_processes() -> dict[int, int]:
    """Every process on the machine now, each mapped to the one that started it.

    Humble object: the ctypes plumbing that cannot exist without Windows, with
    no decision in it worth a unit test of its own.
    """
    parents: dict[int, int] = {}
    with _snapshot_of_every_process() as snapshot:
        kernel32 = _kernel32()
        entry = _ProcessEntry()
        entry.size = ctypes.sizeof(_ProcessEntry)
        found = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            parents[entry.pid] = entry.parent_pid
            found = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    return parents


class _ProcessEntry(ctypes.Structure):
    """Win32's PROCESSENTRY32W, named for the two fields this module reads."""

    _fields_ = (
        ("size", ctypes.c_ulong),
        ("usage_count", ctypes.c_ulong),
        ("pid", ctypes.c_ulong),
        ("default_heap_id", ctypes.c_size_t),
        ("module_id", ctypes.c_ulong),
        ("thread_count", ctypes.c_ulong),
        ("parent_pid", ctypes.c_ulong),
        ("base_priority", ctypes.c_long),
        ("flags", ctypes.c_ulong),
        ("image_name", ctypes.c_wchar * _LONGEST_IMAGE_NAME),
    )


@contextmanager
def _snapshot_of_every_process() -> Iterator[ctypes.c_void_p]:
    kernel32 = _kernel32()
    # Without an explicit restype ctypes truncates the handle to a C int, and
    # every call made with what is left addresses nothing.
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    snapshot = kernel32.CreateToolhelp32Snapshot(_ALL_PROCESSES, 0)
    if snapshot in (None, ctypes.c_void_p(_NOT_A_SNAPSHOT).value):
        raise OSError("Windows would not take a snapshot of the process table")
    handle = ctypes.c_void_p(snapshot)
    try:
        yield handle
    finally:
        # A real kernel handle: leaking one per lookup leaks one per poll of
        # every launch a suite makes.
        kernel32.CloseHandle(handle)


def _kernel32() -> ctypes.WinDLL:
    return ctypes.windll.kernel32
