"""
Integration test for the cache example using time-based leak monitoring.
"""

from __future__ import annotations

import time
from pathlib import Path
from threading import Thread
from typing import Any

import numpy as np
import pytest

import memalot
from memalot.reports import FileReportReader
from tests_integration.utils import (
    assert_object_type_details,
    assert_referrer_graphs_have_root_names,
    assert_warmup_iteration,
    has_leak_iterations,
    read_single_report,
)


class Cache:
    """
    A cache that stores objects in a list.
    """

    def __init__(self) -> None:
        self.cache_list: list[Any] = []


class LeakyObject:
    """
    An object with a numpy array payload.
    """

    def __init__(self, size: int) -> None:
        self.payload = np.ones(size)


class NotLeakyObject:
    """
    An object that is not leaked.
    """

    def __init__(self, size: int) -> None:
        self.payload = np.ones(size)


def create_leaky_object() -> LeakyObject:
    """
    Creates a leaky object after creating a non-leaky object.
    """
    _ = NotLeakyObject(128)
    return LeakyObject(32)


def create_and_cache(cache: Cache) -> None:
    """
    Creates a leaky object and adds it to the cache.
    """
    cache.cache_list.append(create_leaky_object())


def create_non_leaky_object_and_cache(cache: Cache) -> None:
    """
    Creates a non-leaky object and adds it to the cache.
    """
    cache.cache_list.append(NotLeakyObject(32))


class LeakingThread(Thread):
    def __init__(self, iteration_time: float) -> None:
        super().__init__()
        self._stopped = False
        self._iteration_time = iteration_time

    def run(self) -> None:
        live_forever_cache = Cache()
        live_for_one_iteration_cache = Cache()
        while not self._stopped:
            create_and_cache(live_forever_cache)
            create_non_leaky_object_and_cache(live_for_one_iteration_cache)
            time.sleep(self._iteration_time)
            live_for_one_iteration_cache.cache_list.clear()

    def stop(self) -> None:
        self._stopped = True


@pytest.mark.integration
class TestCacheExampleTimeBased:
    """
    Tests for the cache example using time-based monitoring.
    """

    def test_cache_example_time_based(self, tmp_path: Path) -> None:
        """
        Tests that the cache example with time-based monitoring generates expected reports.

        This test verifies that:
        - start_leak_monitoring creates a background thread
        - Objects created after warmup are properly detected as leaks
        - Reports contain correct type summaries and object details
        - The monitoring thread can be stopped cleanly
        """
        expected_leak_iterations = 2

        reader = FileReportReader(report_directory=tmp_path)

        # Some objects live for only one iteration, so we need to set a higher max_object_lifetime
        # that the iteration time.
        iteration_time = 0.1
        max_object_lifetime = 1.0
        assert max_object_lifetime > iteration_time

        # when: continuously add leaky objects until we have at least one iteration with leaks
        stoppable = memalot.start_leak_monitoring(
            max_object_lifetime=max_object_lifetime,
            warmup_time=5.0,
            report_directory=tmp_path,
            max_object_details=4,
            str_max_length=200,
        )

        leaking_thread = LeakingThread(iteration_time=iteration_time)
        leaking_thread.start()

        # then: check for iterations with leaks
        try:
            deadline = time.monotonic() + 240.0
            while True:
                if has_leak_iterations(
                    reader=reader, expected_leak_iterations=expected_leak_iterations
                ):
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("Timeout waiting for iterations with leaks.")
                time.sleep(iteration_time)
        finally:
            # then: stop the monitoring thread and leaking thread
            stoppable.stop()
            stoppable.join(timeout=60.0)
            leaking_thread.stop()
            leaking_thread.join(timeout=60.0)

        # Read and verify the report
        full_report = read_single_report(tmp_path=tmp_path)

        assert full_report.summary.iteration_count >= expected_leak_iterations, (
            f"Expected at least {expected_leak_iterations} iterations, "
            f"got {full_report.summary.iteration_count}"
        )

        # Verify the first iteration is warmup
        iteration_1 = full_report.iterations[0]
        assert iteration_1.iteration_number == 1
        assert_warmup_iteration(iteration=iteration_1)

        leak_iterations = [
            iteration
            for iteration in full_report.iterations
            if len(iteration.leak_summary.type_summaries) > 0
        ]
        assert len(leak_iterations) >= expected_leak_iterations

        for leak_iteration in leak_iterations[:expected_leak_iterations]:
            # Check type summaries - we expect LeakyObject and ndarray only
            type_summaries = leak_iteration.leak_summary.type_summaries
            actual_types = {summary.object_type for summary in type_summaries}

            # Verify that at minimum we have LeakyObject and ndarray
            required_types = {
                "tests_integration.test_time_based.LeakyObject",
                "numpy.ndarray",
            }
            assert actual_types == required_types

            object_details_list = list(leak_iteration.object_details_list)

            # Verify LeakyObject
            assert_object_type_details(
                object_details_list=object_details_list,
                object_type="tests_integration.test_time_based.LeakyObject",
                expected_count=2,
                expected_target_names={"LeakyObject (object)"},
            )

            # Verify ndarray
            assert_object_type_details(
                object_details_list=object_details_list,
                object_type="numpy.ndarray",
                expected_count=2,
                expected_target_names={"ndarray (object)"},
            )

            # Verify root names for LeakyObject and ndarray
            # Both should trace back to the cache
            expected_root_names = {
                "run.live_forever_cache (local)",
            }
            assert_referrer_graphs_have_root_names(
                object_details_list=object_details_list,
                expected_root_names=expected_root_names,
            )
