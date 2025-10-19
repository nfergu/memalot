"""
Helper functions for integration tests.
"""

from __future__ import annotations

from pathlib import Path

from memalot.base import ReferrerGraph
from memalot.reports import (
    FileReportReader,
    FullReport,
    ObjectDetails,
    ReportIteration,
    TypeSummary,
)
from tests.utils_for_testing import one


def has_leak_iterations(
    reader: FileReportReader,
    expected_leak_iterations: int,
) -> bool:
    """
    Checks if the specified number of report iterations with leaks has been generated.
    """
    summaries = reader.get_report_summaries()
    if len(summaries) > 0:
        assert len(summaries) == 1, f"Expected exactly 1 summary, got {len(summaries)}"
        summary = summaries[0]
        if summary.iteration_count >= expected_leak_iterations:
            full_report_check = reader.get_full_report(
                report_id=summary.metadata.report_id, num_iterations=100
            )
            iterations_with_leaks = sum(
                1
                for iteration in full_report_check.iterations
                if len(iteration.leak_summary.type_summaries) > 0
            )
            if iterations_with_leaks >= expected_leak_iterations:
                return True
    return False


def read_single_report(tmp_path: Path) -> FullReport:
    """
    Reads a single report from the given directory.
    """
    reader = FileReportReader(report_directory=tmp_path)
    summaries = reader.get_report_summaries()
    assert len(summaries) == 1

    summary = one(summaries)
    metadata = summary.metadata
    full_report = reader.get_full_report(report_id=metadata.report_id, num_iterations=100)
    return full_report


def assert_iteration_count(full_report: FullReport, expected_count: int) -> None:
    """
    Asserts that the report has the expected number of iterations.
    """
    assert full_report.summary.iteration_count == expected_count
    assert len(full_report.iterations) == expected_count


def assert_warmup_iteration(iteration: ReportIteration) -> None:
    """
    Asserts that the given iteration is a warmup iteration with no leaks.
    """
    assert len(iteration.leak_summary.type_summaries) == 0
    assert len(list(iteration.object_details_list)) == 0


def assert_type_summaries(
    type_summaries: list[TypeSummary], expected_types: set[str], expected_counts: set[int]
) -> None:
    """
    Asserts that the type summaries contain the expected types and counts.
    """
    actual_types = {summary.object_type for summary in type_summaries}
    assert actual_types == expected_types, f"Expected types {expected_types}, got {actual_types}"
    actual_counts = {summary.count for summary in type_summaries}
    assert actual_counts == expected_counts, (
        f"Expected counts {expected_counts}, got {actual_counts}"
    )


def assert_object_details_types(
    object_details_list: list[ObjectDetails], expected_types: set[str]
) -> None:
    """
    Asserts that the object details list contains objects of the expected types.
    """
    object_details_types = {
        object_details.object_type_name for object_details in object_details_list
    }
    assert object_details_types == expected_types


def filter_object_details_by_type(
    object_details_list: list[ObjectDetails], object_type: str
) -> list[ObjectDetails]:
    """
    Filters the object details list to include only objects of the specified type.
    """
    return [
        object_details
        for object_details in object_details_list
        if object_details.object_type_name == object_type
    ]


def assert_referrer_graph_target_names(
    referrer_graph: ReferrerGraph, expected_target_names: set[str]
) -> None:
    """
    Asserts that the referrer graph has the expected target node names.
    """
    actual_target_names = {
        node.name for node in referrer_graph.graph_nodes if node.id in referrer_graph.target_ids
    }
    assert actual_target_names == expected_target_names, (
        f"Expected target names: {expected_target_names}, "
        f"Actual target names: {actual_target_names}"
    )


def assert_referrers_checked(object_details_list: list[ObjectDetails]) -> None:
    """
    Asserts that referrers have been checked for all object details.
    """
    for details in object_details_list:
        assert details.referrers_checked is True
        assert details.referrer_graph is not None


def assert_all_referrer_graphs_have_target_names(
    object_details_list: list[ObjectDetails], expected_target_names: set[str]
) -> None:
    """
    Asserts that all object details have referrer graphs with the expected target names.

    This helper verifies that:
    - All details have referrer graphs
    - Each referrer graph has the expected target names
    """
    for details in object_details_list:
        assert details.referrer_graph is not None
        assert_referrer_graph_target_names(
            referrer_graph=details.referrer_graph, expected_target_names=expected_target_names
        )


def assert_referrer_graphs_have_root_names(
    object_details_list: list[ObjectDetails], expected_root_names: set[str]
) -> None:
    """
    Asserts that the total set of root names in the referrer graphs for all object details
    is equal to the expected set.
    """
    all_root_names: set[str] = set()
    for details in object_details_list:
        assert details.referrer_graph is not None
        all_root_names.update(
            node.name
            for node in details.referrer_graph.graph_nodes
            if node.id in details.referrer_graph.root_ids
        )
    assert all_root_names == expected_root_names, (
        f"Expected root names: {expected_root_names}, Actual root names: {all_root_names}"
    )


def assert_object_type_details(
    object_details_list: list[ObjectDetails],
    object_type: str,
    expected_count: int,
    expected_target_names: set[str],
) -> list[ObjectDetails]:
    """
    Filters, counts, and verifies object details for a specific type.

    This helper performs the common pattern of:
    1. Filtering object details by type
    2. Asserting the expected count
    3. Verifying referrers are checked
    4. Verifying target names

    Returns the filtered list of object details for further assertions.
    """
    filtered_list = filter_object_details_by_type(
        object_details_list=object_details_list, object_type=object_type
    )
    assert len(filtered_list) == expected_count, (
        f"Expected {expected_count} {object_type} objects, found {len(filtered_list)}"
    )
    assert_referrers_checked(object_details_list=filtered_list)
    assert_all_referrer_graphs_have_target_names(
        object_details_list=filtered_list, expected_target_names=expected_target_names
    )
    return filtered_list
