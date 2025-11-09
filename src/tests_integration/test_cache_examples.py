"""
Integration tests for the cache examples.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from memalot import create_leak_monitor, leak_monitor
from tests_integration.utils import (
    assert_iteration_count,
    assert_object_details_types,
    assert_object_type_details,
    assert_referrer_graphs_have_root_names,
    assert_type_summaries,
    assert_warmup_iteration,
    filter_object_details_by_type,
    read_single_report,
)


class Cache:
    """
    A cache that stores objects in a list.
    """

    def __init__(self) -> None:
        self.cache_list: list["LeakyObject"] = []


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


class PreviousObject:
    """
    An object that only lives from one iteration to the next.
    """

    def __init__(self, size: int) -> None:
        self.payload = np.ones(size)


def create_leaky_object() -> LeakyObject:
    """
    Creates a leaky object after creating a non-leaky object.
    """
    _ = NotLeakyObject(128)
    return LeakyObject(128)


@pytest.mark.integration
class TestCacheExampleFunctionBased:
    """
    Tests for the cache example using function-based monitoring.
    """

    def test_cache_example_function_based(self, tmp_path: Path) -> None:
        """
        Tests that the cache example with function-based monitoring generates the expected report.

        This test verifies that:
        - LeakyObjects added to a cache are properly detected as leaks
        - Each iteration reports exactly 1 new LeakyObject
        - Type summaries contain only LeakyObject and numpy.ndarray types
        - Referrer graphs correctly identify the cache as the root
        """

        # given: a create_and_cache function with leak monitoring
        @leak_monitor(
            report_directory=tmp_path,
        )
        def create_and_cache(cache: Cache) -> None:
            cache.cache_list.append(create_leaky_object())

        cache = Cache()

        # when: we call create_and_cache 3 times to generate reports
        for _ in range(3):
            create_and_cache(cache=cache)

        # then: read the report from disk and verify
        full_report = read_single_report(tmp_path=tmp_path)
        assert_iteration_count(full_report=full_report, expected_count=3)

        # Iteration 1: warmup - no leaks reported
        iteration_1 = full_report.iterations[0]
        assert iteration_1.iteration_number == 1
        assert_warmup_iteration(iteration=iteration_1)

        # Iteration 2: exactly 1 new LeakyObject and 1 ndarray
        iteration_2 = full_report.iterations[1]
        assert iteration_2.iteration_number == 2

        # Check type summaries
        type_summaries = iteration_2.leak_summary.type_summaries
        expected_types = {
            "tests_integration.test_cache_examples.LeakyObject",
            "numpy.ndarray",
        }
        expected_counts = {1}
        assert_type_summaries(
            type_summaries=type_summaries,
            expected_types=expected_types,
            expected_counts=expected_counts,
        )

        # Check object details
        object_details_list = list(iteration_2.object_details_list)
        assert_object_details_types(
            object_details_list=object_details_list, expected_types=expected_types
        )

        # Verify LeakyObject
        assert_object_type_details(
            object_details_list=object_details_list,
            object_type="tests_integration.test_cache_examples.LeakyObject",
            expected_count=1,
            expected_target_names={"LeakyObject (object)"},
        )

        # Verify ndarray
        assert_object_type_details(
            object_details_list=object_details_list,
            object_type="numpy.ndarray",
            expected_count=1,
            expected_target_names={"ndarray (object)"},
        )

        # Verify root names for all objects - they should trace back to the cache
        # Note: Since cache is passed as a keyword argument, it appears in kwargs
        expected_root_names = {
            "test_cache_example_function_based.cache (local)",
            "create_and_cache kwargs (local)",
        }
        assert_referrer_graphs_have_root_names(
            object_details_list=object_details_list,
            expected_root_names=expected_root_names,
        )

        # Iteration 3: exactly 1 new LeakyObject and 1 ndarray (same as iteration 2)
        iteration_3 = full_report.iterations[2]
        assert iteration_3.iteration_number == 3

        type_summaries_3 = iteration_3.leak_summary.type_summaries
        assert_type_summaries(
            type_summaries=type_summaries_3,
            expected_types=expected_types,
            expected_counts=expected_counts,
        )


@pytest.mark.integration
class TestCacheExampleContextManager:
    """
    Tests for the cache example using context manager-based monitoring.
    """

    def test_cache_example_context_manager(self, tmp_path: Path) -> None:
        """
        Tests that the cache example with context manager generates the expected report.

        This test verifies that:
        - LeakyObjects added to a cache are properly detected as leaks
        - Each iteration reports exactly 1 new LeakyObject
        - Type summaries contain only LeakyObject and numpy.ndarray types
        - Referrer graphs correctly identify the cache as the root
        """

        # given: a create_and_cache function and a leak monitor context manager
        def create_and_cache(cache: Cache) -> None:
            cache.cache_list.append(create_leaky_object())

        cache = Cache()
        monitor = create_leak_monitor(
            report_directory=tmp_path,
            output_func=lambda _: None,
        )

        # when: we call create_and_cache 3 times with the monitor context
        for _ in range(3):
            with monitor:
                create_and_cache(cache)

        # then: read the report from disk and verify
        full_report = read_single_report(tmp_path=tmp_path)
        assert_iteration_count(full_report=full_report, expected_count=3)

        # Iteration 1: warmup - no leaks reported
        iteration_1 = full_report.iterations[0]
        assert iteration_1.iteration_number == 1
        assert_warmup_iteration(iteration=iteration_1)

        # Iteration 2: exactly 1 new LeakyObject and 1 ndarray
        iteration_2 = full_report.iterations[1]
        assert iteration_2.iteration_number == 2

        # Check type summaries
        type_summaries = iteration_2.leak_summary.type_summaries
        expected_types = {
            "tests_integration.test_cache_examples.LeakyObject",
            "numpy.ndarray",
        }
        expected_counts = {1}
        assert_type_summaries(
            type_summaries=type_summaries,
            expected_types=expected_types,
            expected_counts=expected_counts,
        )

        # Check object details
        object_details_list = list(iteration_2.object_details_list)
        assert_object_details_types(
            object_details_list=object_details_list, expected_types=expected_types
        )

        # Verify LeakyObject
        assert_object_type_details(
            object_details_list=object_details_list,
            object_type="tests_integration.test_cache_examples.LeakyObject",
            expected_count=1,
            expected_target_names={"LeakyObject (object)"},
        )

        # Verify ndarray
        assert_object_type_details(
            object_details_list=object_details_list,
            object_type="numpy.ndarray",
            expected_count=1,
            expected_target_names={"ndarray (object)"},
        )

        # Verify root names for all objects - they should trace back to the cache
        expected_root_names = {
            "test_cache_example_context_manager.cache (local)",
        }
        assert_referrer_graphs_have_root_names(
            object_details_list=object_details_list,
            expected_root_names=expected_root_names,
        )

        # Iteration 3: exactly 1 new LeakyObject and 1 ndarray (same as iteration 2)
        iteration_3 = full_report.iterations[2]
        assert iteration_3.iteration_number == 3

        type_summaries_3 = iteration_3.leak_summary.type_summaries
        assert_type_summaries(
            type_summaries=type_summaries_3,
            expected_types=expected_types,
            expected_counts=expected_counts,
        )


@pytest.mark.integration
class TestCacheExampleMultipleCalls:
    """
    Tests for the cache example with max_object_age_calls parameter.
    """

    def test_cache_example_multiple_calls(self, tmp_path: Path) -> None:
        """
        Tests that the cache example with max_object_age_calls=2 generates expected report.

        This test verifies that:
        - Only objects that survive for 2 calls are reported as leaks
        - PreviousObject instances are NOT reported since they only survive 1 call
        - LeakyObjects that survive multiple calls ARE reported
        - Type summaries contain only LeakyObject and numpy.ndarray types
        """

        # given: a create_and_cache function with max_object_age_calls=2
        @leak_monitor(
            max_object_age_calls=2,
            report_directory=tmp_path,
            output_func=lambda _: None,
        )
        def create_and_cache(cache: Cache, previous_list: list[Any]) -> None:
            cache.cache_list.append(create_leaky_object())
            previous_list[0] = PreviousObject(2)

        cache = Cache()
        previous_list: list[Any] = [None]

        # when: we call create_and_cache 5 times to generate reports
        for _ in range(5):
            create_and_cache(cache=cache, previous_list=previous_list)

        # then: read the report from disk and verify
        full_report = read_single_report(tmp_path=tmp_path)
        # With max_object_age_calls=2, we need objects to survive 2 calls
        # So after 5 calls, we get: 1 warmup + 2 reporting iterations
        assert_iteration_count(full_report=full_report, expected_count=3)

        # Iteration 1: warmup - no leaks reported
        iteration_1 = full_report.iterations[0]
        assert iteration_1.iteration_number == 1
        assert_warmup_iteration(iteration=iteration_1)

        # Iteration 2: exactly 1 new LeakyObject and 1 ndarray
        # PreviousObject should NOT be reported as it only survives 1 call
        iteration_2 = full_report.iterations[1]
        assert iteration_2.iteration_number == 2

        # Check type summaries - should NOT include PreviousObject
        type_summaries = iteration_2.leak_summary.type_summaries
        expected_types = {
            "tests_integration.test_cache_examples.LeakyObject",
            "numpy.ndarray",
        }
        expected_counts = {1}
        assert_type_summaries(
            type_summaries=type_summaries,
            expected_types=expected_types,
            expected_counts=expected_counts,
        )

        # Check object details
        object_details_list = list(iteration_2.object_details_list)
        assert_object_details_types(
            object_details_list=object_details_list, expected_types=expected_types
        )

        # Verify PreviousObject is not in the report
        previous_object_details_list = filter_object_details_by_type(
            object_details_list=object_details_list,
            object_type="tests_integration.test_cache_examples.PreviousObject",
        )
        assert len(previous_object_details_list) == 0

        # Verify LeakyObject
        assert_object_type_details(
            object_details_list=object_details_list,
            object_type="tests_integration.test_cache_examples.LeakyObject",
            expected_count=1,
            expected_target_names={"LeakyObject (object)"},
        )

        # Verify ndarray
        assert_object_type_details(
            object_details_list=object_details_list,
            object_type="numpy.ndarray",
            expected_count=1,
            expected_target_names={"ndarray (object)"},
        )

        # Verify root names for all objects
        # Note: previous_list won't appear because PreviousObject is not reported
        expected_root_names = {
            "test_cache_example_multiple_calls.cache (local)",
            "create_and_cache kwargs (local)",
        }
        assert_referrer_graphs_have_root_names(
            object_details_list=object_details_list,
            expected_root_names=expected_root_names,
        )

        # Iteration 3: exactly 1 new LeakyObject and 1 ndarray (same as iteration 2)
        iteration_3 = full_report.iterations[2]
        assert iteration_3.iteration_number == 3

        type_summaries_3 = iteration_3.leak_summary.type_summaries
        assert_type_summaries(
            type_summaries=type_summaries_3,
            expected_types=expected_types,
            expected_counts=expected_counts,
        )
