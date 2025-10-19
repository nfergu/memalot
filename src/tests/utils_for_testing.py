import time
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar, cast
from unittest.mock import MagicMock, create_autospec

from memalot import leak_monitor
from memalot.base import ObjectGetter

_REPORT_DIR = Path(__file__).parent / "test_data" / "reports" / "v1"


class Cache:
    def __init__(self) -> None:
        self.cache_list: list[Any] = []


class MemalotObject:
    def __init__(self, size: int) -> None:
        self.payload = [1] * size


def create_memalot_object() -> MemalotObject:
    return MemalotObject(128)


# Set save_reports=True if regenerating the test data
@leak_monitor(
    report_directory=_REPORT_DIR,
    force_terminal=True,
    check_referrers=True,
    save_reports=False,
)
def create_and_cache(cache: Cache) -> None:
    cache.cache_list.append(create_memalot_object())


def create_leaks() -> None:
    cache = Cache()
    for _ in range(3):
        create_and_cache(cache)


def create_mock(spec: Any, spec_set: bool = True, instance: bool = True) -> MagicMock:
    return cast(MagicMock, create_autospec(spec=spec, spec_set=spec_set, instance=instance))


def wait_for_assertion(
    assertion_func: Callable[[], None],
    wait_time_secs: float = 60.0,
    poll_interval_secs: float = 0.1,
) -> None:
    """
    Waits for `assertion_func` to complete without raising an `AssertionError`.

    Retries the assertion until it passes or the timeout elapses. If the timeout
    elapses, the last `AssertionError` is re-raised.
    """
    if wait_time_secs < 0:
        raise ValueError("wait_time_secs must be non-negative")
    if poll_interval_secs <= 0:
        raise ValueError("poll_interval_secs must be positive")

    deadline = time.monotonic() + wait_time_secs

    while True:
        try:
            assertion_func()
            break
        except AssertionError as error:
            if time.monotonic() >= deadline:
                raise error
            remaining = max(0.0, deadline - time.monotonic())
            time.sleep(min(poll_interval_secs, remaining))


T = TypeVar("T")


def one(iterable: Iterable[T]) -> T:
    (result,) = iterable
    return result


class FixedObjectGetter(ObjectGetter):
    """
    Gets a fixed list of objects.
    """

    def __init__(self, objects: list[Any]) -> None:
        self._objects = objects

    def get_objects(self) -> list[Any]:
        return self._objects
