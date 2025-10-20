# mypy: ignore-errors
from pathlib import Path
from typing import Any, List

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic.dataclasses import dataclass

from memalot.reports import (
    FullReport,
    ReportSummary,
    filter_iteration_by_types,
    get_report_reader,
)

mcp: FastMCP[Any] = FastMCP("Memalot MCP Server")


@dataclass
class ReportSummaries:
    """
    Wraps a list of report summaries so that they can be returning from the MCP server.
    Just returning a list gives slightly odd results.
    """

    summaries: List[ReportSummary]


@mcp.tool(
    annotations=ToolAnnotations(
        title="List Reports",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def list_leak_reports(num_reports: int = 5, report_directory: str | None = None) -> ReportSummaries:
    """
    List the `num_reports` most recent memory reports that have been run.
    The reports are ordered by start time with the most recent report first.

    By default, the server will return the 5 most recent reports.
    This can be overridden by passing a different value for `num_reports`.

    Args:
        num_reports: The number of reports to return.
        report_directory: The directory to search for reports. If `None`, the
        default directory will be used. This is the `.memalot/reports` directory
        in the user's home directory.

    Returns:
        A `ReportSummaries` object.
    """
    reader = get_report_reader(
        report_directory=Path(report_directory) if report_directory else None
    )
    summaries = reader.get_report_summaries()
    summaries.sort(key=lambda s: s.metadata.start_time, reverse=True)
    return ReportSummaries(summaries[:num_reports])


@mcp.tool(
    annotations=ToolAnnotations(
        title="Get Report",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def get_leak_report(
    report_id: str,
    num_iterations: int = 1,
    report_directory: str | None = None,
    filter_types: str | None = None,
) -> FullReport:
    """
    Get the full report for a specific ID.

    By default, the server will return the most recent iteration of the report.
    This can be overridden by passing a different value for `num_iterations`.

    Args:
        report_id: The ID of the report to get. This can be obtained from the
        `list_reports` method.
        num_iterations: The number of iterations to return.
        report_directory: The directory to search for reports. If `None`, the
        default directory will be used.
        filter_types: A comma-separated list of types to filter on. Only these types
        are included in the report. This is useful for reducing the size of reports
        to more easily fit them in a model's context window, for example.

    Returns:
        A `FullReport` object.
    """
    reader = get_report_reader(
        report_directory=Path(report_directory) if report_directory else None
    )
    full_report = reader.get_full_report(report_id=report_id, num_iterations=num_iterations)

    if filter_types:
        filter_types_list = [t.strip() for t in filter_types.split(",") if t.strip()]
        # Filter each iteration
        filtered_iterations = [
            filter_iteration_by_types(iteration, filter_types_list)
            for iteration in full_report.iterations
        ]
        # Return a new FullReport with filtered iterations
        return FullReport(
            summary=full_report.summary,
            iterations=filtered_iterations,
        )
    else:
        return full_report


def run_mcp_server() -> None:  # pragma: no cover
    """
    Run the Memalot MCP server.
    """
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    run_mcp_server()
