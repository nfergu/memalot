from typing import Any, Callable
from unittest.mock import ANY, MagicMock, call

import pytest

from memalot.base import MemalotCount, MemalotObjectIds, ObjectGetter
from memalot.monitors import (
    FilteringObjectGetter,
    LeakMonitorImpl,
    LeakMonitorThread,
    StopMonitorThreadException,
)
from memalot.options import Options
from memalot.output import OutputWriter
from memalot.report_generator import ReportGenerator
from memalot.reports import ReportWriter
from memalot.snapshots import MemalotObjects, MemalotSnapshotManager, MemalotUsageSnapshot
from tests.utils_for_testing import create_mock, wait_for_assertion


@pytest.fixture(name="mock_output_writer")
def _mock_output_writer() -> MagicMock:
    """
    Mock OutputWriter for testing.
    """
    return create_mock(spec=OutputWriter)


@pytest.fixture(name="mock_report_writer")
def _mock_report_writer() -> MagicMock:
    """
    Mock ReportWriter for testing.
    """
    return create_mock(spec=ReportWriter)


@pytest.fixture(name="mock_snapshot_manager")
def _mock_snapshot_manager() -> MagicMock:
    """
    Mock MemalotSnapshotManager for testing.
    """
    return create_mock(spec=MemalotSnapshotManager)


@pytest.fixture(name="mock_all_objects_manager")
def _mock_all_objects_manager() -> MagicMock:
    """
    Mock MemalotSnapshotManager for all objects tracking.
    """
    return create_mock(spec=MemalotSnapshotManager)


@pytest.fixture(name="mock_new_objects_manager")
def _mock_new_objects_manager() -> MagicMock:
    """
    Mock MemalotSnapshotManager for new objects tracking.
    """
    return create_mock(spec=MemalotSnapshotManager)


@pytest.fixture(name="mock_report_generator")
def _mock_report_generator() -> MagicMock:
    """
    Mock ReportGenerator for testing.
    """
    return create_mock(spec=ReportGenerator)


@pytest.fixture(name="mock_get_objects_func")
def _mock_get_objects_func() -> MagicMock:
    """
    Mock get_objects function for testing.
    """
    return create_mock(spec=Callable[[int], list[Any]])


@pytest.fixture(name="mock_object_getter")
def _mock_object_getter() -> MagicMock:
    """
    Mock ObjectGetter for testing.
    """
    return create_mock(spec=ObjectGetter)


@pytest.fixture(name="test_options")
def _test_options() -> Options:
    """
    Options instance for testing.
    """
    return Options()


class TestLeakMonitorImpl:
    def test_report_generated(
        self,
        mock_output_writer: MagicMock,
        mock_report_writer: MagicMock,
        mock_snapshot_manager: MagicMock,
        mock_report_generator: MagicMock,
        mock_object_getter: MagicMock,
        test_options: Options,
    ) -> None:
        """
        Tests that a report is generated when the leak monitor is called as a context manager,
        and that collaborators are called with expected arguments.
        """
        objects_on_exit = ["exit1", "exit2"]
        # The mock object getter is called once at exit time to check for new objects
        mock_object_getter.get_objects.return_value = objects_on_exit

        # Mock the snapshot's is_new_since_snapshot to return True for all objects
        mock_snapshot_manager.most_recent_snapshot.is_new_since_snapshot.return_value = True

        leak_monitor = LeakMonitorImpl(
            writer=mock_output_writer,
            report_writer=mock_report_writer,
            warmup_calls=0,
            calls_per_report=1,
            options=test_options,
            snapshot_manager=mock_snapshot_manager,
            report_generator=mock_report_generator,
            object_getter=mock_object_getter,
        )
        with leak_monitor:
            pass

        # The object getter is called once when checking for new objects
        mock_object_getter.get_objects.assert_called_once_with()

        # Check that generate_new_snapshot was called with the object getter
        mock_snapshot_manager.generate_new_snapshot.assert_called_once_with(
            object_getter=mock_object_getter,
            since_snapshot=None,
        )

        # Check that generate_report was called with correct parameters
        mock_report_generator.generate_report.assert_called_once_with(
            report_id=mock_snapshot_manager.report_id,
            iteration_start_time=mock_snapshot_manager.most_recent_snapshot_time,
            memory_usage_provider=mock_snapshot_manager,
            objects=MemalotObjects(objects_on_exit),
            output_writer=mock_output_writer,
            report_writer=mock_report_writer,
            options=test_options,
            iteration=MemalotCount(1),
            detailed_report=True,
            function_name=None,
            excluded_from_referrers=ANY,  # Dynamic object IDs, but should have 1 element
        )
        # Verify excluded_from_referrers has exactly one element
        assert (
            len(mock_report_generator.generate_report.call_args.kwargs["excluded_from_referrers"])
            == 1
        )

        mock_snapshot_manager.clear_snapshots.assert_called_once_with()

    def test_baseline_report_generated_on_last_warmup_call(
        self,
        mock_output_writer: MagicMock,
        mock_report_writer: MagicMock,
        mock_snapshot_manager: MagicMock,
        mock_report_generator: MagicMock,
        mock_get_objects_func: MagicMock,
        test_options: Options,
    ) -> None:
        """
        When warmup_calls > 0, a baseline report is generated at the end of warmup without
        a snapshot.
        """
        objects_on_exit = [object(), object()]
        mock_get_objects_func.side_effect = [objects_on_exit]

        object_getter = FilteringObjectGetter(
            get_objects_func=mock_get_objects_func,
            options=test_options,
            snapshot_managers=[mock_snapshot_manager],
        )

        leak_monitor = LeakMonitorImpl(
            writer=mock_output_writer,
            report_writer=mock_report_writer,
            warmup_calls=1,
            calls_per_report=1,
            options=test_options,
            snapshot_manager=mock_snapshot_manager,
            report_generator=mock_report_generator,
            object_getter=object_getter,
        )

        with leak_monitor:
            pass

        mock_snapshot_manager.generate_new_snapshot.assert_not_called()
        mock_report_generator.generate_report.assert_called_once()

        kwargs = mock_report_generator.generate_report.call_args.kwargs
        assert kwargs["objects"] == MemalotObjects([])
        assert kwargs["excluded_from_referrers"] == [id(MemalotObjectIds())]

        mock_snapshot_manager.clear_snapshots.assert_called_once()

    def test_calls_per_report_of_two_delays_report_until_second_call(
        self,
        mock_output_writer: MagicMock,
        mock_report_writer: MagicMock,
        mock_snapshot_manager: MagicMock,
        mock_report_generator: MagicMock,
        mock_object_getter: MagicMock,
        test_options: Options,
    ) -> None:
        """
        With calls_per_report=2 and no warmup, the first call creates a snapshot and the
        second call generates the report using objects from the snapshot.
        """
        objects_exit_1 = ["exit1", "exit2"]
        objects_exit_2 = ["exit2"]
        # The object getter is called once, at the second exit, so return exit2 objects
        mock_object_getter.get_objects.return_value = objects_exit_2

        # Mock the snapshot's is_in_snapshot method
        # Objects from exit_1 should be considered as being in the snapshot
        mock_snapshot_manager.most_recent_snapshot.is_in_snapshot.side_effect = (
            lambda obj: obj in objects_exit_1
        )

        leak_monitor = LeakMonitorImpl(
            writer=mock_output_writer,
            report_writer=mock_report_writer,
            warmup_calls=0,
            calls_per_report=2,
            options=test_options,
            snapshot_manager=mock_snapshot_manager,
            report_generator=mock_report_generator,
            object_getter=mock_object_getter,
        )

        with leak_monitor:
            pass
        assert mock_report_generator.generate_report.call_count == 0

        with leak_monitor:
            pass
        assert mock_report_generator.generate_report.call_count == 1

        # Check that generate_report was called with correct parameters
        # This should be the objects from exit_1 that are still alive at exit_2
        expected_objects = MemalotObjects(["exit2"])
        mock_report_generator.generate_report.assert_called_once_with(
            report_id=mock_snapshot_manager.report_id,
            iteration_start_time=mock_snapshot_manager.most_recent_snapshot_time,
            memory_usage_provider=mock_snapshot_manager,
            objects=expected_objects,
            output_writer=mock_output_writer,
            report_writer=mock_report_writer,
            options=test_options,
            iteration=MemalotCount(1),
            detailed_report=True,
            function_name=None,
            excluded_from_referrers=ANY,  # Dynamic object IDs, but should have 1 element
        )
        # Verify excluded_from_referrers has exactly one element
        assert (
            len(mock_report_generator.generate_report.call_args.kwargs["excluded_from_referrers"])
            == 1
        )

        # Should have generated two snapshots:
        # 1. On first __enter__ with since_snapshot=None (at start of first call)
        # 2. On first __exit__ with since_snapshot=<snapshot> (after first call, before report)
        assert mock_snapshot_manager.generate_new_snapshot.call_count == 2
        first_call = mock_snapshot_manager.generate_new_snapshot.call_args_list[0]
        second_call = mock_snapshot_manager.generate_new_snapshot.call_args_list[1]

        # Both calls pass the object getter directly
        assert first_call.kwargs["object_getter"] is mock_object_getter
        assert first_call.kwargs["since_snapshot"] is None
        assert second_call.kwargs["object_getter"] is mock_object_getter
        assert second_call.kwargs["since_snapshot"] == mock_snapshot_manager.most_recent_snapshot

    def test_multiple_reports_reset_state_between_iterations(
        self,
        mock_output_writer: MagicMock,
        mock_report_writer: MagicMock,
        mock_snapshot_manager: MagicMock,
        mock_report_generator: MagicMock,
        mock_get_objects_func: MagicMock,
        test_options: Options,
    ) -> None:
        """
        With calls_per_report=1 and no warmup, each call generates a report and state resets
        on each report.
        """
        exit_1 = ["exit1", "exit2"]
        exit_2 = ["exit3", "exit4"]
        mock_get_objects_func.side_effect = [exit_1, exit_2]

        # Mock the snapshot's is_new_since_snapshot to return True for all objects
        mock_snapshot_manager.most_recent_snapshot.is_new_since_snapshot.return_value = True

        object_getter = FilteringObjectGetter(
            get_objects_func=mock_get_objects_func,
            options=test_options,
            snapshot_managers=[mock_snapshot_manager],
        )

        leak_monitor = LeakMonitorImpl(
            writer=mock_output_writer,
            report_writer=mock_report_writer,
            warmup_calls=0,
            calls_per_report=1,
            options=test_options,
            snapshot_manager=mock_snapshot_manager,
            report_generator=mock_report_generator,
            object_getter=object_getter,
        )

        with leak_monitor:
            pass
        with leak_monitor:
            pass

        assert mock_report_generator.generate_report.call_count == 2
        # Check all parameters for both calls
        mock_report_generator.generate_report.assert_has_calls(
            [
                call(
                    report_id=mock_snapshot_manager.report_id,
                    iteration_start_time=mock_snapshot_manager.most_recent_snapshot_time,
                    memory_usage_provider=mock_snapshot_manager,
                    objects=MemalotObjects(exit_1),
                    output_writer=mock_output_writer,
                    report_writer=mock_report_writer,
                    options=test_options,
                    iteration=MemalotCount(1),
                    detailed_report=True,
                    function_name=None,
                    excluded_from_referrers=ANY,  # Dynamic object IDs, but should have 1 element
                ),
                call(
                    report_id=mock_snapshot_manager.report_id,
                    iteration_start_time=mock_snapshot_manager.most_recent_snapshot_time,
                    memory_usage_provider=mock_snapshot_manager,
                    objects=MemalotObjects(exit_2),
                    output_writer=mock_output_writer,
                    report_writer=mock_report_writer,
                    options=test_options,
                    iteration=MemalotCount(2),
                    detailed_report=True,
                    function_name=None,
                    excluded_from_referrers=ANY,  # Dynamic object IDs, but should have 1 element
                ),
            ]
        )
        # Verify excluded_from_referrers has exactly one element in each call
        for call_obj in mock_report_generator.generate_report.call_args_list:
            assert len(call_obj.kwargs["excluded_from_referrers"]) == 1

        # Verify generate_new_snapshot was called twice with object_getter and since_snapshot=None
        assert mock_snapshot_manager.generate_new_snapshot.call_count == 2
        mock_snapshot_manager.generate_new_snapshot.assert_has_calls(
            [
                call(object_getter=object_getter, since_snapshot=None),
                call(object_getter=object_getter, since_snapshot=None),
            ]
        )

        assert mock_snapshot_manager.clear_snapshots.call_count == 2

    def test_calls_per_report_two_with_warmup_two(
        self,
        mock_output_writer: MagicMock,
        mock_report_writer: MagicMock,
        mock_snapshot_manager: MagicMock,
        mock_report_generator: MagicMock,
        mock_get_objects_func: MagicMock,
        test_options: Options,
    ) -> None:
        """
        With warmup_calls=2 and calls_per_report=2, a baseline report is generated on the
        second call, then a snapshot is created on the third call, and the report is
        generated on the fourth call using objects from the snapshot.
        """
        exit_snapshot = [
            "snapshot-object1",
            "snapshot-object2",
            "snapshot-object3",
            "snapshot-object4",
        ]
        report_objects = [
            "report-object1",
            "report-object2",
            "snapshot-object3",
            "snapshot-object4",
        ]

        mock_get_objects_func.side_effect = [exit_snapshot, report_objects]

        def _mock_is_in_snapshot(obj: object) -> bool:
            # Objects in the snapshot that we want to check for in the report
            return obj in ["snapshot-object3", "snapshot-object4"]

        def _mock_is_new_since_snapshot(obj: object) -> bool:
            return obj in ["snapshot-object3", "snapshot-object4"]

        mock_snapshot_manager.most_recent_snapshot.is_in_snapshot = MagicMock(
            wraps=_mock_is_in_snapshot
        )
        mock_snapshot_manager.most_recent_snapshot.is_new_since_snapshot = MagicMock(
            wraps=_mock_is_new_since_snapshot
        )

        object_getter = FilteringObjectGetter(
            get_objects_func=mock_get_objects_func,
            options=test_options,
            snapshot_managers=[mock_snapshot_manager],
        )

        leak_monitor = LeakMonitorImpl(
            writer=mock_output_writer,
            report_writer=mock_report_writer,
            warmup_calls=2,
            calls_per_report=2,
            options=test_options,
            snapshot_manager=mock_snapshot_manager,
            report_generator=mock_report_generator,
            object_getter=object_getter,
        )

        with leak_monitor:
            pass
        assert mock_report_generator.generate_report.call_count == 0

        with leak_monitor:
            pass
        # A report should have been generated (but with no objects, and not a detailed report)
        assert mock_report_generator.generate_report.call_count == 1
        mock_report_generator.generate_report.assert_called_once_with(
            report_id=mock_snapshot_manager.report_id,
            iteration_start_time=mock_snapshot_manager.most_recent_snapshot_time,
            memory_usage_provider=mock_snapshot_manager,
            objects=MemalotObjects([]),
            output_writer=mock_output_writer,
            report_writer=mock_report_writer,
            options=test_options,
            iteration=MemalotCount(1),
            excluded_from_referrers=ANY,  # Dynamic object IDs, but should have 1 element
            detailed_report=False,
            function_name=None,
        )
        # Verify excluded_from_referrers has exactly one element
        assert (
            len(mock_report_generator.generate_report.call_args.kwargs["excluded_from_referrers"])
            == 1
        )

        with leak_monitor:
            pass
        # No new report yet, but a snapshot should have been generated
        assert mock_report_generator.generate_report.call_count == 1

        # Two snapshots: one on enter (when warmup finishes) and one on exit (with new objects)
        assert mock_snapshot_manager.generate_new_snapshot.call_count == 2
        first_call = mock_snapshot_manager.generate_new_snapshot.call_args_list[0]
        second_call = mock_snapshot_manager.generate_new_snapshot.call_args_list[1]

        # Check the first call uses the object_getter that was passed to the constructor
        # and since_snapshot=None
        assert first_call.kwargs["object_getter"] is object_getter
        assert first_call.kwargs["since_snapshot"] is None

        # Check the second call uses since_snapshot=<snapshot>
        assert second_call.kwargs["object_getter"] is object_getter
        assert second_call.kwargs["since_snapshot"] == mock_snapshot_manager.most_recent_snapshot

        with leak_monitor:
            pass
        # Now a full report should be generated
        # Check that iteration 2 was generated
        assert mock_report_generator.generate_report.call_count == 2

        # Now assert the call with the specific parameters
        expected_objects = ["snapshot-object3", "snapshot-object4"]
        mock_report_generator.generate_report.assert_called_with(
            report_id=mock_snapshot_manager.report_id,
            iteration_start_time=mock_snapshot_manager.most_recent_snapshot_time,
            memory_usage_provider=mock_snapshot_manager,
            objects=MemalotObjects(expected_objects),
            output_writer=mock_output_writer,
            report_writer=mock_report_writer,
            options=test_options,
            iteration=MemalotCount(2),
            excluded_from_referrers=ANY,
            detailed_report=True,
            function_name=None,
        )
        # Verify excluded_from_referrers has exactly one element
        assert (
            len(mock_report_generator.generate_report.call_args.kwargs["excluded_from_referrers"])
            == 1
        )


class TestLeakMonitorThread:
    """
    Tests for the `LeakMonitorThread` class.
    """

    def test_report_generated(
        self,
        mock_output_writer: MagicMock,
        mock_report_writer: MagicMock,
        mock_all_objects_manager: MagicMock,
        mock_new_objects_manager: MagicMock,
        mock_report_generator: MagicMock,
        mock_get_objects_func: MagicMock,
        test_options: Options,
    ) -> None:
        """
        Tests that a report is generated when the LeakMonitorThread is started.
        """
        sleep_func = MagicMock()
        # Allow three sleeps: warmup (30s), initial wait (60s), iteration (60s), then stop
        sleep_func.side_effect = [None, None, StopMonitorThreadException]

        snapshot_objects = ["snapshot-object1", "snapshot-object2"]

        # Only one call to get_objects in the first iteration (for the snapshot)
        mock_get_objects_func.side_effect = [snapshot_objects]

        # Mock the snapshot to return empty MemalotObjects for the first report
        # since no previous snapshot exists
        mock_all_objects_manager.most_recent_snapshot = None
        mock_new_objects_manager.most_recent_snapshot = None

        object_getter = FilteringObjectGetter(
            get_objects_func=mock_get_objects_func,
            options=test_options,
            snapshot_managers=[mock_all_objects_manager, mock_new_objects_manager],
        )

        leak_monitor = LeakMonitorThread(
            max_object_lifetime=60.0,
            warmup_time=30.0,
            writer=mock_output_writer,
            report_writer=mock_report_writer,
            options=test_options,
            all_objects_manager=mock_all_objects_manager,
            new_objects_manager=mock_new_objects_manager,
            object_getter=object_getter,
            report_generator=mock_report_generator,
            sleep_func=sleep_func,
        )

        leak_monitor.start()

        def _assert_one_report() -> None:
            assert mock_report_generator.generate_report.call_count >= 1

        wait_for_assertion(_assert_one_report)

        sleep_func.assert_has_calls([call(30.0), call(60.0), call(60.0)])

        # Verify all_objects_manager.generate_new_snapshot was called twice:
        # 1. At start with since_snapshot=None (all objects baseline after warmup)
        # 2. After first iteration with since_snapshot=None (all objects update after report)
        mock_all_objects_manager.generate_new_snapshot.assert_has_calls(
            [
                call(object_getter=object_getter, since_snapshot=None),
                call(object_getter=object_getter, since_snapshot=None),
            ]
        )

        # Verify new_objects_manager.generate_new_snapshot was called once:
        # 1. In first iteration with since_snapshot=all_objects_manager.most_recent_snapshot
        mock_new_objects_manager.generate_new_snapshot.assert_called_once_with(
            object_getter=object_getter,
            since_snapshot=mock_all_objects_manager.most_recent_snapshot,
        )

        # Check generate_report was called with all expected parameters
        mock_report_generator.generate_report.assert_called_once_with(
            report_id=mock_all_objects_manager.report_id,
            iteration_start_time=mock_all_objects_manager.most_recent_snapshot_time,
            memory_usage_provider=mock_all_objects_manager,
            objects=MemalotObjects([]),
            output_writer=mock_output_writer,
            report_writer=mock_report_writer,
            options=test_options,
            iteration=MemalotCount(1),
            detailed_report=False,  # First iteration is warmup
            excluded_from_referrers=[],
        )

    def test_generate_reports_with_multiple_iterations(
        self,
        mock_output_writer: MagicMock,
        mock_report_writer: MagicMock,
        mock_all_objects_manager: MagicMock,
        mock_new_objects_manager: MagicMock,
        mock_report_generator: MagicMock,
        mock_get_objects_func: MagicMock,
        test_options: Options,
    ) -> None:
        """
        Two iterations generate two reports and two snapshots with expected arguments.
        """
        sleep_func = MagicMock()
        # Allow multiple sleeps: warmup (5s), initial wait (10s),
        # iteration 1 (10s), iteration 2 (10s), then stop
        sleep_func.side_effect = [None, None, None, StopMonitorThreadException]

        # Iteration 1: snapshot creation at start, then report with empty objects
        # Iteration 2: check for objects still alive, generate report, then new snapshot
        report_2_objects = ["r2-a", "r2-b", "r2-c"]
        # Only some objects are in the snapshot (r2-a and r2-b)
        snapshot_objects = ["r2-a", "r2-b"]

        mock_get_objects_func.side_effect = [
            report_2_objects,  # Second iteration: for checking objects in snapshot
        ]

        mock_new_snapshot = create_mock(spec=MemalotUsageSnapshot)
        mock_new_objects_manager.most_recent_snapshot = mock_new_snapshot
        # Mock is_in_snapshot to filter objects - only return True for objects in snapshot_objects
        mock_new_snapshot.is_in_snapshot.side_effect = lambda obj: obj in snapshot_objects

        object_getter = FilteringObjectGetter(
            get_objects_func=mock_get_objects_func,
            options=test_options,
            snapshot_managers=[mock_all_objects_manager, mock_new_objects_manager],
        )

        leak_monitor = LeakMonitorThread(
            max_object_lifetime=10.0,
            warmup_time=5.0,
            writer=mock_output_writer,
            report_writer=mock_report_writer,
            options=test_options,
            all_objects_manager=mock_all_objects_manager,
            new_objects_manager=mock_new_objects_manager,
            object_getter=object_getter,
            report_generator=mock_report_generator,
            sleep_func=sleep_func,
        )

        leak_monitor.start()

        def _assert_two_reports() -> None:
            assert mock_report_generator.generate_report.call_count >= 2

        wait_for_assertion(_assert_two_reports)

        sleep_func.assert_has_calls([call(5.0), call(10.0), call(10.0), call(10.0)])

        # During execution, get_objects_func is called once (for checking objects in
        # second iteration)
        # generate_new_snapshot is mocked, so those calls don't execute the function
        assert mock_get_objects_func.call_count == 1

        assert mock_report_generator.generate_report.call_count == 2

        # Check all parameters for both reports
        mock_report_generator.generate_report.assert_has_calls(
            [
                call(
                    report_id=mock_all_objects_manager.report_id,
                    iteration_start_time=mock_all_objects_manager.most_recent_snapshot_time,
                    memory_usage_provider=mock_all_objects_manager,
                    objects=MemalotObjects([]),
                    output_writer=mock_output_writer,
                    report_writer=mock_report_writer,
                    options=test_options,
                    iteration=MemalotCount(1),
                    detailed_report=False,  # First iteration is warmup
                    excluded_from_referrers=[],
                ),
                call(
                    report_id=mock_all_objects_manager.report_id,
                    iteration_start_time=mock_all_objects_manager.most_recent_snapshot_time,
                    memory_usage_provider=mock_all_objects_manager,
                    objects=MemalotObjects(snapshot_objects),  # Only objects that passed the filter
                    output_writer=mock_output_writer,
                    report_writer=mock_report_writer,
                    options=test_options,
                    iteration=MemalotCount(2),
                    detailed_report=True,  # Second iteration is detailed
                    excluded_from_referrers=[],
                ),
            ]
        )

        # Verify all_objects_manager.generate_new_snapshot was called 3 times:
        # 1. At start with since_snapshot=None (all objects baseline after warmup)
        # 2. After first iteration with since_snapshot=None (all objects update after report)
        # 3. After second iteration with since_snapshot=None (all objects update after report)
        mock_all_objects_manager.generate_new_snapshot.assert_has_calls(
            [
                call(object_getter=object_getter, since_snapshot=None),
                call(object_getter=object_getter, since_snapshot=None),
                call(object_getter=object_getter, since_snapshot=None),
            ]
        )

        # Verify new_objects_manager.generate_new_snapshot was called twice:
        # 1. In first iteration with since_snapshot=all_objects_manager.most_recent_snapshot
        # 2. In second iteration with since_snapshot=all_objects_manager.most_recent_snapshot
        mock_new_objects_manager.generate_new_snapshot.assert_has_calls(
            [
                call(
                    object_getter=object_getter,
                    since_snapshot=mock_all_objects_manager.most_recent_snapshot,
                ),
                call(
                    object_getter=object_getter,
                    since_snapshot=mock_all_objects_manager.most_recent_snapshot,
                ),
            ]
        )

        mock_all_objects_manager.clear_snapshots.assert_not_called()
        mock_new_objects_manager.clear_snapshots.assert_not_called()

    def test_thread_keeps_running_with_exception(
        self,
        mock_output_writer: MagicMock,
        mock_report_writer: MagicMock,
        mock_all_objects_manager: MagicMock,
        mock_new_objects_manager: MagicMock,
        mock_report_generator: MagicMock,
        mock_get_objects_func: MagicMock,
        test_options: Options,
    ) -> None:
        """
        Tests that the thread keeps running even when an exception occurs during report generation.
        """
        sleep_func = MagicMock()

        mock_report_generator.generate_report.side_effect = ValueError

        object_getter = FilteringObjectGetter(
            get_objects_func=mock_get_objects_func,
            options=test_options,
            snapshot_managers=[mock_all_objects_manager, mock_new_objects_manager],
        )

        leak_monitor = LeakMonitorThread(
            max_object_lifetime=10.0,
            warmup_time=5.0,
            writer=mock_output_writer,
            report_writer=mock_report_writer,
            options=test_options,
            all_objects_manager=mock_all_objects_manager,
            new_objects_manager=mock_new_objects_manager,
            object_getter=object_getter,
            report_generator=mock_report_generator,
            sleep_func=sleep_func,
        )

        try:
            leak_monitor.start()

            def _assert_four_sleeps() -> None:
                # There should be one warmup call and three sleeps when the exception occurs
                assert sleep_func.call_count >= 4

            wait_for_assertion(_assert_four_sleeps)
        finally:
            leak_monitor.stop()

        assert mock_report_generator.generate_report.call_count >= 3

        # The exception occurs during generate_report, but before that the snapshot managers
        # should have been called. Verify all_objects_manager was called at least once
        # (after warmup)
        mock_all_objects_manager.generate_new_snapshot.assert_called_with(
            object_getter=object_getter, since_snapshot=None
        )

        # Verify new_objects_manager was called at least once with the all_objects snapshot
        mock_new_objects_manager.generate_new_snapshot.assert_called_with(
            object_getter=object_getter,
            since_snapshot=mock_all_objects_manager.most_recent_snapshot,
        )

        # When we get an exception we sleep for max_object_lifetime
        sleep_func.assert_called_with(10.0)


class TestFilteringObjectGetter:
    """
    Tests for the FilteringObjectGetter class.
    """

    def test_get_objects(
        self,
        mock_snapshot_manager: MagicMock,
        test_options: Options,
    ) -> None:
        """
        Test that get_objects() returns objects without any filtering.
        """
        mock_get_objects_func = MagicMock(return_value=["obj1", "obj2"])
        object_getter = FilteringObjectGetter(
            get_objects_func=mock_get_objects_func,
            options=test_options,
            snapshot_managers=[mock_snapshot_manager],
        )

        # Call get_objects
        result = object_getter.get_objects()

        # Should call the underlying function and return the filtered result
        mock_get_objects_func.assert_called_once_with(3)
        assert isinstance(result, list)

    def test_filtering_all_types(
        self,
        mock_snapshot_manager: MagicMock,
    ) -> None:
        """
        Test that FilteringObjectGetter applies all types of filtering correctly:
        - excluded_types (EXCLUDED_TYPES)
        - included_type_names (from options)
        - excluded_type_names (from options)
        - exclude_object_ids (objects from snapshot manager)
        """

        # Create various types of objects to test filtering
        class IncludedType:
            pass

        class ExcludedByName:
            pass

        class RegularObject:
            pass

        # Create instances
        included_obj = IncludedType()
        excluded_by_name_obj = ExcludedByName()
        regular_obj1 = RegularObject()
        regular_obj2 = RegularObject()

        # Set up snapshot manager to return objects to exclude
        mock_snapshot = MagicMock()
        mock_snapshot_manager.most_recent_snapshot = mock_snapshot
        mock_snapshot_manager.most_recent_snapshot_time = "some_time"

        # Mock get_objects_func to return all objects
        all_objects = [
            included_obj,
            excluded_by_name_obj,
            regular_obj1,
            regular_obj2,
            mock_snapshot,  # Should be filtered by exclude_object_ids
        ]

        mock_get_objects_func = MagicMock(return_value=all_objects)

        # Create options with specific included/excluded type names
        options = Options(
            included_type_names=frozenset([f"{IncludedType.__module__}.{IncludedType.__name__}"]),
            excluded_type_names=frozenset(
                [f"{ExcludedByName.__module__}.{ExcludedByName.__name__}"]
            ),
        )

        object_getter = FilteringObjectGetter(
            get_objects_func=mock_get_objects_func,
            options=options,
            snapshot_managers=[mock_snapshot_manager],
        )

        # Call get_objects
        result = object_getter.get_objects()

        # Should call the underlying function with max_untracked_search_depth
        mock_get_objects_func.assert_called_once_with(options.max_untracked_search_depth)

        # Verify filtering results:
        # - included_obj should be present (in included_type_names)
        # - excluded_by_name_obj should NOT be present (in excluded_type_names)
        # - regular_obj1 and regular_obj2 should NOT be present (not in included_type_names)
        # - mock_snapshot should NOT be present (in exclude_object_ids)
        assert included_obj in result
        assert excluded_by_name_obj not in result
        assert regular_obj1 not in result
        assert regular_obj2 not in result
        assert mock_snapshot not in result

        # Should only have one object: included_obj
        assert len(result) == 1
