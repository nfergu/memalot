"""
General integration (functional) tests for the application.
"""

from __future__ import annotations

from typing import Any

import pytest

from leaky import leak_monitor


class LeakedObject:
    pass


output_chunks = []


class LeakyObject:
    def __init__(self) -> None:
        self._data: list[Any] = []

    @leak_monitor(
        output_func=lambda x: output_chunks.append(x),
        tee_console=True,
    )
    def add_data(self) -> None:
        item = LeakedObject()
        self._data.append(item)


@pytest.mark.integration
class TestOutput:
    """
    Integration tests that check that the correct output is produced when the application
    is run.

    Note: we don't do extensive testing of the exact output, as it's awkward to test.
    """

    def test_output_for_simple_example(self) -> None:
        """
        Tests that a simple example that leaks some memory periodically outputs the correct
        information. We can't test the exact output, but we can check the rough format.
        """
        # ruff: noqa: W291
        leaky_object = LeakyObject()

        for _ in range(2):
            leaky_object.add_data()

        expected_chunks = [
            "Leaky is performing leak monitoring for the add_data function",
            "Leaky Report (iteration 1) ",
            "This is a warmup iteration. Reports will be available from the next iteration.",
            "End of Leaky Report (iteration 1)",
            "Leaky Report (iteration 2)",
            """
             Possible New Leaks (iteration 2)              
╭─────────────────────────────────────────────────┬───────╮
│ Object Type                                     │ Count │
├─────────────────────────────────────────────────┼───────┤
│ tests_integration.test_integration.LeakedObject │     1 │
╰─────────────────────────────────────────────────┴───────╯
""",
            "Leaky is generating object details. This may take some time...",
            "Details for tests_integration.test_integration.LeakedObject",
            "End of Leaky Report (iteration 2)",
        ]

        for output_chunk, expected_chunk in zip(output_chunks, expected_chunks, strict=True):
            assert expected_chunk in output_chunk
