from datetime import datetime, timezone

from memalot.base import CachingIterable, MemalotCount
from memalot.options import Options
from memalot.output import OutputWriter
from memalot.reports import (
    LeakSummary,
    MemoryUsageOutput,
    ObjectDetails,
    ReportIteration,
    ReportWriter,
    get_memory_usage_output,
)
from memalot.snapshots import MemalotObjects, MemoryUsageProvider


class ReportGenerator:
    """
    Generator of memory reports.
    """

    def generate_report(
        self,
        report_id: str,
        iteration_start_time: datetime | None,
        memory_usage_provider: MemoryUsageProvider,
        objects: MemalotObjects,
        output_writer: OutputWriter,
        report_writer: ReportWriter,
        options: Options,
        iteration: MemalotCount,
        excluded_from_referrers: list[int],
        detailed_report: bool,
        function_name: str | None = None,
    ) -> None:
        """
        Generates and writes a report based on the passed in objects and the contents
        of the snapshot manager.

        If `detailed_report` is `False`, then only a basic summary is generated.
        """
        self._write_report(
            report_id=report_id,
            iteration_start_time=iteration_start_time,
            memory_usage_provider=memory_usage_provider,
            objects=objects,
            output_writer=output_writer,
            report_writer=report_writer,
            options=options,
            iteration=iteration,
            excluded_from_referrers=[id(objects)] + excluded_from_referrers,
            detailed_report=detailed_report,
            function_name=function_name,
        )

    def _write_report(
        self,
        report_id: str,
        iteration_start_time: datetime | None,
        memory_usage_provider: MemoryUsageProvider,
        objects: MemalotObjects,
        output_writer: OutputWriter,
        report_writer: ReportWriter,
        options: Options,
        iteration: MemalotCount,
        excluded_from_referrers: list[int],
        detailed_report: bool,
        function_name: str | None = None,
    ) -> None:
        """
        Generates and writes a report.
        """
        report_time = datetime.now(timezone.utc)

        summary, referrers_iterable = self._collect_leak_report_data(
            objects=objects,
            options=options,
            iteration=iteration,
            excluded_from_referrers=excluded_from_referrers,
            detailed_report=detailed_report,
            function_name=function_name,
        )

        usage_output = self._collect_memory_usage_output(iteration, memory_usage_provider)

        report_iteration = ReportIteration(
            report_id=report_id,
            iteration_number=iteration,
            start_time=iteration_start_time or report_time,
            end_time=report_time,
            memory_usage=usage_output,
            leak_summary=summary,
            object_details_list=referrers_iterable,
        )

        output_writer.write(output=report_iteration)
        report_writer.write_iteration(iteration=report_iteration)

    def _collect_memory_usage_output(
        self, iteration: MemalotCount, memory_usage_provider: MemoryUsageProvider
    ) -> MemoryUsageOutput:
        old_usage, new_usage = memory_usage_provider.rotate_memory_usage(iteration=iteration)
        usage_output = get_memory_usage_output(previous=old_usage, new=new_usage)
        return usage_output

    def _collect_leak_report_data(
        self,
        objects: MemalotObjects,
        options: Options,
        iteration: MemalotCount,
        excluded_from_referrers: list[int],
        detailed_report: bool,
        function_name: str | None = None,
    ) -> tuple[LeakSummary, CachingIterable[ObjectDetails]]:
        """
        Collects report data without writing to output.
        Returns a tuple of (leak_summary, referrers_list).
        """
        if not detailed_report:
            return (
                LeakSummary(
                    iteration=iteration,
                    type_summaries=[],
                    max_types_in_summary=options.max_types_in_leak_summary,
                ),
                CachingIterable[ObjectDetails]([]),
            )

        if len(objects) == 0:
            return (
                LeakSummary(
                    iteration=iteration,
                    type_summaries=[],
                    max_types_in_summary=options.max_types_in_leak_summary,
                ),
                CachingIterable[ObjectDetails]([]),
            )

        summary = objects.get_leak_summary(iteration=iteration, options=options)

        referrers_iterable = CachingIterable(
            objects.generate_object_details(
                excluded_from_referrers=[id(objects)] + excluded_from_referrers,
                options=options,
                function_name=function_name,
            )
        )

        return summary, referrers_iterable
