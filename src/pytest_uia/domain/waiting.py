"""The single authority on retrying, so every adapter can stay one-shot.

Locators look once and give up; only this module waits. Clock and sleep are
injected rather than imported at the call site, which is what lets the unit
tests exercise multi-second timeouts instantly.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    """How long to keep asking, and how often."""

    timeout: float = 5.0
    interval: float = 0.25


def poll(
    operation: Callable[[], T],
    policy: RetryPolicy,
    *,
    retry_on: type[Exception] | tuple[type[Exception], ...],
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Retry operation while it raises retry_on, until the policy's deadline.

    The operation is always attempted at least once, so a zero timeout still
    reflects the current state of the screen rather than failing blind.
    """
    deadline = clock() + policy.timeout
    while True:
        try:
            return operation()
        except retry_on:
            # Re-raise the freshest miss, not the first: it describes the state
            # the screen was actually left in when the wait ran out.
            if clock() >= deadline:
                raise
            sleep(policy.interval)
