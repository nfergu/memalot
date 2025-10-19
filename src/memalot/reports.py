import json
import random
import string
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, List

from pydantic import TypeAdapter, field_serializer
from pydantic.dataclasses import dataclass
from rich import box
from rich.console import NewLine as RichNewLine
from rich.console import RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from memalot import networkx_copy
from memalot.base import ApproximateSize, CachingIterable, ReferrerGraph
from memalot.memory import MemalotMemoryUsage
from memalot.options import Options
from memalot.output import NewBlock, Output
from memalot.themes import (
    COUNT,
    END_OF_SECTION_TEXT,
    HEADING_BORDER,
    MEMORY_DECREASE,
    MEMORY_INCREASE,
    OBJECT_DETAILS_TITLE,
    SIZE_TITLE,
    STRING_REPR_TITLE,
    TABLE_BORDER,
    TABLE_HEADER,
    TABLE_TITLE,
    TITLE,
)
from memalot.utils import as_mib, as_mib_sf, convert_graph_nodes_to_printable, format_bytes

_CURRENT_FILE_VERSION = 1
"""
The current file format version. Used when writing files.
"""

_REPORT_DIR_PREFIX = "memalot_report_"
"""
The prefix of the report directory name.
"""

_ITERATION_REPORT_PREFIX = "iteration_report_"
"""
The prefix of the iteration report file name.
"""

_SUMMARY_FILE_NAME = "summary.json"
"""
The name of the summary file.
"""


@dataclass
class ReportMetadata:
    """
    Metadata relating to a single report. This is generated at the start of execution.
    """

    report_id: str
    """
    A unique ID of the report.
    """
    entrypoint: str
    """
    The entrypoint of the report. This is the main function that was used to start the
    program that was analyzed.
    """
    arguments: List[str]
    """
    The arguments that were used to start the program that was analyzed.
    """
    start_time: datetime
    """
    The start time of the report.
    """


@dataclass
class ReportSummary:
    """
    A summary of a single report, generated at the end of execution.
    """

    metadata: ReportMetadata
    """
    Metadata about the report.
    """

    iteration_count: int
    """
    The number of iterations that were run. This can be used to, for example, get the most
    recent iteration of the report, since iteration numbers are sequential.
    """


@dataclass
class MemoryUsageOutput(Output):
    """
    An `Output` object representing the memory usage.
    """

    current_rss_bytes: int
    """
    The current resident set size (RSS) in bytes.
    """

    system_percent_used: float
    """
    The percent of total physical system memory used.
    """

    peak_rss_bytes: int | None = None
    """
    The peak resident set size (RSS) in bytes. This is `None` if not supported on the
    current platform.
    """

    current_rss_diff: int | None = None
    """
    The difference in RSS between the current and previous usage. This is `None` if
    previous usage is not provided.
    """

    peak_rss_diff: int | None = None
    """
    The difference in RSS between the peak and previous peak. This is `None` if
    previous usage is not provided.
    """

    diff_from_iteration: int | None = None
    """
    The iteration number that the difference was calculated from. This is `None` if
    previous usage is not provided.
    """

    def to_renderables(self) -> list[RenderableType]:
        parts = [f"[{TITLE}]Memory used[/{TITLE}]: {as_mib(self.current_rss_bytes)}"]
        if self.current_rss_diff is not None:
            sign = "+" if self.current_rss_diff >= 0 else ""
            tag = MEMORY_INCREASE if self.current_rss_diff > 0 else MEMORY_DECREASE
            parts.append(f" ([{tag}]{sign}[/{tag}]{as_mib_sf(self.current_rss_diff, tag=tag)})")
        parts.append(f" / {self.system_percent_used:.2f}% sys")
        if self.peak_rss_bytes is not None:
            parts.append("\n")
            parts.append(f"[{TITLE}]Peak memory[/{TITLE}]: {as_mib(self.peak_rss_bytes)}")
            if self.peak_rss_diff is not None:
                sign = "+" if self.peak_rss_diff >= 0 else ""
                tag = MEMORY_INCREASE if self.peak_rss_diff > 0 else MEMORY_DECREASE
                parts.append(f" ([{tag}]{sign}[/{tag}]{as_mib_sf(self.peak_rss_diff, tag=tag)})")
        return ["".join(parts)]


@dataclass
class TypeSummary:
    """
    A summary of a specific type of object.
    """

    object_type: str
    """
    The name of the type of object that was found to be leaking.
    """
    count: int
    """
    The number of objects of this type that were found to be leaking.
    """
    shallow_size_bytes: ApproximateSize | None = None
    """
    The total shallow size of all objects of this type that were found to be leaking.

    If the total size could not be determined, then the `upper_bound_known` field of
    `deep_size_bytes` will be `False`.

    This may be None if the shallow size was not computed.
    """


@dataclass
class LeakSummary(Output):
    """
    A summary of potential leaks.
    """

    iteration: int
    """
    The iteration that this summary is for
    """

    type_summaries: list[TypeSummary]
    """
    A list of summaries for each type of object that was found to be leaking.
    """

    max_types_in_summary: int | None = None
    """
    The maximum number of types in the summary. This may be `None` in older versions.
    """

    def to_renderables(self) -> list[RenderableType]:
        table = Table(
            title=f"Possible New Leaks (iteration {self.iteration})",
            box=box.ROUNDED,
            header_style=TABLE_HEADER,
            title_style=TABLE_TITLE,
            border_style=TABLE_BORDER,
        )
        table.add_column("Object Type", justify="left", no_wrap=False, overflow="fold")
        table.add_column("Count", justify="right", no_wrap=True)
        show_sizes = any(summary.shallow_size_bytes is not None for summary in self.type_summaries)
        if show_sizes:
            table.add_column("Shallow size (estimated)", justify="right", no_wrap=True)
        for summary in self.type_summaries:
            if summary.shallow_size_bytes is not None:
                byte_string = format_bytes(summary.shallow_size_bytes.approx_size)
                formatted_bytes = f"{summary.shallow_size_bytes.prefix}{byte_string}"
            else:
                formatted_bytes = "Unknown"
            row_data = [
                summary.object_type,
                f"[{COUNT}]{summary.count}[/{COUNT}]",
            ]
            if show_sizes:
                row_data.append(formatted_bytes)
            table.add_row(*row_data)
        renderables: list[RenderableType] = [table]
        if (
            self.max_types_in_summary is not None
            and len(self.type_summaries) >= self.max_types_in_summary
        ):
            renderables.append(f"(truncated to {self.max_types_in_summary} entries)")
        return renderables


@dataclass
class ObjectDetails(Output):
    """
    Represents details of a specific object, including its referrers.
    """

    object_type_name: str
    object_id: int
    object_str: str
    deep_size_bytes: ApproximateSize
    referrer_graph: ReferrerGraph | None = None
    referrers_checked: bool = True

    def to_renderables(self) -> list[RenderableType]:
        title = (
            f"[{OBJECT_DETAILS_TITLE}]Details for {self.object_type_name} (id="
            f"{self.object_id})[/{OBJECT_DETAILS_TITLE}]"
        )
        size_str = (
            f"[{OBJECT_DETAILS_TITLE}]{self.deep_size_bytes.prefix}[/{OBJECT_DETAILS_TITLE}]"
            f"{format_bytes(self.deep_size_bytes.approx_size, tag=OBJECT_DETAILS_TITLE)}"
        )
        size = f"[{SIZE_TITLE}]Deep size (estimated):[/{SIZE_TITLE}] {size_str}"
        if self.referrer_graph is None or len(self.referrer_graph) == 0:
            if self.referrers_checked:
                referrer_graph = "No referrers found"
            else:
                referrer_graph = (
                    "Not checking referrers. Set the check_referrers option to "
                    "True to turn on referrer checking"
                )
        else:
            # We avoid using Rich's tree here for now, as it seems to have issues
            # with wrapping and cropping. See https://github.com/Textualize/rich/issues/3785.
            printable_graph = convert_graph_nodes_to_printable(self.referrer_graph)
            network_text = networkx_copy.generate_network_text(
                printable_graph, override_glyphs=networkx_copy.UtfUndirectedGlyphs
            )  # type: ignore
            referrer_graph = "\n" + "\n".join(line for line in network_text)
        return [
            Panel(
                title,
                box=box.ASCII,
                expand=False,
                padding=0,
                border_style=HEADING_BORDER,
            ),
            RichNewLine(),
            size,
            RichNewLine(),
            referrer_graph,
            RichNewLine(),
            f"[{STRING_REPR_TITLE}]String representation:[/{STRING_REPR_TITLE}]",
            self.object_str,
        ]

    def __eq__(self, other: object) -> bool:
        # noinspection PyProtocol
        assert isinstance(other, ObjectDetails)
        # noinspection PyUnresolvedReferences
        return (
            self.object_type_name == other.object_type_name
            and self.object_id == other.object_id
            and self.deep_size_bytes == other.deep_size_bytes
            and self.referrers_checked == other.referrers_checked
            and self.referrer_graph == other.referrer_graph
        )

    def __hash__(self) -> int:
        raise NotImplementedError("Hashing ObjectDetails is not supported")


@dataclass(config={"arbitrary_types_allowed": True})
class ReportIteration(Output):
    """
    A single iteration of a report.
    """

    report_id: str
    """
    The ID of the report that this iteration belongs to.
    """
    iteration_number: int
    """
    The iteration number of the report.
    """
    start_time: datetime
    """
    The start time of the iteration.
    """
    end_time: datetime
    """
    The end time of the iteration.
    """
    memory_usage: MemoryUsageOutput
    """
    The memory usage of the iteration.
    """
    leak_summary: LeakSummary
    """
    A summary of the leaks found in this iteration.
    """
    object_details_list: CachingIterable[ObjectDetails] | list[ObjectDetails]
    """
    A list of object details for each potential leak.
    """

    def to_renderables(self) -> Generator[RenderableType, None, None]:
        """
        Converts this report iteration to a generator of rich renderable objects.

        This yields all the individual renderable elements that make up the report
        for this iteration, in the order they should be displayed.
        """
        yield RichNewLine()
        yield RichNewLine()

        report_id_text = f"Report ID: {self.report_id}"

        panel_text = Text.from_markup(
            report_id_text + "\n" + str(self.memory_usage.to_renderables()[0]), justify="center"
        )
        yield Panel(
            panel_text,
            expand=False,
            padding=1,
            border_style=HEADING_BORDER,
            title=f"[bold]Memalot Report[/bold] (iteration {self.iteration_number})",
            title_align="center",
        )

        yield NewBlock("")

        yield RichNewLine()

        if self.leak_summary.type_summaries:
            for renderable in self.leak_summary.to_renderables():
                yield renderable
            yield RichNewLine()
        else:
            if self.iteration_number == 1:
                yield (
                    "This is a warmup iteration. Reports will be available from the next iteration."
                )
            else:
                yield "No leaks found during this iteration."
            yield RichNewLine()

        yield NewBlock("")

        if self.leak_summary.type_summaries:
            yield "Memalot is generating object details. This may take some time..."
            yield NewBlock("")

        for object_details in self.object_details_list:
            for renderable in object_details.to_renderables():
                yield renderable
            yield RichNewLine()
            yield NewBlock("")

        yield (
            f"[{END_OF_SECTION_TEXT}]End of Memalot Report "
            f"(iteration {self.iteration_number})[/{END_OF_SECTION_TEXT}]"
        )

    @field_serializer("object_details_list")
    def serialize_referrer_graph(
        self, referrers: CachingIterable[ObjectDetails] | list[ObjectDetails]
    ) -> list[ObjectDetails]:
        if isinstance(referrers, CachingIterable):
            return list(referrers)
        else:
            return referrers


@dataclass
class FullReport:
    """
    A full report.
    """

    summary: ReportSummary
    """
    A summary of the report.
    """
    iterations: list[ReportIteration]
    """
    A list of all iterations of the report. Each iteration contains information about the
    memory usage and potential leaks at that point in time.
    """


class ReportWriter(ABC):
    """
    A writer that writes report data to a sink. This is typically a file.
    """

    @abstractmethod
    def write_iteration(self, iteration: ReportIteration) -> None:  # pragma: no cover
        pass

    @property
    @abstractmethod
    def report_id(self) -> str:  # pragma: no cover
        pass


class ReportReader(ABC):
    """
    A reader that reads report data from a source. This is typically a file.
    """

    @abstractmethod
    def get_report_summaries(self) -> list[ReportSummary]:
        """
        Gets the summaries of all reports in the given directory. If no directory is
        provided, the default report root is used.

        If the directory does not exist, an empty list is returned.
        """
        pass  # pragma: no cover

    @abstractmethod
    def get_full_report(self, report_id: str, num_iterations: int) -> FullReport:
        """
        Gets the full report for a given report ID. The number of iterations to return
        is specified by the `num_iterations` parameter. The most recent `num_iterations`
        are returned, ordered by iteration number.

        If the report does not exist, a `ValueError` is raised.
        """
        pass  # pragma: no cover


class NoOpReportWriter(ReportWriter):
    """
    A writer that does nothing.
    """

    def __init__(self, report_summary: ReportMetadata) -> None:
        self._report_id = report_summary.report_id

    def write_iteration(self, iteration: ReportIteration) -> None:
        # Do nothing
        pass

    @property
    def report_id(self) -> str:
        return self._report_id


class FileReportWriter(ReportWriter):
    """
    A writer that writes report data to a file within the report directory. Each
    iteration is written to a separate file suffixed with the iteration number.

    The writer is initialized with the path to the report directory and the report
    summary, which is written to a file named `summary.json`.
    """

    def __init__(self, report_directory: Path, report_summary: ReportMetadata) -> None:
        self._report_directory = report_directory
        self._report_summary = report_summary
        summary_file = self._report_directory / _SUMMARY_FILE_NAME
        with open(summary_file, "wb") as f:
            f.write(TypeAdapter(type(self._report_summary)).dump_json(self._report_summary))
        version_file = self._report_directory / "version"
        with open(version_file, "w") as f:
            f.write(str(_CURRENT_FILE_VERSION))

    def write_iteration(self, iteration: ReportIteration) -> None:
        iteration_file = (
            self._report_directory / f"{_ITERATION_REPORT_PREFIX}{iteration.iteration_number}.json"
        )
        with open(iteration_file, "wb") as f:
            f.write(TypeAdapter(type(iteration)).dump_json(iteration))

    @property
    def report_id(self) -> str:
        return self._report_summary.report_id


class FileReportReader(ReportReader):
    def __init__(self, report_directory: Path | None = None) -> None:
        self._report_root = _get_report_root(
            override=str(report_directory) if report_directory else None
        )

    def get_report_summaries(self) -> List[ReportSummary]:
        """
        Gets the summaries of all reports in the given directory. If no directory is
        provided, the default report root is used.

        If the directory does not exist, an empty list is returned.
        """
        if not self._report_root.exists():
            return []
        else:
            summary_list = []
            # This is not a list comprehension because otherwise it shows up on leak reports
            # in Python versions < 3.12.
            report_dirs = []
            for item in self._report_root.iterdir():
                if item.is_dir() and item.name.startswith(_REPORT_DIR_PREFIX):
                    report_dirs.append(item)
            for report_dir in report_dirs:
                summary_path = report_dir / _SUMMARY_FILE_NAME
                if summary_path.exists():
                    with open(summary_path, "r") as f:
                        data = json.load(f)
                        summary_start: ReportMetadata = TypeAdapter(ReportMetadata).validate_python(
                            data
                        )
                    iteration_files = list(report_dir.glob(f"{_ITERATION_REPORT_PREFIX}*.json"))
                    iteration_count = len(iteration_files)
                    summary = ReportSummary(
                        metadata=summary_start,
                        iteration_count=iteration_count,
                    )
                    summary_list.append(summary)
            return summary_list

    def get_full_report(self, report_id: str, num_iterations: int) -> FullReport:
        report_dir = self._report_root / f"{_REPORT_DIR_PREFIX}{report_id}"
        if not report_dir.exists():
            raise ValueError(f"Report with ID {report_id} not found.")

        summary_path = report_dir / _SUMMARY_FILE_NAME
        with open(summary_path, "r") as f:
            data = json.load(f)
            summary_start = TypeAdapter(ReportMetadata).validate_python(data)

        iteration_files = sorted(
            report_dir.glob(f"{_ITERATION_REPORT_PREFIX}*.json"),
            key=lambda p: int(p.stem.split(f"{_ITERATION_REPORT_PREFIX}")[1]),
            reverse=True,
        )

        iterations = []
        for iteration_file in iteration_files[:num_iterations]:
            with open(iteration_file, "r") as f:
                data = json.load(f)
                iteration = TypeAdapter(ReportIteration).validate_python(data)
                iterations.append(iteration)

        iterations.sort(key=lambda i: i.iteration_number)

        summary = ReportSummary(
            metadata=summary_start,
            iteration_count=len(iteration_files),
        )

        return FullReport(summary=summary, iterations=iterations)


def get_report_writer(options: Options) -> ReportWriter:
    """
    Gets an report writer for the given options.

    If the report directory is not specified, the default report root is used.
    The report root is a directory in the user's home directory called `.memalot/reports`.
    """
    start_time = datetime.now(timezone.utc)
    report_id = _generate_report_id(start_time)

    report_summary = ReportMetadata(
        report_id=report_id,
        entrypoint=_get_entrypoint(),
        arguments=_get_arguments(),
        start_time=start_time,
    )

    if options.save_reports:
        report_root = _get_report_root(
            override=str(options.report_directory) if options.report_directory else None
        )

        report_dir_name = f"{_REPORT_DIR_PREFIX}{report_id}"
        report_directory = report_root / report_dir_name
        while report_directory.exists():
            report_id = _generate_report_id(start_time)
            report_dir_name = f"{_REPORT_DIR_PREFIX}{report_id}"
            report_directory = report_root / report_dir_name
        report_directory.mkdir(parents=True, exist_ok=False)
        report_writer: ReportWriter = FileReportWriter(report_directory, report_summary)
    else:
        report_writer = NoOpReportWriter(report_summary)
    return report_writer


def filter_iteration_by_types(
    iteration: ReportIteration, filter_types: List[str]
) -> ReportIteration:
    """
    Filter a report iteration to only include objects whose types contain any of
    the filter strings.
    """
    if not filter_types:
        return iteration

    filtered_type_summaries = [
        ts
        for ts in iteration.leak_summary.type_summaries
        if any(filter_type.lower() in ts.object_type.lower() for filter_type in filter_types)
    ]

    filtered_referrers = [
        obj
        for obj in iteration.object_details_list
        if any(filter_type.lower() in obj.object_type_name.lower() for filter_type in filter_types)
    ]

    filtered_leak_summary = LeakSummary(
        iteration=iteration.leak_summary.iteration,
        type_summaries=filtered_type_summaries,
        max_types_in_summary=iteration.leak_summary.max_types_in_summary,
    )

    return ReportIteration(
        report_id=iteration.report_id,
        iteration_number=iteration.iteration_number,
        start_time=iteration.start_time,
        end_time=iteration.end_time,
        memory_usage=iteration.memory_usage,
        leak_summary=filtered_leak_summary,
        object_details_list=filtered_referrers,
    )


def get_memory_usage_output(
    previous: MemalotMemoryUsage | None, new: MemalotMemoryUsage
) -> MemoryUsageOutput:
    """
    Gets a `Output` object representing the memory usage. This includes the difference
    between the current and previous usage if the previous usage is provided.
    """
    return MemoryUsageOutput(
        current_rss_bytes=new.current_rss_bytes,
        peak_rss_bytes=new.peak_rss_bytes,
        current_rss_diff=new.current_rss_bytes - previous.current_rss_bytes if previous else None,
        system_percent_used=new.system_percent_used,
        peak_rss_diff=(
            new.peak_rss_bytes - previous.peak_rss_bytes
            if previous and previous.peak_rss_bytes is not None and new.peak_rss_bytes is not None
            else None
        ),
        diff_from_iteration=previous.iteration_number if previous else None,
    )


def get_report_reader(report_directory: Path | None = None) -> ReportReader:
    """
    Gets a report reader for the given report directory. If no directory is provided,
    the default report root is used.
    """
    return FileReportReader(report_directory=report_directory)


def _get_report_root(override: str | None) -> Path:
    """
    Gets the root directory for reports.
    """
    if override is None:
        report_root = _get_default_report_root()
    else:
        report_root = Path(override)
    return report_root


def _get_default_report_root() -> Path:
    """
    Gets the default report root.
    """
    return Path.home() / ".memalot" / "reports"


def _generate_report_id(start_time: datetime) -> str:
    """
    Generates a short, human-friendly, ID with a high probability of uniqueness
    (but the ID is not guaranteed to be unique, so needs to be checked).
    """
    chars = string.ascii_lowercase + string.digits
    first_part = "".join(random.choice(chars) for _ in range(4))
    second_part = "".join(random.choice(chars) for _ in range(4))
    return f"{first_part}-{second_part}"


def _get_entrypoint() -> str:
    """
    Gets the entrypoint of the report.
    """
    return sys.argv[0]


def _get_arguments() -> list[str]:
    """
    Gets the arguments of the report.
    """
    return sys.argv[1:]
