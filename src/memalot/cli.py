#!/usr/bin/env python3
"""
CLI tool for listing memory reports.
"""

import argparse
import sys
from pathlib import Path
from typing import List

from rich import box
from rich.console import Console
from rich.table import Table

from memalot.options import Options
from memalot.output import get_output_writer
from memalot.reports import (
    FullReport,
    ReportIteration,
    ReportSummary,
    filter_iteration_by_types,
    get_report_reader,
)
from memalot.themes import (
    CLI_ITERATIONS_COLUMN,
    CLI_LIST_REPORT_ID,
    CLI_NO_REPORTS_MESSAGE,
    CLI_TABLE_HEADER,
    CLI_TABLE_STYLE,
    CLI_TABLE_TITLE,
    DEFAULT_RICH_THEME,
)


def _list_reports(num_reports: int = 5, report_directory: str | None = None) -> List[ReportSummary]:
    """
    List the most recent reports.

    Args:
        num_reports: The number of reports to return.
        report_directory: The directory to search for reports. If None, the
            default directory will be used.

    Returns:
        A list of ReportSummary objects.
    """
    reader = get_report_reader(
        report_directory=Path(report_directory) if report_directory else None
    )
    summaries = reader.get_report_summaries()
    summaries.sort(key=lambda s: s.metadata.start_time, reverse=True)
    return summaries[:num_reports]


def _print_report(
    report_id: str,
    num_iterations: int = 1,
    report_directory: str | None = None,
    force_terminal: bool | None = None,
    filter_types: List[str] | None = None,
    summary_only: bool = False,
) -> None:
    """
    Print a specific report to the console.

    Args:
        report_id: The ID of the report to print.
        num_iterations: The number of iterations to print. Defaults to 1 (last iteration).
        report_directory: The directory to search for reports. If None, the
            default directory will be used.
        force_terminal: Forces the use of terminal control codes for colors and formatting.
        filter_types: List of object type substrings to filter on. If provided, only
            objects whose type names contain any of these substrings will be included.
        summary_only: If True, only print the summary table and not the full iterations.
    """
    reader = get_report_reader(
        report_directory=Path(report_directory) if report_directory else None
    )
    full_report: FullReport = reader.get_full_report(
        report_id=report_id, num_iterations=num_iterations
    )

    options = Options(force_terminal=force_terminal)
    writer = get_output_writer(options)

    for iteration in full_report.iterations:
        if summary_only:
            iteration = ReportIteration(
                report_id=iteration.report_id,
                iteration_number=iteration.iteration_number,
                start_time=iteration.start_time,
                end_time=iteration.end_time,
                memory_usage=iteration.memory_usage,
                leak_summary=iteration.leak_summary,
                object_details_list=[],
            )
        if filter_types:
            filtered_iteration = filter_iteration_by_types(iteration, filter_types)
            writer.write(filtered_iteration)
        else:
            writer.write(iteration)


def _display_reports(summaries: List[ReportSummary], force_terminal: bool | None = None) -> None:
    """
    Display the report summaries using rich formatting.

    Args:
        summaries: List of report summaries to display.
        force_terminal: Forces the use of terminal control codes for colors and formatting.
    """
    console = Console(theme=DEFAULT_RICH_THEME, force_terminal=force_terminal)

    if not summaries:
        console.print("No reports found.", style=CLI_NO_REPORTS_MESSAGE)
        return

    table = Table(
        title="Reports",
        title_style=CLI_TABLE_TITLE,
        show_lines=True,
        style=CLI_TABLE_STYLE,
        header_style=CLI_TABLE_HEADER,
        box=box.ROUNDED,
    )

    table.add_column("Report ID", style=CLI_LIST_REPORT_ID, no_wrap=True)
    table.add_column("Iterations", style=CLI_ITERATIONS_COLUMN, justify="right", no_wrap=True)
    table.add_column("Start Time", no_wrap=True)
    table.add_column("Entrypoint", no_wrap=False, overflow="fold")
    table.add_column("Arguments", no_wrap=False, overflow="fold")

    for summary in summaries:
        # Format the start time nicely
        start_time_str = summary.metadata.start_time.strftime("%Y-%m-%d %H:%M:%S")

        # Format arguments - join them without truncation
        args_str = " ".join(summary.metadata.arguments)

        table.add_row(
            summary.metadata.report_id,
            str(summary.iteration_count),
            start_time_str,
            summary.metadata.entrypoint,
            args_str,
        )

    console.print(table)


def entrypoint(sys_args: List[str]) -> int:
    """
    Main CLI entry point.
    """
    parser = argparse.ArgumentParser(description="Memalot memory reports CLI", prog="memalot")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List recent reports")
    list_parser.add_argument(
        "--num-reports", type=int, default=10, help="Number of reports to display (default: 10)"
    )
    list_parser.add_argument(
        "--report-directory",
        type=str,
        help="Directory to search for reports (default: ~/.memalot/reports)",
    )
    list_parser.add_argument(
        "--force-terminal",
        action="store_true",
        help="Force the use of terminal control codes for colors and formatting",
    )

    # Print command
    print_parser = subparsers.add_parser("print", help="Print a specific report")
    print_parser.add_argument(
        "report_id",
        type=str,
        help="The ID of the report to print",
    )
    print_parser.add_argument(
        "--num-iterations",
        type=int,
        default=1,
        help="Number of iterations to print (default: 1, most recent)",
    )
    print_parser.add_argument(
        "--report-directory",
        type=str,
        help="Directory to search for reports (default: ~/.memalot/reports)",
    )
    print_parser.add_argument(
        "--force-terminal",
        action="store_true",
        help="Force the use of terminal control codes for colors and formatting",
    )
    print_parser.add_argument(
        "--filter-types",
        type=str,
        help="Filter by object types (comma-separated substrings, case-insensitive)",
    )
    print_parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Only print the summary table and not object details",
    )

    args = parser.parse_args(sys_args)

    if args.command == "list":
        summaries = _list_reports(
            num_reports=args.num_reports, report_directory=args.report_directory
        )
        _display_reports(
            summaries, force_terminal=args.force_terminal if args.force_terminal else None
        )
    elif args.command == "print":
        # Parse comma-separated filter types
        filter_types = None
        if args.filter_types:
            filter_types = [t.strip() for t in args.filter_types.split(",") if t.strip()]

        _print_report(
            report_id=args.report_id,
            num_iterations=args.num_iterations,
            report_directory=args.report_directory,
            force_terminal=args.force_terminal if args.force_terminal else None,
            filter_types=filter_types,
            summary_only=args.summary_only,
        )
    else:  # pragma: no cover
        parser.print_help()
        return 1

    return 0


def main() -> None:  # pragma: no cover
    sys.exit(entrypoint(sys.argv[1:]))


if __name__ == "__main__":  # pragma: no cover
    main()
