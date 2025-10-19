import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import networkx as nx
import pytest
from pydantic import TypeAdapter
from pytest_mock import MockerFixture
from referrers import ReferrerGraphNode
from rich.console import Console, RenderableType

from memalot import reports
from memalot.base import ApproximateSize, CachingIterable
from memalot.memory import MemalotMemoryUsage
from memalot.options import Options
from memalot.reports import (
    FileReportReader,
    FileReportWriter,
    LeakSummary,
    MemoryUsageOutput,
    NoOpReportWriter,
    ObjectDetails,
    ReportIteration,
    ReportMetadata,
    ReportSummary,
    TypeSummary,
    filter_iteration_by_types,
    get_memory_usage_output,
    get_report_writer,
)
from memalot.themes import DEFAULT_RICH_THEME
from memalot.utils import PrintableReferrerNode, convert_graph_nodes


@pytest.fixture(name="sample_report_metadata")
def _sample_report_metadata() -> ReportMetadata:
    return ReportMetadata(
        report_id="abcd-1234",
        entrypoint="/path/to/entry.py",
        arguments=["--flag", "value"],
        start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture(name="sample_memory_usage")
def _sample_memory_usage() -> MemoryUsageOutput:
    return MemoryUsageOutput(
        current_rss_bytes=262144,
        peak_rss_bytes=524288,
        system_percent_used=12.34,
        current_rss_diff=512,
        peak_rss_diff=1024,
        diff_from_iteration=1,
    )


@pytest.fixture(name="sample_type_summaries")
def _sample_type_summaries() -> List[TypeSummary]:
    return [
        TypeSummary(
            object_type="collections.MyType",
            count=3,
            shallow_size_bytes=ApproximateSize(approx_size=123, upper_bound_known=True),
        ),
        TypeSummary(
            object_type="mymodule.OtherType",
            count=1,
            shallow_size_bytes=ApproximateSize(approx_size=456, upper_bound_known=False),
        ),
    ]


@pytest.fixture(name="sample_leak_summary")
def _sample_leak_summary(sample_type_summaries: List[TypeSummary]) -> LeakSummary:
    return LeakSummary(
        iteration=2,
        type_summaries=sample_type_summaries,
        max_types_in_summary=500,
    )


@pytest.fixture(name="sample_leak_summary_truncated")
def _sample_leak_summary_truncated(sample_type_summaries: List[TypeSummary]) -> LeakSummary:
    return LeakSummary(
        iteration=2,
        type_summaries=sample_type_summaries,
        max_types_in_summary=1,
    )


@pytest.fixture(name="sample_type_summaries_no_sizes")
def _sample_type_summaries_no_sizes() -> List[TypeSummary]:
    return [
        TypeSummary(
            object_type="collections.MyType",
            count=3,
            shallow_size_bytes=None,
        ),
        TypeSummary(
            object_type="mymodule.OtherType",
            count=1,
            shallow_size_bytes=None,
        ),
    ]


@pytest.fixture(name="sample_leak_summary_no_sizes")
def _sample_leak_summary_no_sizes(sample_type_summaries_no_sizes: List[TypeSummary]) -> LeakSummary:
    return LeakSummary(
        iteration=2,
        type_summaries=sample_type_summaries_no_sizes,
        max_types_in_summary=500,
    )


@pytest.fixture(name="sample_referrer_graph")
def _sample_referrer_graph() -> nx.DiGraph:
    g: nx.DiGraph = nx.DiGraph()
    # Create ReferrerGraphNode objects
    node1 = ReferrerGraphNode(name="root", id=1001, type="local")
    node2 = ReferrerGraphNode(name="child", id=1002, type="attr")
    g.add_node(node1)
    g.add_node(node2)
    g.add_edge(node1, node2)
    return g


@pytest.fixture(name="sample_object_details")
def _sample_object_details(sample_referrer_graph: nx.DiGraph) -> ObjectDetails:
    return ObjectDetails(
        object_type_name="mymodule.MyType",
        object_id=42,
        object_str="<MyType repr>",
        deep_size_bytes=ApproximateSize(approx_size=24, upper_bound_known=True),
        referrer_graph=convert_graph_nodes(sample_referrer_graph),
        referrers_checked=True,
    )


@pytest.fixture(name="sample_object_details_no_referrers")
def _sample_object_details_no_referrers(sample_referrer_graph: nx.DiGraph) -> ObjectDetails:
    return ObjectDetails(
        object_type_name="mymodule.MyType",
        object_id=42,
        object_str="<MyType repr>",
        deep_size_bytes=ApproximateSize(approx_size=24, upper_bound_known=True),
        referrer_graph=None,
        referrers_checked=True,
    )


@pytest.fixture(name="sample_object_details_referrers_not_checked")
def _sample_object_details_referrers_not_checked() -> ObjectDetails:
    return ObjectDetails(
        object_type_name="mymodule.MyType",
        object_id=42,
        object_str="<MyType repr>",
        deep_size_bytes=ApproximateSize(approx_size=24, upper_bound_known=True),
        referrer_graph=None,
        referrers_checked=False,
    )


@pytest.fixture(name="sample_report_iteration_no_leaks")
def _sample_report_iteration_no_leaks(
    sample_report_iteration: ReportIteration,
) -> ReportIteration:
    return ReportIteration(
        report_id=sample_report_iteration.report_id,
        iteration_number=1,
        start_time=sample_report_iteration.start_time,
        end_time=sample_report_iteration.end_time,
        memory_usage=sample_report_iteration.memory_usage,
        leak_summary=LeakSummary(
            iteration=1,
            type_summaries=[],
            max_types_in_summary=500,
        ),
        object_details_list=[],
    )


@pytest.fixture(name="sample_report_iteration")
def _sample_report_iteration(
    sample_memory_usage: MemoryUsageOutput,
    sample_leak_summary: LeakSummary,
    sample_object_details: ObjectDetails,
) -> ReportIteration:
    return ReportIteration(
        report_id="abcd-1234",
        iteration_number=2,
        start_time=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc),
        memory_usage=sample_memory_usage,
        leak_summary=sample_leak_summary,
        object_details_list=[sample_object_details],
    )


class TestMemoryUsageOutput:
    """
    Tests for the `MemoryUsageOutput` class.
    """

    def test_to_renderables(self, sample_memory_usage: MemoryUsageOutput) -> None:
        renderables = sample_memory_usage.to_renderables()
        expected = (
            "Memory used: 0.2 MiB (+0.000488 MiB) / 12.34% sys\n"
            "Peak memory: 0.5 MiB (+0.000977 MiB)\n"
        )
        memory_usage_str = _get_renderables_as_string(renderables)
        assert memory_usage_str == expected


class TestLeakSummary:
    def test_to_renderables(self, sample_leak_summary: LeakSummary) -> None:
        renderables = sample_leak_summary.to_renderables()
        table_str = _get_renderables_as_string(renderables)
        assert "│ Object Type        │ Count │ Shallow size (estimated) │" in table_str
        assert "collections.MyType │     3 │                   ~123 B" in table_str
        assert "mymodule.OtherType │     1 │                  >=456 B" in table_str

    def test_to_renderables_no_sizes(self, sample_leak_summary_no_sizes: LeakSummary) -> None:
        renderables = sample_leak_summary_no_sizes.to_renderables()
        table_str = _get_renderables_as_string(renderables)
        assert "│ Object Type        │ Count │" in table_str
        assert "collections.MyType │     3 │" in table_str
        assert "mymodule.OtherType │     1 │" in table_str

    def test_to_renderables_truncated(self, sample_leak_summary_truncated: LeakSummary) -> None:
        renderables = sample_leak_summary_truncated.to_renderables()
        table_str = _get_renderables_as_string(renderables)
        assert "│ Object Type        │ Count │ Shallow size (estimated) │" in table_str
        assert "collections.MyType │     3 │                   ~123 B" in table_str
        assert "(truncated to 1 entries)" in table_str


class TestObjectDetails:
    def test_to_renderables(self, sample_object_details: ObjectDetails) -> None:
        renderables = sample_object_details.to_renderables()
        expected = (
            "+-----------------------------------+\n"
            "|Details for mymodule.MyType (id=42)|\n"
            "+-----------------------------------+\n"
            "\n"
            "Deep size (estimated): ~24 B\n"
            "\n"
            "\n"
            "╙── child (id=1002) \n"
            "    └── root (id=1001) (root)\n"
            "\n"
            "String representation:\n"
            "<MyType repr>\n"
        )
        object_details_str = _get_renderables_as_string(renderables)
        assert object_details_str == expected

    def test_to_renderables__with_referrers_checked_no_referrers_found(
        self, sample_object_details_no_referrers: ObjectDetails
    ) -> None:
        """
        Tests that when referrers_checked=True but no referrers found, it shows
        'No referrers found'.
        """
        renderables = sample_object_details_no_referrers.to_renderables()
        expected = (
            "+-----------------------------------+\n"
            "|Details for mymodule.MyType (id=42)|\n"
            "+-----------------------------------+\n"
            "\n"
            "Deep size (estimated): ~24 B\n"
            "\n"
            "No referrers found\n"
            "\n"
            "String representation:\n"
            "<MyType repr>\n"
        )
        object_details_str = _get_renderables_as_string(renderables)
        assert object_details_str == expected

    def test_to_renderables__with_referrers_not_checked(
        self, sample_object_details_referrers_not_checked: ObjectDetails
    ) -> None:
        """
        Tests that when referrers_checked=False, it shows informative message about enabling
        referrer checking.
        """
        renderables = sample_object_details_referrers_not_checked.to_renderables()
        expected = (
            "+-----------------------------------+\n"
            "|Details for mymodule.MyType (id=42)|\n"
            "+-----------------------------------+\n"
            "\n"
            "Deep size (estimated): ~24 B\n"
            "\n"
            "Not checking referrers. Set the check_referrers option to True to turn on referrer "
            "checking\n"
            "\n"
            "String representation:\n"
            "<MyType repr>\n"
        )
        object_details_str = _get_renderables_as_string(renderables)
        assert object_details_str == expected

    def test_serialize_and_validate_roundtrip(self, sample_object_details: ObjectDetails) -> None:
        data = TypeAdapter(ObjectDetails).dump_json(sample_object_details)
        restored = TypeAdapter(ObjectDetails).validate_json(data)
        assert isinstance(restored, ObjectDetails)
        assert restored == sample_object_details

    def test_serialize_with_none_referrer_graph(self) -> None:
        """
        Test that ObjectDetails serializes correctly when referrer_graph is None.
        """
        from memalot.base import ApproximateSize

        object_details = ObjectDetails(
            object_id=42,
            object_type_name="str",
            object_str="test string",
            deep_size_bytes=ApproximateSize(10),
            referrer_graph=None,
            referrers_checked=True,
        )

        # This should not raise an exception
        data = TypeAdapter(ObjectDetails).dump_json(object_details)
        restored = TypeAdapter(ObjectDetails).validate_json(data)

        assert isinstance(restored, ObjectDetails)
        assert restored.referrer_graph is None
        assert restored == object_details

    def test_hash_not_supported(self, sample_object_details: ObjectDetails) -> None:
        """
        Test that hashing ObjectDetails raises NotImplementedError.
        """
        with pytest.raises(NotImplementedError, match="Hashing ObjectDetails is not supported"):
            hash(sample_object_details)


class TestReportIteration:
    def test_to_renderables(self, sample_report_iteration: ReportIteration) -> None:
        renderables = list(sample_report_iteration.to_renderables())
        iteration_str = _get_renderables_as_string(renderables)
        expected_header = (
            "╭────────── Memalot Report (iteration 2) ───────────╮\n"
            "│                                                   │\n"
            "│               Report ID: abcd-1234                │\n"
            "│ Memory used: 0.2 MiB (+0.000488 MiB) / 12.34% sys │\n"
            "│       Peak memory: 0.5 MiB (+0.000977 MiB)        │\n"
            "│                                                   │\n"
            "╰───────────────────────────────────────────────────╯\n"
        )
        expected_footer = "End of Memalot Report (iteration 2)\n"
        assert expected_header in iteration_str
        assert expected_footer in iteration_str
        assert "Possible New Leaks (iteration 2)" in iteration_str
        assert "Details for mymodule.MyType (id=42)" in iteration_str

    def test_to_renderables_warmup_iteration_message(
        self, sample_report_iteration_no_leaks: ReportIteration
    ) -> None:
        renderables = list(sample_report_iteration_no_leaks.to_renderables())
        iteration_str = _get_renderables_as_string(renderables)
        assert (
            "This is a warmup iteration. Reports will be available from the next iteration."
        ) in iteration_str

    def test_to_renderables_no_leaks_message_non_first_iteration(
        self, sample_report_iteration: ReportIteration
    ) -> None:
        # Create a non-first iteration with no leaks
        iteration_no_leaks = ReportIteration(
            report_id=sample_report_iteration.report_id,
            iteration_number=2,
            start_time=sample_report_iteration.start_time,
            end_time=sample_report_iteration.end_time,
            memory_usage=sample_report_iteration.memory_usage,
            leak_summary=LeakSummary(
                iteration=2,
                type_summaries=[],
                max_types_in_summary=500,
            ),
            object_details_list=[],
        )
        renderables = list(iteration_no_leaks.to_renderables())
        iteration_str = _get_renderables_as_string(renderables)
        assert "No leaks found during this iteration." in iteration_str

    def test_serialization_converts_caching_iterable(
        self, sample_object_details: ObjectDetails
    ) -> None:
        referrers: CachingIterable[ObjectDetails] = CachingIterable([sample_object_details])
        iteration = ReportIteration(
            report_id="abcd-1234",
            iteration_number=5,
            start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc),
            memory_usage=MemoryUsageOutput(
                current_rss_bytes=1,
                peak_rss_bytes=None,
                system_percent_used=1.0,
                current_rss_diff=None,
                peak_rss_diff=None,
                diff_from_iteration=None,
            ),
            leak_summary=LeakSummary(
                iteration=5,
                type_summaries=[],
                max_types_in_summary=500,
            ),
            object_details_list=referrers,
        )
        # Serialize and restore
        dumped = TypeAdapter(ReportIteration).dump_json(iteration)
        restored = TypeAdapter(ReportIteration).validate_json(dumped)
        assert isinstance(restored, ReportIteration)
        assert isinstance(restored.object_details_list, list)
        assert restored.object_details_list == [sample_object_details]


class TestNoOpReportWriter:
    def test_write_and_report_id(
        self, sample_report_metadata: ReportMetadata, sample_report_iteration: ReportIteration
    ) -> None:
        writer = NoOpReportWriter(sample_report_metadata)
        writer.write_iteration(sample_report_iteration)
        assert writer.report_id == sample_report_metadata.report_id


class TestFileReportWriter:
    def test_writes_summary_and_iteration(
        self,
        tmp_path: Path,
        sample_report_metadata: ReportMetadata,
        sample_report_iteration: ReportIteration,
    ) -> None:
        root = tmp_path
        report_dir = root / f"memalot_report_{sample_report_metadata.report_id}"
        report_dir.mkdir(parents=True, exist_ok=False)

        writer = FileReportWriter(report_dir, sample_report_metadata)

        # Summary files
        summary_path = report_dir / "summary.json"
        version_path = report_dir / "version"
        assert summary_path.exists()
        assert version_path.exists()
        with open(version_path, "r") as f:
            assert f.read().strip() == "1"
        with open(summary_path, "r") as f:
            data = json.load(f)
            restored = TypeAdapter(ReportMetadata).validate_python(data)
            assert restored == sample_report_metadata

        # Iteration
        writer.write_iteration(sample_report_iteration)
        iter_path = report_dir / f"iteration_report_{sample_report_iteration.iteration_number}.json"
        assert iter_path.exists()
        with open(iter_path, "r") as f:
            data = json.load(f)
            restored_iter = TypeAdapter(ReportIteration).validate_python(data)
            assert restored_iter == sample_report_iteration


class TestFileReportReader:
    @pytest.fixture(name="_temp_report_dir")
    def _temp_report_dir(
        self,
        tmp_path: Path,
        sample_report_metadata: ReportMetadata,
        sample_report_iteration_no_leaks: ReportIteration,
        sample_report_iteration: ReportIteration,
    ) -> Path:
        root = tmp_path
        report_dir = root / f"memalot_report_{sample_report_metadata.report_id}"
        report_dir.mkdir(parents=True, exist_ok=False)
        writer = FileReportWriter(report_dir, sample_report_metadata)
        # Write multiple iterations
        writer.write_iteration(sample_report_iteration_no_leaks)
        writer.write_iteration(sample_report_iteration)
        return root

    @pytest.fixture(name="_v1_reports_dir")
    def _v1_reports_dir(self) -> Path:
        """
        Fixture providing the path to test reports directory.
        """
        return Path(__file__).parent / "test_data" / "reports" / "v1"

    def test_get_report_summaries(
        self, _temp_report_dir: Path, sample_report_metadata: ReportMetadata
    ) -> None:
        reader = FileReportReader(report_directory=_temp_report_dir)
        summaries = reader.get_report_summaries()
        assert summaries == [
            ReportSummary(
                metadata=sample_report_metadata,
                iteration_count=2,
            )
        ]

    def test_get_full_report_latest_only(
        self,
        _temp_report_dir: Path,
        sample_report_metadata: ReportMetadata,
        sample_report_iteration: ReportIteration,
    ) -> None:
        reader = FileReportReader(report_directory=_temp_report_dir)
        full = reader.get_full_report(report_id=sample_report_metadata.report_id, num_iterations=1)
        assert full.iterations == [sample_report_iteration]

    def test_get_full_report_all_iterations(
        self,
        _temp_report_dir: Path,
        sample_report_metadata: ReportMetadata,
        sample_report_iteration_no_leaks: ReportIteration,
        sample_report_iteration: ReportIteration,
    ) -> None:
        reader = FileReportReader(report_directory=_temp_report_dir)
        full = reader.get_full_report(
            report_id=sample_report_metadata.report_id, num_iterations=100
        )
        assert full.iterations == [sample_report_iteration_no_leaks, sample_report_iteration]

    def test_get_full_report_not_found(self, _temp_report_dir: Path) -> None:
        reader = FileReportReader(report_directory=_temp_report_dir)
        with pytest.raises(ValueError):
            reader.get_full_report(report_id="does-not-exist", num_iterations=1)

    def test_read_v1_data(self, _v1_reports_dir: Path) -> None:
        """
        Tests backwards compatibility with v1 report data by ensuring that we can read it.

        Note: we don't actually check the resulting data, just that it can be read without error.
        """
        reader = FileReportReader(report_directory=_v1_reports_dir)
        for summary in reader.get_report_summaries():
            _ = reader.get_full_report(report_id=summary.metadata.report_id, num_iterations=100)


class TestGetReportWriter:
    """
    Tests for the `get_report_writer` function.
    """

    def test_get_report_writer(self, tmp_path: Path) -> None:
        report_directory = tmp_path / "custom_reports"
        options = Options(report_directory=report_directory, save_reports=True)

        report_writer = get_report_writer(options)

        report_dirs = list(report_directory.glob("memalot_report_*"))
        assert len(report_dirs) == 1
        actual_report_dir = report_dirs[0]

        summary_path = actual_report_dir / "summary.json"
        version_path = actual_report_dir / "version"
        assert summary_path.exists()
        assert version_path.exists()

        with open(version_path, "r") as f:
            assert f.read().strip() == "1"

        with open(summary_path, "r") as f:
            data = json.load(f)
            restored = TypeAdapter(ReportMetadata).validate_python(data)
            assert restored.report_id == report_writer.report_id
            assert restored.entrypoint is not None
            assert restored.arguments is not None
            assert restored.start_time is not None

    def test_get_report_writer_no_save(self) -> None:
        """
        Test that get_report_writer returns NoOpReportWriter when save_reports=False.
        """
        options = Options(save_reports=False)

        report_writer = get_report_writer(options)

        assert isinstance(report_writer, NoOpReportWriter)

    def test_get_report_writer_directory_collision(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """
        Test that get_report_writer handles directory name collisions correctly.
        """
        report_directory = tmp_path / "custom_reports"
        options = Options(report_directory=report_directory, save_reports=True)

        # Create a directory that will cause a collision
        collision_dir = report_directory / "memalot_report_collision-id"
        collision_dir.mkdir(parents=True)

        # Mock _generate_report_id to return the same ID twice, then a different one
        mock_generate_report_id = mocker.patch.object(
            reports,
            "_generate_report_id",
            side_effect=["collision-id", "collision-id", "unique-id"],
        )

        _ = get_report_writer(options)

        # Should have called _generate_report_id 3 times due to collision
        assert mock_generate_report_id.call_count == 3

        # Should create directory with the unique ID (plus the collision directory)
        report_dirs = list(report_directory.glob("memalot_report_*"))
        assert len(report_dirs) == 2  # collision-id and unique-id
        report_dir_names = {d.name for d in report_dirs}
        assert "memalot_report_collision-id" in report_dir_names
        assert "memalot_report_unique-id" in report_dir_names

    def test_get_report_writer_default_directory(self) -> None:
        """
        Test that get_report_writer uses the default report directory when report_directory=None.
        """
        options = Options(report_directory=None, save_reports=True)

        report_writer = get_report_writer(options)

        # The report writer should be a FileReportWriter
        assert isinstance(report_writer, FileReportWriter)
        assert report_writer.report_id is not None

        # Verify the report was written to the default directory
        default_report_root = Path.home() / ".memalot" / "reports"
        assert default_report_root.exists()

        report_dirs = list(default_report_root.glob(f"memalot_report_{report_writer.report_id}"))
        assert len(report_dirs) == 1
        actual_report_dir = report_dirs[0]

        summary_path = actual_report_dir / "summary.json"
        version_path = actual_report_dir / "version"
        assert summary_path.exists()
        assert version_path.exists()

        with open(version_path, "r") as f:
            assert f.read().strip() == "1"

        with open(summary_path, "r") as f:
            data = json.load(f)
            restored = TypeAdapter(ReportMetadata).validate_python(data)
            assert restored.report_id == report_writer.report_id


class TestFilterIterationByTypes:
    def test_filters_type_summaries_and_referrers(
        self, sample_report_iteration: ReportIteration
    ) -> None:
        # Two types present: collections.MyType and mymodule.OtherType
        filtered = filter_iteration_by_types(sample_report_iteration, ["OtherType"])
        assert len(filtered.leak_summary.type_summaries) == 1
        assert filtered.leak_summary.type_summaries[0].object_type.endswith("OtherType")
        assert len(filtered.object_details_list) == 0

    def test_no_filters_returns_same(self, sample_report_iteration: ReportIteration) -> None:
        same = filter_iteration_by_types(sample_report_iteration, [])
        assert same is sample_report_iteration


class TestGetMemoryUsageOutput:
    """
    Tests the `get_memory_usage_output` function.
    """

    def test_with_previous(self) -> None:
        """
        Test get_memory_usage_output with both previous and new MemoryUsage objects.
        """
        previous = MemalotMemoryUsage(
            current_rss_bytes=1000,
            peak_rss_bytes=1500,
            system_percent_used=10.0,
            iteration_number=1,
        )

        new = MemalotMemoryUsage(
            current_rss_bytes=1200,
            peak_rss_bytes=1800,
            system_percent_used=12.0,
            iteration_number=2,
        )

        result = get_memory_usage_output(previous, new)

        assert isinstance(result, MemoryUsageOutput)
        assert result.current_rss_bytes == 1200
        assert result.peak_rss_bytes == 1800
        assert result.system_percent_used == 12.0
        assert result.current_rss_diff == 200  # 1200 - 1000
        assert result.peak_rss_diff == 300  # 1800 - 1500
        assert result.diff_from_iteration == 1

    def test_without_previous(self) -> None:
        """
        Test get_memory_usage_output when previous is None.
        """
        new = MemalotMemoryUsage(
            current_rss_bytes=1200,
            peak_rss_bytes=1800,
            system_percent_used=12.0,
            iteration_number=2,
        )

        result = get_memory_usage_output(None, new)

        assert isinstance(result, MemoryUsageOutput)
        assert result.current_rss_bytes == 1200
        assert result.peak_rss_bytes == 1800
        assert result.system_percent_used == 12.0
        assert result.current_rss_diff is None
        assert result.peak_rss_diff is None
        assert result.diff_from_iteration is None

    def test_with_none_peak_rss(self) -> None:
        """
        Test get_memory_usage_output when peak_rss_bytes is None.
        """
        previous = MemalotMemoryUsage(
            current_rss_bytes=1000,
            peak_rss_bytes=None,
            system_percent_used=10.0,
            iteration_number=1,
        )

        new = MemalotMemoryUsage(
            current_rss_bytes=1200,
            peak_rss_bytes=None,
            system_percent_used=12.0,
            iteration_number=2,
        )

        result = get_memory_usage_output(previous, new)

        assert isinstance(result, MemoryUsageOutput)
        assert result.current_rss_bytes == 1200
        assert result.peak_rss_bytes is None
        assert result.system_percent_used == 12.0
        assert result.current_rss_diff == 200  # 1200 - 1000
        assert result.peak_rss_diff is None  # Both are None
        assert result.diff_from_iteration == 1


class TestPrintableReferrerNode:
    """
    Tests for the `_PrintableReferrerNode` class.
    """

    def test_str_with_is_leaf_and_is_cycle_true(self) -> None:
        """
        Test the __str__ method when both is_leaf and is_cycle are True.
        """
        node = PrintableReferrerNode(
            unique_id=1,
            name="test_node",
            object_id=12345,
            is_cycle_member=True,
            is_root=True,
        )

        result = str(node)
        assert "(cycle member)" in result
        assert "test_node" in result

    def test_str_with_is_leaf_true_is_cycle_false(self) -> None:
        """
        Test the __str__ method when is_leaf is True and is_cycle is False.
        """
        node = PrintableReferrerNode(
            unique_id=1,
            name="test_node",
            object_id=12345,
            is_cycle_member=False,
            is_root=True,
        )

        result = str(node)
        assert "(root)" in result
        assert "test_node" in result

    def test_str_with_is_leaf_false(self) -> None:
        """
        Test the __str__ method when is_leaf is False.
        """
        node = PrintableReferrerNode(
            unique_id=1,
            name="test_node",
            object_id=12345,
            is_cycle_member=False,
            is_root=False,
        )

        result = str(node)
        assert "(cycle)" not in result
        assert "(root)" not in result
        assert "test_node" in result


def _get_renderables_as_string(renderables: list[RenderableType]) -> str:
    console = Console(width=10000, theme=DEFAULT_RICH_THEME)
    with console.capture() as captured:
        for renderable in renderables:
            console.print(renderable)
    return captured.get()
