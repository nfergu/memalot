"""
Performance test that creates one million objects of 5 different types.

This test creates a large number of objects and runs the leak_monitor decorator
for two iterations without checking referrers.
"""

from typing import Any

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from memalot import leak_monitor


class TypeA:
    """
    First object type for performance testing.
    """

    def __init__(self, value: int) -> None:
        self.value = value


class TypeB:
    """
    Second object type for performance testing.
    """

    def __init__(self, value: int) -> None:
        self.value = value


class TypeC:
    """
    Third object type for performance testing.
    """

    def __init__(self, value: int) -> None:
        self.value = value


class TypeD:
    """
    Fourth object type for performance testing.
    """

    def __init__(self, value: int) -> None:
        self.value = value


class TypeE:
    """
    Fifth object type for performance testing.
    """

    def __init__(self, value: int) -> None:
        self.value = value


@leak_monitor(
    check_referrers=False,
    max_object_age_calls=1,
    max_object_details=2,
    # Set output to nowhere
    output_func=lambda _: None,
)
def create_objects(num_objects: int) -> list[Any]:
    """
    Creates a list of objects distributed across 5 different types.
    """
    objects: list[Any] = []
    for i in range(num_objects):
        type_index = i % 5
        if type_index == 0:
            objects.append(TypeA(i))
        elif type_index == 1:
            objects.append(TypeB(i))
        elif type_index == 2:
            objects.append(TypeC(i))
        elif type_index == 3:
            objects.append(TypeD(i))
        else:
            objects.append(TypeE(i))
    return objects


@leak_monitor(
    check_referrers=False,
    max_object_age_calls=1,
    max_object_details=2,
    # Set output to nowhere
    output_func=lambda _: None,
)
def create_tuples(num_objects: int) -> list[Any]:
    """
    Creates a list of tuples with of size num_objects. Each tuple consists of 20 numbers.
    """
    objects: list[Any] = []
    for i in range(num_objects):
        objects.append(tuple(range(i - 20, i)))
    return objects


@pytest.mark.performance
class TestMassObjectCreationPerformance:
    """
    Performance tests for creating large numbers of objects.
    """

    def test_create_one_million_objects(self, benchmark: BenchmarkFixture) -> None:
        """
        Test the performance of creating one million objects of 5 different types
        across two iterations without checking referrers.
        """

        def run_object_creation() -> None:
            # Create 500,000 objects per iteration for a total of 1 million across 2 iterations
            create_objects(500_000)
            create_objects(500_000)

        benchmark.pedantic(run_object_creation, rounds=1)  # type: ignore

        # Based on preliminary testing, the test should complete in well under 40 seconds
        # on average, even on Github's workers (this is about 4x what it takes on a fast laptop).
        # This assertion allows for some variability but catches very significant performance
        # regressions.
        assert benchmark.stats is not None
        assert benchmark.stats.stats.mean < 40.0, (
            f"Performance regression detected: mean time {benchmark.stats.stats.mean:.2f}s "
            f"exceeds 40.0s"
        )

    def test_create_one_million_tuples(self, benchmark: BenchmarkFixture) -> None:
        """
        Test the performance of creating one million tuples.

        This is an interesting test because tuples are not (at the time of writing) weakly
        referenceable, which means that they are treated differently.
        """

        def run_object_creation() -> None:
            # Create 500,000 tuples per iteration for a total of 1 million across 2 iterations
            create_tuples(500_000)
            create_tuples(500_000)

        benchmark.pedantic(run_object_creation, rounds=1)  # type: ignore

        # Based on preliminary testing, the test should complete in well under 80 seconds
        # on average, even on Github's workers (this is about 4x what it takes on a fast laptop).
        # This assertion allows for some variability but catches very significant performance
        # regressions.
        assert benchmark.stats is not None
        assert benchmark.stats.stats.mean < 80.0, (
            f"Performance regression detected: mean time {benchmark.stats.stats.mean:.2f}s "
            f"exceeds 80.0s"
        )
