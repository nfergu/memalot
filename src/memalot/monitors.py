import gc
import logging
import time
from itertools import chain
from threading import Thread
from typing import Any, Callable, Iterable

from memalot.base import (
    MemalotCount,
    MemalotInt,
    MemalotList,
    MemalotObjectId,
    MemalotObjectIds,
    MemalotSet,
    ObjectGetter,
    ObjectSignature,
)
from memalot.interface import LeakMonitor, Stoppable
from memalot.memory import MemalotMemoryUsage
from memalot.objects import filter_objects
from memalot.options import Options
from memalot.output import OutputWriter
from memalot.report_generator import ReportGenerator
from memalot.reports import ReportWriter
from memalot.snapshots import (
    MemalotObjects,
    MemalotSnapshotManager,
    MemalotUsageSnapshot,
)

LOG = logging.getLogger(__name__)


class LeakMonitorImpl(LeakMonitor):
    """
    Context manager to monitor for memory leaks. The *second* time that the enclosed code
    is called, a summary of potential leaks will be printed to the console.
    """

    def __init__(
        self,
        writer: OutputWriter,
        report_writer: ReportWriter,
        warmup_calls: int,
        calls_per_report: int,
        options: Options,
        snapshot_manager: MemalotSnapshotManager,
        object_getter: ObjectGetter,
        function_name: str | None = None,
        report_generator: ReportGenerator | None = None,
    ) -> None:
        self._writer = writer
        self._warmup_calls = warmup_calls
        self._calls_per_report = calls_per_report
        self._options = options
        self._function_name = function_name
        self._report_writer = report_writer
        self._snapshot_manager = snapshot_manager
        self._report_generator = report_generator or ReportGenerator()
        self._object_getter = object_getter

        # Mutable state
        self._call_count: MemalotCount = MemalotCount(0)
        self._report_iteration: MemalotCount = MemalotCount(0)
        self._calls_since_previous_report: MemalotCount = MemalotCount(0)
        self._object_ids_from_first_call: MemalotObjectIds = MemalotObjectIds()
        self._adding_during_snapshot_creation = None

    def __enter__(self) -> None:
        """
        Enters the context manager.
        """
        self._call_count = MemalotCount(self._call_count + 1)
        if self._call_count > self._warmup_calls:
            self._calls_since_previous_report = MemalotCount(self._calls_since_previous_report + 1)
        # Only generate a snapshot after the warmup time, and if this is the first call
        # since the previous report. This snapshot contains *all* objects.
        if self._call_count > self._warmup_calls and self._calls_since_previous_report == 1:
            self._snapshot_manager.generate_new_snapshot(
                object_getter=self._object_getter,
                since_snapshot=None,
            )

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: Any
    ) -> None:
        """
        Exits the context manager.
        """
        if (
            self._call_count > self._warmup_calls
            and self._calls_per_report > 1
            and self._calls_since_previous_report == 1
        ):
            # If there are multiple calls per report and this is the *first* call since the
            # previous report, generate a new snapshot based on all the new objects since
            # the previous snapshot. We only want to consider objects created within the *first*
            # call after the previous report was generated. This is so that the calls_per_report
            # parameter is respected. In other words, the objects must be created in the first
            # call and live for calls_per_report calls.
            # Note: we don't generate a report in this case; only a snapshot.
            self._snapshot_manager.generate_new_snapshot(
                object_getter=self._object_getter,
                since_snapshot=self._snapshot_manager.most_recent_snapshot,
            )
        else:
            # In this case we generate a report. The specific objects in the report will vary
            # depending on whether this is a warmup iteration, and the value of _calls_per_report.
            if self._call_count < self._warmup_calls:
                # Still in warmup, no report yet
                return
            elif self._call_count == self._warmup_calls:
                # For warmup iterations, we don't include any objects in the report at all.
                report_objects = MemalotObjects([])
            elif self._call_count > self._warmup_calls and self._calls_per_report == 1:
                # If we are generating a report on every call, the objects to include in the report
                # are just those in the snapshot diff.
                report_objects = self._get_new_objects_since_snapshot()
            elif (
                self._call_count > self._warmup_calls
                and self._calls_per_report > 1
                and self._calls_since_previous_report >= self._calls_per_report
            ):
                # If we are generating a report after multiple calls, the objects we want to include
                # in the report are those that are in the current snapshot (this is the snapshot
                # that was generated on the first call after the previous report) and are still
                # alive.
                report_objects = self._get_objects_in_snapshot()
            else:  # pragma: no cover
                # This shouldn't happen
                raise ValueError(
                    f"Unexpected state. Call count: {self._call_count}; Report "
                    f"iteration: {self._report_iteration}; Calls since previous "
                    f"report: {self._calls_since_previous_report}; Warmup calls: "
                    f"{self._warmup_calls}; Calls per report: {self._calls_per_report}."
                )

            self._report_iteration = MemalotCount(self._report_iteration + 1)
            self._report_generator.generate_report(
                report_id=self._snapshot_manager.report_id,
                iteration_start_time=self._snapshot_manager.most_recent_snapshot_time,
                memory_usage_provider=self._snapshot_manager,
                objects=report_objects,
                output_writer=self._writer,
                report_writer=self._report_writer,
                options=self._options,
                iteration=self._report_iteration,
                excluded_from_referrers=[
                    id(self._object_ids_from_first_call),
                ],
                # Only generate a detailed report after the warmup time.
                detailed_report=self._call_count > self._warmup_calls,
                function_name=self._function_name,
            )
            self._snapshot_manager.clear_snapshots()
            self._adding_during_snapshot_creation = None
            self._calls_since_previous_report = MemalotCount(0)
            self._object_ids_from_first_call = MemalotObjectIds()

    def _get_objects_in_snapshot(self) -> MemalotObjects:
        assert self._snapshot_manager.most_recent_snapshot is not None
        objects_list = MemalotList()
        for obj in self._object_getter.get_objects():
            if self._snapshot_manager.most_recent_snapshot.is_in_snapshot(obj):
                objects_list.append(obj)
        report_objects = MemalotObjects(objects_list)
        return report_objects

    def _get_new_objects_since_snapshot(self) -> MemalotObjects:
        assert self._snapshot_manager.most_recent_snapshot is not None
        objects_list = MemalotList()
        for obj in self._object_getter.get_objects():
            if self._snapshot_manager.most_recent_snapshot.is_new_since_snapshot(obj):
                objects_list.append(obj)
        report_objects = MemalotObjects(objects_list)
        return report_objects


class StopMonitorThreadException(Exception):
    """
    Exception raised to stop the leak monitor thread.
    """

    pass


class LeakMonitorThread(Thread, Stoppable):
    """
    Thread to monitor for memory leaks.
    """

    def __init__(
        self,
        max_object_lifetime: float,
        warmup_time: float,
        writer: OutputWriter,
        report_writer: ReportWriter,
        options: Options,
        all_objects_manager: MemalotSnapshotManager,
        new_objects_manager: MemalotSnapshotManager,
        object_getter: ObjectGetter,
        report_generator: ReportGenerator | None = None,
        sleep_func: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(daemon=True)
        self._warmup_time = warmup_time
        self._max_object_lifetime = max_object_lifetime
        self._writer = writer
        self._report_writer = report_writer
        self._options = options
        self._all_objects_manager = all_objects_manager
        self._new_objects_manager = new_objects_manager
        self._report_generator = report_generator or ReportGenerator()
        self._object_getter = object_getter
        self._sleep_func = sleep_func

        # Mutable state
        self._report_iteration: MemalotCount = MemalotCount(0)
        self._should_stop: bool = False

    def stop(self) -> None:
        """
        Signals the thread to stop at the next safe opportunity.

        Note: this may take a while (`max_object_lifetime` seconds or longer).
        """
        self._should_stop = True

    def run(self) -> None:
        self._sleep_func(self._warmup_time)
        # Before we enter the main loop we need to take a snapshot of all objects
        # and then sleep for the maximum object lifetime. This ensures we can generate
        # a "new objects" snapshot with a baseline of all objects that exist at the
        # end of the warmup period.
        self._all_objects_manager.generate_new_snapshot(
            object_getter=self._object_getter,
            since_snapshot=None,
        )
        self._sleep_func(self._max_object_lifetime)
        while not self._should_stop:
            try:
                self._run_iteration()
            except StopMonitorThreadException:
                break
            except Exception:
                LOG.exception(
                    "Unexpected exception occurred in leak monitor thread. "
                    f"The thread will continue running after {self._max_object_lifetime} "
                    f"seconds..."
                )
                # Pause for a bit so we don't keep logging the above message continuously.
                self._sleep_func(self._max_object_lifetime)

    def _run_iteration(self) -> None:
        # If this is the warmup iteration, we don't include any objects in the report.
        self._report_iteration = MemalotCount(self._report_iteration + 1)
        if self._report_iteration == MemalotCount(1):
            report_objects = MemalotObjects([])
        else:
            report_objects = self._get_report_objects()
        # Generate a snapshot with only new objects in it. These are objects that have
        # been created since the previous "all objects" snapshot, which was at least
        # max_object_lifetime seconds ago.
        self._new_objects_manager.generate_new_snapshot(
            object_getter=self._object_getter,
            since_snapshot=self._all_objects_manager.most_recent_snapshot,
        )
        self._report_generator.generate_report(
            report_id=self._all_objects_manager.report_id,
            iteration_start_time=self._all_objects_manager.most_recent_snapshot_time,
            memory_usage_provider=self._all_objects_manager,
            objects=report_objects,
            output_writer=self._writer,
            report_writer=self._report_writer,
            options=self._options,
            iteration=self._report_iteration,
            excluded_from_referrers=[],
            # On the warmup iteration, do not generate a detailed report
            detailed_report=self._report_iteration > MemalotCount(1),
        )
        # Take a snapshot with all objects in it. We need to take this *after* the report
        # so that the next  "new objects" snapshot does not include objects created as part
        # of the report (it would be better if we didn't have to do this, as there's currently a
        # window in which leaks are not being detected).
        self._all_objects_manager.generate_new_snapshot(
            object_getter=self._object_getter,
            since_snapshot=None,
        )
        self._sleep_func(self._max_object_lifetime)
        gc.collect()

    def _get_report_objects(self) -> MemalotObjects:
        # The objects to include in the report are those that are in the new objects snapshot
        # and are still alive. This means they've lived for at least the maximum object
        # lifetime.
        assert self._new_objects_manager.most_recent_snapshot is not None
        # This can't be a list comprehension because in Python <= 3.11 this gets reported as a
        # leak.
        objects_list = MemalotList()
        for obj in self._object_getter.get_objects():
            if self._new_objects_manager.most_recent_snapshot.is_in_snapshot(obj):
                objects_list.append(obj)
        report_objects = MemalotObjects(objects_list)
        return report_objects


class FilteringObjectGetter(ObjectGetter):
    """
    Encapsulates the logic for getting filtered objects.
    """

    def __init__(
        self,
        get_objects_func: Callable[[int], list[Any]],
        options: Options,
        snapshot_managers: list[MemalotSnapshotManager],
    ) -> None:
        self._get_objects_func = get_objects_func
        self._options = options
        self._snapshot_managers = snapshot_managers

    def get_objects(self) -> list[Any]:
        """
        Get filtered objects by calling the underlying function and applying filters.
        """
        return filter_objects(
            objects=self._get_objects_func(self._options.max_untracked_search_depth),
            excluded_types=EXCLUDED_TYPES,
            included_type_names=self._options.included_type_names,
            excluded_type_names=self._options.excluded_type_names,
            include_object_ids=MemalotObjectIds(),
            # These objects may have been created since the previous iteration
            exclude_object_ids=self._get_ids(
                chain.from_iterable(
                    (
                        snapshot_manager.most_recent_snapshot,
                        (
                            snapshot_manager.most_recent_snapshot.__dict__
                            if snapshot_manager.most_recent_snapshot
                            else None
                        ),
                        snapshot_manager.most_recent_snapshot_time,
                    )
                    for snapshot_manager in self._snapshot_managers
                )
            ),
        )

    @staticmethod
    def _get_ids(objs: Iterable[Any | None]) -> MemalotObjectIds:
        """
        Gets the IDs of the objects in the list if they are not `None`.
        """
        return MemalotObjectIds(MemalotObjectId(id(obj)) for obj in objs if obj is not None)


EXCLUDED_TYPES = {
    MemalotSnapshotManager,
    MemalotUsageSnapshot,
    MemalotObjects,
    MemalotInt,
    MemalotCount,
    MemalotObjectId,
    MemalotObjectIds,
    MemalotList,
    MemalotSet,
    ObjectSignature,
    LeakMonitorImpl,
    LeakMonitorThread,
    MemalotMemoryUsage,
    ObjectGetter,
}
