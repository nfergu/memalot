from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from memalot.mcp_server.main import mcp


@pytest.fixture(name="test_reports_dir")
def _test_reports_dir() -> Path:
    """
    Fixture providing the path to test reports directory.
    """
    return Path(__file__).parent.parent / "test_data" / "reports" / "v1"


@pytest.fixture(name="mcp_client")
def _mcp_client() -> "Client[Any]":
    """
    Fixture providing a FastMCP client connected to the server.
    """
    return Client[Any](mcp)


class TestListLeakReports:
    """
    Tests for the `list_leak_reports` MCP tool.
    """

    @pytest.mark.asyncio
    async def test_list_reports_default_parameters(
        self, mcp_client: Client[Any], test_reports_dir: Path
    ) -> None:
        """
        Test listing reports with default parameters (5 reports, default directory).
        """
        async with mcp_client:
            result = await mcp_client.call_tool(
                "list_leak_reports", {"report_directory": str(test_reports_dir)}
            )

        assert hasattr(result, "data"), f"Result {type(result)} has no data attribute"
        assert not result.is_error, "Tool call should not result in an error"
        report_summaries = result.data

        assert len(report_summaries.summaries) == 3
        assert report_summaries.summaries[0].metadata.report_id == "d6wf-uw2w"
        assert report_summaries.summaries[0].metadata.entrypoint == "utils_for_testing.py"
        assert report_summaries.summaries[0].metadata.arguments == []
        assert report_summaries.summaries[0].metadata.start_time == datetime(
            2025, 9, 29, 20, 54, 18, 936290, tzinfo=timezone.utc
        )
        assert report_summaries.summaries[0].iteration_count == 3

        assert report_summaries.summaries[1].metadata.report_id == "lyy0-uf3p"
        assert report_summaries.summaries[1].metadata.entrypoint == "utils_for_testing.py"
        assert report_summaries.summaries[1].metadata.arguments == []
        assert report_summaries.summaries[1].metadata.start_time == datetime(
            2025, 9, 29, 20, 54, 6, 560032, tzinfo=timezone.utc
        )
        assert report_summaries.summaries[1].iteration_count == 3

        assert report_summaries.summaries[2].metadata.report_id == "ykik-ab4l"
        assert report_summaries.summaries[2].metadata.entrypoint == "utils_for_testing.py"
        assert report_summaries.summaries[2].metadata.arguments == ["dummy_arg1", "dummy_arg2"]
        assert report_summaries.summaries[2].metadata.start_time == datetime(
            2025, 9, 29, 20, 53, 39, 600135, tzinfo=timezone.utc
        )
        assert report_summaries.summaries[2].iteration_count == 3

    @pytest.mark.asyncio
    async def test_list_reports_with_num_reports(
        self, mcp_client: Client[Any], test_reports_dir: Path
    ) -> None:
        """
        Test listing reports with specific number of reports requested.
        """
        async with mcp_client:
            result = await mcp_client.call_tool(
                "list_leak_reports", {"num_reports": 2, "report_directory": str(test_reports_dir)}
            )

        assert hasattr(result, "data"), f"Result {type(result)} has no data attribute"
        assert not result.is_error, "Tool call should not result in an error"
        report_summaries = result.data

        assert len(report_summaries.summaries) == 2
        assert report_summaries.summaries[0].metadata.report_id == "d6wf-uw2w"
        assert report_summaries.summaries[0].metadata.entrypoint == "utils_for_testing.py"
        assert report_summaries.summaries[0].metadata.arguments == []
        assert report_summaries.summaries[0].metadata.start_time == datetime(
            2025, 9, 29, 20, 54, 18, 936290, tzinfo=timezone.utc
        )
        assert report_summaries.summaries[0].iteration_count == 3

        assert report_summaries.summaries[1].metadata.report_id == "lyy0-uf3p"
        assert report_summaries.summaries[1].metadata.entrypoint == "utils_for_testing.py"
        assert report_summaries.summaries[1].metadata.arguments == []
        assert report_summaries.summaries[1].metadata.start_time == datetime(
            2025, 9, 29, 20, 54, 6, 560032, tzinfo=timezone.utc
        )
        assert report_summaries.summaries[1].iteration_count == 3

    @pytest.mark.asyncio
    async def test_list_reports_high_num_reports(
        self, mcp_client: Client[Any], test_reports_dir: Path
    ) -> None:
        """
        Test listing reports when requesting more reports than available.
        """
        async with mcp_client:
            result = await mcp_client.call_tool(
                "list_leak_reports", {"num_reports": 100, "report_directory": str(test_reports_dir)}
            )

        assert hasattr(result, "data"), f"Result {type(result)} has no data attribute"
        assert not result.is_error, "Tool call should not result in an error"
        report_summaries = result.data
        report_ids = [report.metadata.report_id for report in report_summaries.summaries]
        assert "d6wf-uw2w" in report_ids
        assert "lyy0-uf3p" in report_ids
        assert "ykik-ab4l" in report_ids

    @pytest.mark.asyncio
    async def test_list_reports_nonexistent_directory(
        self, mcp_client: Client[Any], tmp_path: Path
    ) -> None:
        """
        Test listing reports from a nonexistent directory.
        """
        nonexistent_dir = tmp_path / "does_not_exist"

        async with mcp_client:
            result = await mcp_client.call_tool(
                "list_leak_reports", {"report_directory": str(nonexistent_dir)}
            )

        assert hasattr(result, "data"), f"Result {type(result)} has no data attribute"
        assert not result.is_error, "Tool call should not result in an error"
        assert len(result.data.summaries) == 0


class TestGetLeakReport:
    """
    Tests for the `get_leak_report` MCP tool.
    """

    @pytest.mark.asyncio
    async def test_get_report_basic(self, mcp_client: Client[Any], test_reports_dir: Path) -> None:
        """
        Test getting a basic report with default parameters.
        """
        async with mcp_client:
            result = await mcp_client.call_tool(
                "get_leak_report",
                {"report_id": "lyy0-uf3p", "report_directory": str(test_reports_dir)},
            )

        assert hasattr(result, "data"), f"Result {type(result)} has no data attribute"
        assert not result.is_error, "Tool call should not result in an error"
        report_data = result.data

        # Verify summary metadata
        assert report_data.summary.metadata.report_id == "lyy0-uf3p"
        assert report_data.summary.metadata.entrypoint == "utils_for_testing.py"
        assert report_data.summary.metadata.arguments == []
        assert report_data.summary.metadata.start_time == datetime(
            2025, 9, 29, 20, 54, 6, 560032, tzinfo=timezone.utc
        )
        assert report_data.summary.iteration_count == 3

        # Verify iterations (default num_iterations=1, so should get most recent iteration)
        assert len(report_data.iterations) == 1
        iteration = report_data.iterations[0]
        assert iteration.report_id == "lyy0-uf3p"
        assert iteration.iteration_number == 3

        # Verify memory usage
        assert iteration.memory_usage.current_rss_bytes == 356024320
        assert iteration.memory_usage.peak_rss_bytes == 376750080
        assert iteration.memory_usage.current_rss_diff == 73564160
        assert iteration.memory_usage.peak_rss_diff == 72286208
        assert iteration.memory_usage.diff_from_iteration == 2

        # Verify leak summary
        assert iteration.leak_summary.iteration == 3
        assert len(iteration.leak_summary.type_summaries) == 2
        assert iteration.leak_summary.type_summaries[0].object_type == "__main__.MemalotObject"
        assert iteration.leak_summary.type_summaries[0].count == 1
        assert iteration.leak_summary.type_summaries[1].object_type == "builtins.list"
        assert iteration.leak_summary.type_summaries[1].count == 1
        assert iteration.leak_summary.max_types_in_summary == 500

        # Verify object details
        assert len(iteration.object_details_list) == 2
        assert iteration.object_details_list[0].object_type_name == "__main__.MemalotObject"
        assert iteration.object_details_list[0].deep_size_bytes.approx_size == 1436
        assert iteration.object_details_list[0].deep_size_bytes.upper_bound_known is True
        assert iteration.object_details_list[0].referrers_checked is True
        assert iteration.object_details_list[1].object_type_name == "builtins.list"
        assert iteration.object_details_list[1].deep_size_bytes.approx_size == 1108
        assert iteration.object_details_list[1].deep_size_bytes.upper_bound_known is True
        assert iteration.object_details_list[1].referrers_checked is True

    @pytest.mark.asyncio
    async def test_get_report_multiple_iterations(
        self, mcp_client: Client[Any], test_reports_dir: Path
    ) -> None:
        """
        Test getting a report with multiple iterations.
        """
        async with mcp_client:
            result = await mcp_client.call_tool(
                "get_leak_report",
                {
                    "report_id": "lyy0-uf3p",
                    "num_iterations": 2,
                    "report_directory": str(test_reports_dir),
                },
            )

        assert hasattr(result, "data"), f"Result {type(result)} has no data attribute"
        assert not result.is_error, "Tool call should not result in an error"
        report_data = result.data

        # Verify summary (same as in test_get_report_basic)
        assert report_data.summary.metadata.report_id == "lyy0-uf3p"
        assert report_data.summary.iteration_count == 3

        # Verify we get 2 iterations (the most recent 2)
        assert len(report_data.iterations) == 2
        iteration_numbers = [iteration.iteration_number for iteration in report_data.iterations]
        assert iteration_numbers == [2, 3]  # Sorted by iteration number

        # Verify iteration 2
        iter_2 = report_data.iterations[0]
        assert iter_2.report_id == "lyy0-uf3p"
        assert iter_2.iteration_number == 2
        assert iter_2.memory_usage.current_rss_bytes == 282460160
        assert iter_2.memory_usage.peak_rss_bytes == 304463872
        assert iter_2.memory_usage.current_rss_diff == 215252992
        assert iter_2.memory_usage.peak_rss_diff == 235831296
        assert iter_2.memory_usage.diff_from_iteration == 1
        assert iter_2.leak_summary.iteration == 2
        assert len(iter_2.leak_summary.type_summaries) == 2
        assert iter_2.leak_summary.type_summaries[0].object_type == "__main__.MemalotObject"
        assert iter_2.leak_summary.type_summaries[0].count == 1
        assert len(iter_2.object_details_list) == 2

        # Verify iteration 3
        iter_3 = report_data.iterations[1]
        assert iter_3.report_id == "lyy0-uf3p"
        assert iter_3.iteration_number == 3
        assert iter_3.memory_usage.current_rss_bytes == 356024320
        assert iter_3.memory_usage.peak_rss_bytes == 376750080
        assert iter_3.leak_summary.iteration == 3
        assert len(iter_3.leak_summary.type_summaries) == 2
        assert len(iter_3.object_details_list) == 2

    @pytest.mark.asyncio
    async def test_get_report_with_filter_types(
        self, mcp_client: Client[Any], test_reports_dir: Path
    ) -> None:
        """
        Test getting a report with type filtering.
        """
        async with mcp_client:
            result = await mcp_client.call_tool(
                "get_leak_report",
                {
                    "report_id": "ykik-ab4l",
                    "report_directory": str(test_reports_dir),
                    "filter_types": "MemalotObject",
                },
            )

        assert hasattr(result, "data"), f"Result {type(result)} has no data attribute"
        assert not result.is_error, "Tool call should not result in an error"
        report_data = result.data

        # Verify summary metadata
        assert report_data.summary.metadata.report_id == "ykik-ab4l"
        assert report_data.summary.metadata.entrypoint == "utils_for_testing.py"
        assert report_data.summary.metadata.arguments == ["dummy_arg1", "dummy_arg2"]
        assert report_data.summary.iteration_count == 3

        # Verify we get 1 iteration (default num_iterations=1)
        assert len(report_data.iterations) == 1
        iteration = report_data.iterations[0]
        assert iteration.report_id == "ykik-ab4l"
        assert iteration.iteration_number == 3

        # Verify leak summary
        assert iteration.leak_summary.iteration == 3
        assert len(iteration.leak_summary.type_summaries) == 1
        assert iteration.leak_summary.type_summaries[0].object_type == "__main__.MemalotObject"
        assert iteration.leak_summary.type_summaries[0].count == 1

    @pytest.mark.asyncio
    async def test_get_report_invalid_id(
        self, mcp_client: Client[Any], test_reports_dir: Path
    ) -> None:
        """
        Test getting a report with an invalid/nonexistent ID.
        """
        async with mcp_client:
            with pytest.raises(ToolError, match="Report with ID does-not-exist not found"):
                _ = await mcp_client.call_tool(
                    "get_leak_report",
                    {"report_id": "does-not-exist", "report_directory": str(test_reports_dir)},
                )
