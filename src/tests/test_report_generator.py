from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from memalot.base import ApproximateSize, CachingIterable, MemalotCount
from memalot.memory import MemalotMemoryUsage
from memalot.options import Options
from memalot.output import Output, OutputWriter
from memalot.report_generator import ReportGenerator
from memalot.reports import (
    LeakSummary,
    MemoryUsageOutput,
    ObjectDetails,
    ReportIteration,
    ReportWriter,
    TypeSummary,
)
from memalot.snapshots import MemalotObjects, MemalotSnapshotManager
from tests.utils_for_testing import create_mock


class _FakeOutputWriter(OutputWriter):
    """
    Simple OutputWriter implementation for testing that captures written output.
    """

    def __init__(self) -> None:
        self.written_outputs: list[ReportIteration] = []

    def write(self, output: Output) -> None:
        # For testing, we expect ReportIteration which is a subclass of Output
        assert isinstance(output, ReportIteration)
        self.written_outputs.append(output)


class _FakeReportWriter(ReportWriter):
    """
    Simple ReportWriter implementation for testing that captures written reports.
    """

    def __init__(self, report_id: str) -> None:
        self._report_id = report_id
        self.written_reports: list[ReportIteration] = []

    def write_iteration(self, iteration: ReportIteration) -> None:
        self.written_reports.append(iteration)

    @property
    def report_id(self) -> str:
        return self._report_id


@pytest.fixture(name="report_generator")
def _report_generator() -> ReportGenerator:
    """
    Creates a ReportGenerator instance for testing.
    """
    return ReportGenerator()


@pytest.fixture(name="mock_iteration")
def _mock_iteration() -> MemalotCount:
    """
    Creates a MemalotCount instance for testing.
    """
    return MemalotCount(3)


@pytest.fixture(name="mock_type_summaries")
def _mock_type_summaries() -> list[TypeSummary]:
    return [
        TypeSummary(
            object_type="builtins.str",
            count=5,
            shallow_size_bytes=ApproximateSize(approx_size=100, upper_bound_known=True),
        ),
        TypeSummary(
            object_type="builtins.int",
            count=3,
            shallow_size_bytes=ApproximateSize(approx_size=72, upper_bound_known=True),
        ),
    ]


@pytest.fixture(name="mock_leak_summary")
def _mock_leak_summary(
    mock_iteration: MemalotCount, mock_type_summaries: list[TypeSummary]
) -> LeakSummary:
    return LeakSummary(
        iteration=mock_iteration,
        type_summaries=mock_type_summaries,
    )


@pytest.fixture(name="mock_object_details")
def _mock_object_details() -> list[ObjectDetails]:
    return [create_mock(spec=ObjectDetails), create_mock(spec=ObjectDetails)]


@pytest.fixture(name="mock_memory_usage")
def _mock_memory_usage(mock_iteration: MemalotCount) -> MemalotMemoryUsage:
    return MemalotMemoryUsage(
        current_rss_bytes=1024 * 1024,
        peak_rss_bytes=2048 * 1024,
        system_percent_used=25.5,
        iteration_number=int(mock_iteration),
    )


@pytest.fixture(name="mock_objects_with_details")
def _mock_objects_with_details(
    mock_leak_summary: LeakSummary,
    mock_object_details: list[ObjectDetails],
) -> MemalotObjects:
    """
    Creates MemalotObjects with mocked details.
    """
    mock_objects = create_mock(spec=MemalotObjects)
    mock_objects.generate_object_details.return_value = iter(mock_object_details)
    mock_objects.get_leak_summary.return_value = mock_leak_summary
    mock_objects.__len__.return_value = 8
    return mock_objects


@pytest.fixture(name="mock_empty_objects")
def _mock_empty_objects() -> MemalotObjects:
    """
    Creates empty MemalotObjects.
    """
    mock_objects = create_mock(spec=MemalotObjects)
    mock_objects.generate_object_details.return_value = iter([])
    mock_objects.get_leak_summary.return_value = create_mock(spec=LeakSummary)
    mock_objects.__len__.return_value = 0
    return mock_objects


@pytest.fixture(name="mock_memory_usage_provider")
def _mock_memory_usage_provider(
    mock_memory_usage: MemalotMemoryUsage,
) -> MagicMock:
    """
    Creates a mock memory usage provider for testing.
    """
    mock_provider = create_mock(spec=MemalotSnapshotManager)
    mock_provider.rotate_memory_usage.return_value = None, mock_memory_usage
    return mock_provider


@pytest.fixture(name="mock_memory_usage_provider_with_previous")
def _mock_memory_usage_provider_with_previous(
    mock_memory_usage: MemalotMemoryUsage,
    mock_iteration: MemalotCount,
) -> MagicMock:
    """
    Creates a mock memory usage provider with previous memory usage.
    """
    mock_provider = create_mock(spec=MemalotSnapshotManager)
    mock_provider.rotate_memory_usage.return_value = (
        MemalotMemoryUsage(
            current_rss_bytes=0,
            peak_rss_bytes=0,
            system_percent_used=0,
            iteration_number=int(mock_iteration) - 1,
        ),
        mock_memory_usage,
    )
    return mock_provider


@pytest.fixture(name="fake_output_writer")
def _fake_output_writer() -> _FakeOutputWriter:
    """
    Creates a fake output writer that captures written output.
    """
    return _FakeOutputWriter()


@pytest.fixture(name="fake_report_writer")
def _fake_report_writer() -> _FakeReportWriter:
    """
    Creates a fake report writer that captures written reports.
    """
    return _FakeReportWriter(report_id="test-report-123")


@pytest.fixture(name="default_options")
def _default_options() -> Options:
    """
    Creates default options for testing.
    """
    return Options()


@pytest.fixture(name="test_objects")
def _test_objects() -> list[Any]:
    """
    Creates a list of test objects.
    """
    return ["test_string", 42, [1, 2, 3], {"key": "value"}]


class TestReportGenerator:
    """
    Tests for the `ReportGenerator` class.
    """

    def test_generate_report(
        self,
        report_generator: ReportGenerator,
        mock_memory_usage_provider: MagicMock,
        fake_output_writer: _FakeOutputWriter,
        fake_report_writer: _FakeReportWriter,
        default_options: Options,
        test_objects: list[Any],
        mock_iteration: MemalotCount,
        mock_memory_usage: MemalotMemoryUsage,
    ) -> None:
        """
        Tests the basic flow of the generate_report method with detailed_report=True.
        """
        excluded_from_referrers: list[int] = []

        before_time = datetime.now(timezone.utc)
        iteration_start_time = datetime.now(timezone.utc)
        report_generator.generate_report(
            report_id="test-report-123",
            iteration_start_time=iteration_start_time,
            memory_usage_provider=mock_memory_usage_provider,
            objects=MemalotObjects(test_objects),
            output_writer=fake_output_writer,
            report_writer=fake_report_writer,
            options=default_options,
            iteration=mock_iteration,
            excluded_from_referrers=excluded_from_referrers,
            detailed_report=True,
        )
        after_time = datetime.now(timezone.utc)

        assert len(fake_output_writer.written_outputs) == 1
        assert len(fake_report_writer.written_reports) == 1

        written_output = fake_output_writer.written_outputs[0]
        written_report = fake_report_writer.written_reports[0]

        # Both writers should have the same object (at the moment)
        assert written_output is written_report

        assert written_report.report_id == "test-report-123"
        assert written_report.iteration_number == mock_iteration
        assert before_time <= written_report.end_time <= after_time

        expected_memory_usage = MemoryUsageOutput(
            current_rss_bytes=mock_memory_usage.current_rss_bytes,
            peak_rss_bytes=mock_memory_usage.peak_rss_bytes,
            system_percent_used=mock_memory_usage.system_percent_used,
            current_rss_diff=None,  # No previous usage
            peak_rss_diff=None,
            diff_from_iteration=None,
        )
        assert written_report.memory_usage == expected_memory_usage

        # Check the leak summary has correct types (based on test_objects)
        assert written_report.leak_summary.iteration == mock_iteration
        type_names = [ts.object_type for ts in written_report.leak_summary.type_summaries]
        # test_objects = ["test_string", 42, [1, 2, 3], {"key": "value"}]
        assert "builtins.str" in type_names
        assert "builtins.int" in type_names
        assert "builtins.list" in type_names
        assert "builtins.dict" in type_names

        assert isinstance(written_report.object_details_list, CachingIterable)

        # Verify memory usage was rotated
        mock_memory_usage_provider.rotate_memory_usage.assert_called_once_with(
            iteration=mock_iteration
        )

    def test_generate_report_no_snapshot(
        self,
        report_generator: ReportGenerator,
        mock_memory_usage_provider: MagicMock,
        fake_output_writer: _FakeOutputWriter,
        fake_report_writer: _FakeReportWriter,
        default_options: Options,
        test_objects: list[Any],
        mock_iteration: MemalotCount,
        mock_memory_usage: MemalotMemoryUsage,
    ) -> None:
        """
        Tests the generate_report method and detailed_report=True.

        Currently, this just generates an empty report (no error).
        """
        excluded_from_referrers: list[int] = []
        iteration_start_time = datetime.now(timezone.utc)

        report_generator.generate_report(
            report_id="test-report-123",
            iteration_start_time=iteration_start_time,
            memory_usage_provider=mock_memory_usage_provider,
            objects=MemalotObjects(test_objects),
            output_writer=fake_output_writer,
            report_writer=fake_report_writer,
            options=default_options,
            iteration=mock_iteration,
            excluded_from_referrers=excluded_from_referrers,
            detailed_report=True,
        )

        # Should generate a report
        written_report = fake_report_writer.written_reports[0]
        assert written_report.report_id == "test-report-123"

    def test_generate_report_no_diff(
        self,
        report_generator: ReportGenerator,
        mock_memory_usage_provider: MagicMock,
        fake_output_writer: _FakeOutputWriter,
        fake_report_writer: _FakeReportWriter,
        default_options: Options,
        test_objects: list[Any],
        mock_iteration: MemalotCount,
        mock_memory_usage: MemalotMemoryUsage,
    ) -> None:
        """
        Tests the generate_report method with empty objects and detailed_report=True.
        """
        excluded_from_referrers: list[int] = []
        iteration_start_time = datetime.now(timezone.utc)

        report_generator.generate_report(
            report_id="test-report-123",
            iteration_start_time=iteration_start_time,
            memory_usage_provider=mock_memory_usage_provider,
            objects=MemalotObjects([]),
            output_writer=fake_output_writer,
            report_writer=fake_report_writer,
            options=default_options,
            iteration=mock_iteration,
            excluded_from_referrers=excluded_from_referrers,
            detailed_report=True,
        )
        written_report = fake_report_writer.written_reports[0]

        assert written_report.leak_summary == LeakSummary(
            iteration=mock_iteration,
            type_summaries=[],
            max_types_in_summary=500,
        )

        assert isinstance(written_report.object_details_list, CachingIterable)
        assert list(written_report.object_details_list) == []

        # Verify memory usage was rotated
        mock_memory_usage_provider.rotate_memory_usage.assert_called_once_with(
            iteration=mock_iteration
        )

    def test_generate_report_with_previous_memory_usage(
        self,
        report_generator: ReportGenerator,
        mock_memory_usage_provider_with_previous: MagicMock,
        fake_output_writer: _FakeOutputWriter,
        fake_report_writer: _FakeReportWriter,
        default_options: Options,
        test_objects: list[Any],
        mock_iteration: MemalotCount,
        mock_memory_usage: MemalotMemoryUsage,
    ) -> None:
        """
        Tests the generate_report method with previous memory usage present and
        detailed_report=True.
        """
        excluded_from_referrers: list[int] = []
        iteration_start_time = datetime.now(timezone.utc)

        report_generator.generate_report(
            report_id="test-report-123",
            iteration_start_time=iteration_start_time,
            memory_usage_provider=mock_memory_usage_provider_with_previous,
            objects=MemalotObjects([]),
            output_writer=fake_output_writer,
            report_writer=fake_report_writer,
            options=default_options,
            iteration=mock_iteration,
            excluded_from_referrers=excluded_from_referrers,
            detailed_report=True,
        )

        written_report = fake_report_writer.written_reports[0]

        assert written_report.memory_usage == MemoryUsageOutput(
            current_rss_bytes=mock_memory_usage.current_rss_bytes,
            peak_rss_bytes=mock_memory_usage.peak_rss_bytes,
            system_percent_used=mock_memory_usage.system_percent_used,
            current_rss_diff=mock_memory_usage.current_rss_bytes,
            peak_rss_diff=mock_memory_usage.peak_rss_bytes,
            diff_from_iteration=mock_iteration - 1,
        )

    def test_generate_report_detailed_report_false(
        self,
        report_generator: ReportGenerator,
        mock_memory_usage_provider: MagicMock,
        fake_output_writer: _FakeOutputWriter,
        fake_report_writer: _FakeReportWriter,
        default_options: Options,
        test_objects: list[Any],
        mock_iteration: MemalotCount,
        mock_memory_usage: MemalotMemoryUsage,
    ) -> None:
        """
        Tests the generate_report method with detailed_report=False returns empty summary
        and referrers.
        """
        excluded_from_referrers: list[int] = []

        before_time = datetime.now(timezone.utc)
        iteration_start_time = datetime.now(timezone.utc)
        report_generator.generate_report(
            report_id="test-report-123",
            iteration_start_time=iteration_start_time,
            memory_usage_provider=mock_memory_usage_provider,
            objects=MemalotObjects(test_objects),
            output_writer=fake_output_writer,
            report_writer=fake_report_writer,
            options=default_options,
            iteration=mock_iteration,
            excluded_from_referrers=excluded_from_referrers,
            detailed_report=False,
        )
        after_time = datetime.now(timezone.utc)

        assert len(fake_output_writer.written_outputs) == 1
        assert len(fake_report_writer.written_reports) == 1

        written_output = fake_output_writer.written_outputs[0]
        written_report = fake_report_writer.written_reports[0]

        # Both writers should have the same object (at the moment)
        assert written_output is written_report

        assert written_report.report_id == "test-report-123"
        assert written_report.iteration_number == mock_iteration
        assert before_time <= written_report.end_time <= after_time

        expected_memory_usage = MemoryUsageOutput(
            current_rss_bytes=mock_memory_usage.current_rss_bytes,
            peak_rss_bytes=mock_memory_usage.peak_rss_bytes,
            system_percent_used=mock_memory_usage.system_percent_used,
            current_rss_diff=None,  # No previous usage
            peak_rss_diff=None,
            diff_from_iteration=None,
        )
        assert written_report.memory_usage == expected_memory_usage

        # When detailed_report=False, should get empty leak summary
        expected_leak_summary = LeakSummary(
            iteration=mock_iteration,
            type_summaries=[],
            max_types_in_summary=default_options.max_types_in_leak_summary,
        )
        assert written_report.leak_summary == expected_leak_summary

        # When detailed_report=False, should get empty referrers
        assert isinstance(written_report.object_details_list, CachingIterable)
        assert list(written_report.object_details_list) == []

        # Verify memory usage was rotated
        mock_memory_usage_provider.rotate_memory_usage.assert_called_once_with(
            iteration=mock_iteration
        )
