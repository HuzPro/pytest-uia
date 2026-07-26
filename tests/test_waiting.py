"""Behavioral spec for the waiting core.

GUI state arrives late: a window paints, a label changes, a control becomes
enabled. poll() is the single authority on retrying, so adapters can stay
one-shot. Clock and sleep are injected, which keeps this spec instant.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from pytest_uia.domain.errors import ElementNotFound
from pytest_uia.domain.waiting import RetryPolicy, poll

_RUNAWAY_ATTEMPTS = 50


class FlakyOperation:
    """Test double: an element that only shows up on the Nth look."""

    def __init__(self, succeeds_on_attempt: int) -> None:
        self._succeeds_on_attempt = succeeds_on_attempt
        self.attempts = 0

    def __call__(self) -> str:
        self.attempts += 1
        if self.attempts < self._succeeds_on_attempt:
            raise ElementNotFound("not painted yet")
        return "element"


class NeverFoundOperation:
    """Test double: an element that never appears, with a fresh reason each look.

    Refuses to be looked for forever: a poll that ignores its deadline should
    fail this spec quickly instead of hanging the whole suite.
    """

    def __init__(self) -> None:
        self.attempts = 0

    def __call__(self) -> str:
        self.attempts += 1
        if self.attempts > _RUNAWAY_ATTEMPTS:
            raise AssertionError("poll kept retrying long past its deadline")
        raise ElementNotFound(f"miss {self.attempts}")


class ScriptedClock:
    """Test double: hands out monotonic readings from a script.

    Lets a five-second timeout elapse in no real time at all.
    """

    def __init__(self, readings: Sequence[float]) -> None:
        self._readings = list(readings)
        self._reads = 0

    def __call__(self) -> float:
        # A real clock never runs out of readings, so hold the last one rather
        # than coupling the spec to how many times poll happens to look.
        index = min(self._reads, len(self._readings) - 1)
        self._reads += 1
        return self._readings[index]


class RecordingSleep:
    """Test double: remembers what it was asked to wait for instead of waiting."""

    def __init__(self) -> None:
        self.durations: list[float] = []

    def __call__(self, duration: float) -> None:
        self.durations.append(duration)


def test_poll_returns_the_result_when_the_operation_succeeds_on_the_first_attempt() -> (
    None
):
    # Given an operation that succeeds straight away
    def resolve() -> str:
        return "element"

    # When it is polled
    result = poll(resolve, RetryPolicy(), retry_on=ElementNotFound)

    # Then its result comes straight back
    assert result == "element"


def test_poll_retries_a_failing_operation_until_it_succeeds() -> None:
    # Given an element that only appears on the third look
    resolve = FlakyOperation(succeeds_on_attempt=3)
    clock = ScriptedClock([0.0, 0.25, 0.5])
    sleep = RecordingSleep()

    # When it is polled, with every attempt falling well inside the timeout
    result = poll(
        resolve,
        RetryPolicy(timeout=5.0, interval=0.25),
        retry_on=ElementNotFound,
        clock=clock,
        sleep=sleep,
    )

    # Then the early misses were absorbed and the eventual answer returned
    assert result == "element"
    assert resolve.attempts == 3, "poll should look again after every miss"


def test_poll_reraises_the_last_error_when_the_deadline_passes() -> None:
    # Given an element that never appears
    resolve = NeverFoundOperation()
    # and a clock that reaches the one-second deadline on its third reading
    clock = ScriptedClock([0.0, 0.5, 1.0])
    sleep = RecordingSleep()

    # When it is polled until the deadline passes
    with pytest.raises(ElementNotFound) as miss:
        poll(
            resolve,
            RetryPolicy(timeout=1.0, interval=0.25),
            retry_on=ElementNotFound,
            clock=clock,
            sleep=sleep,
        )

    # Then the freshest miss surfaces, since it describes the final state
    assert str(miss.value) == "miss 2", (
        "the last attempt's reason is the one worth reading"
    )


def test_poll_sleeps_the_configured_interval_between_attempts() -> None:
    # Given an element that appears on the third look
    resolve = FlakyOperation(succeeds_on_attempt=3)
    clock = ScriptedClock([0.0, 0.1, 0.2])
    sleep = RecordingSleep()

    # When it is polled with a tenth-of-a-second interval
    poll(
        resolve,
        RetryPolicy(timeout=5.0, interval=0.1),
        retry_on=ElementNotFound,
        clock=clock,
        sleep=sleep,
    )

    # Then it waited that interval after each miss, and not after the success
    assert sleep.durations == [0.1, 0.1]
