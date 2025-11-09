from typing import Any, Dict, Optional
from unittest.mock import ANY, MagicMock

import pytest
from pytest_mock import MockerFixture

from memalot.api import create_leak_monitor, leak_monitor, start_leak_monitoring
from memalot.interface import LeakMonitor
from memalot.monitors import LeakMonitorImpl
from memalot.options import Options
from memalot.output import OutputWriter
from memalot.reports import ReportWriter
from tests.utils_for_testing import create_mock

_MODULE_UNDER_TEST = "memalot.api"


@pytest.fixture(name="mock_output_writer")
def _mock_output_writer() -> MagicMock:
    """
    Mock OutputWriter instance.
    """
    return create_mock(spec=OutputWriter)


@pytest.fixture(name="mock_report_writer")
def _mock_report_writer() -> MagicMock:
    """
    Mock ReportWriter instance.
    """
    return create_mock(spec=ReportWriter)


@pytest.fixture(name="mock_get_output_writer")
def _mock_get_output_writer(mocker: MockerFixture, mock_output_writer: MagicMock) -> MagicMock:
    """
    Mock get_output_writer function.
    """
    return mocker.patch(f"{_MODULE_UNDER_TEST}.get_output_writer", return_value=mock_output_writer)


@pytest.fixture(name="mock_get_report_writer")
def _mock_get_report_writer(mocker: MockerFixture, mock_report_writer: MagicMock) -> MagicMock:
    """
    Mock get_report_writer function.
    """
    return mocker.patch(f"{_MODULE_UNDER_TEST}.get_report_writer", return_value=mock_report_writer)


@pytest.fixture(name="mock_leak_monitor_thread")
def _mock_leak_monitor_thread(mocker: MockerFixture) -> MagicMock:
    """
    Mock LeakMonitorThread class.
    """
    return mocker.patch(f"{_MODULE_UNDER_TEST}.LeakMonitorThread")


@pytest.fixture(name="mock_leak_monitor")
def _mock_leak_monitor() -> MagicMock:
    """
    Mock LeakMonitor instance.
    """
    return create_mock(spec=LeakMonitor)


@pytest.fixture(name="mock_create_leak_monitor")
def _mock_create_leak_monitor(mocker: MockerFixture, mock_leak_monitor: MagicMock) -> MagicMock:
    """
    Mock _create_leak_monitor function.
    """
    return mocker.patch(f"{_MODULE_UNDER_TEST}.create_leak_monitor", return_value=mock_leak_monitor)


class TestStart:
    """
    Tests for the start function.
    """

    def test_start(
        self,
        mock_output_writer: MagicMock,
        mock_get_output_writer: MagicMock,
        mock_report_writer: MagicMock,
        mock_get_report_writer: MagicMock,
        mock_leak_monitor_thread: MagicMock,
    ) -> None:
        """
        Test that the start function starts the leak monitor.
        """
        expected_options = Options()

        start_leak_monitoring(max_object_lifetime=1.0)

        mock_get_output_writer.assert_called_once_with(options=expected_options)
        mock_get_report_writer.assert_called_once_with(options=expected_options)
        mock_leak_monitor_thread.assert_called_once_with(
            max_object_lifetime=1.0,
            warmup_time=1.0,
            writer=mock_output_writer,
            report_writer=mock_report_writer,
            options=expected_options,
            all_objects_manager=ANY,
            new_objects_manager=ANY,
            object_getter=ANY,
        )

    @pytest.mark.parametrize(
        "max_object_lifetime,warmup_time,expected_warmup_time",
        [
            (1.0, None, 1.0),  # warmup_time defaults to max_object_lifetime
            (2.0, 3.0, 3.0),  # explicit warmup_time
        ],
    )
    def test_start__with_max_object_lifetime_and_warmup_time(
        self,
        max_object_lifetime: float,
        warmup_time: Optional[float],
        expected_warmup_time: float,
        mock_output_writer: MagicMock,
        mock_get_output_writer: MagicMock,
        mock_report_writer: MagicMock,
        mock_get_report_writer: MagicMock,
        mock_leak_monitor_thread: MagicMock,
    ) -> None:
        """
        Test that the start function starts the leak monitor with different parameter values.
        """
        expected_options = Options()

        if warmup_time is None:
            start_leak_monitoring(max_object_lifetime=max_object_lifetime)
        else:
            start_leak_monitoring(max_object_lifetime=max_object_lifetime, warmup_time=warmup_time)

        mock_get_output_writer.assert_called_once_with(options=expected_options)
        mock_get_report_writer.assert_called_once_with(options=expected_options)
        mock_leak_monitor_thread.assert_called_once_with(
            max_object_lifetime=max_object_lifetime,
            warmup_time=expected_warmup_time,
            writer=mock_output_writer,
            report_writer=mock_report_writer,
            options=expected_options,
            all_objects_manager=ANY,
            new_objects_manager=ANY,
            object_getter=ANY,
        )

    @pytest.mark.parametrize(
        "kwargs,expected_options",
        [
            (
                {"force_terminal": True, "color": False},
                Options(force_terminal=True, color=False),
            ),
            (
                {"max_types_in_leak_summary": 100, "check_referrers": False},
                Options(
                    max_types_in_leak_summary=100,
                    check_referrers=False,
                ),
            ),
            (
                {"max_object_details": 50, "referrers_max_depth": 25},
                Options(max_object_details=50, referrers_max_depth=25),
            ),
        ],
    )
    def test_start__with_options_passed(
        self,
        kwargs: Dict[str, Any],
        expected_options: Options,
        mock_output_writer: MagicMock,
        mock_get_output_writer: MagicMock,
        mock_report_writer: MagicMock,
        mock_get_report_writer: MagicMock,
        mock_leak_monitor_thread: MagicMock,
    ) -> None:
        """
        Test that the start function passes options correctly to the Options class.
        """
        if "force_terminal" in kwargs and "color" in kwargs:
            start_leak_monitoring(
                max_object_lifetime=1.0,
                force_terminal=kwargs["force_terminal"],
                color=kwargs["color"],
            )
        elif "max_types_in_leak_summary" in kwargs and "check_referrers" in kwargs:
            start_leak_monitoring(
                max_object_lifetime=1.0,
                max_types_in_leak_summary=kwargs["max_types_in_leak_summary"],
                check_referrers=kwargs["check_referrers"],
            )
        elif "max_object_details" in kwargs and "referrers_max_depth" in kwargs:
            start_leak_monitoring(
                max_object_lifetime=1.0,
                max_object_details=kwargs["max_object_details"],
                referrers_max_depth=kwargs["referrers_max_depth"],
            )

        mock_get_output_writer.assert_called_once_with(options=expected_options)
        mock_get_report_writer.assert_called_once_with(options=expected_options)
        mock_leak_monitor_thread.assert_called_once_with(
            max_object_lifetime=1.0,
            warmup_time=1.0,
            writer=mock_output_writer,
            report_writer=mock_report_writer,
            options=expected_options,
            all_objects_manager=ANY,
            new_objects_manager=ANY,
            object_getter=ANY,
        )


class TestLeakMonitorDecorator:
    """
    Tests for the leak_monitor decorator.
    """

    def test_leak_monitor_decorator(
        self,
        mock_leak_monitor: MagicMock,
        mock_create_leak_monitor: MagicMock,
    ) -> None:
        """
        Test that the leak_monitor decorator works with default parameters.
        """

        @leak_monitor()
        def test_function(x: int, y: int) -> int:
            return x + y

        result = test_function(1, 2)

        assert result == 3
        self._check_create_leak_monitor_call_default(mock_create_leak_monitor)
        mock_leak_monitor.__enter__.assert_called_once()
        mock_leak_monitor.__exit__.assert_called_once()

    def test_leak_monitor_decorator__without_parentheses(
        self,
        mock_leak_monitor: MagicMock,
        mock_create_leak_monitor: MagicMock,
    ) -> None:
        """
        Test that the leak_monitor decorator works without parentheses.
        """

        @leak_monitor
        def test_function(x: int, y: int) -> int:
            return x + y

        result = test_function(1, 2)

        assert result == 3
        self._check_create_leak_monitor_call_default(mock_create_leak_monitor)
        mock_leak_monitor.__enter__.assert_called_once()
        mock_leak_monitor.__exit__.assert_called_once()

    @pytest.mark.parametrize(
        "warmup_calls,max_object_age_calls",
        [
            (1, 1),  # default values
            (2, 3),  # custom values
        ],
    )
    def test_leak_monitor_decorator__with_different_call_parameters(
        self,
        warmup_calls: int,
        max_object_age_calls: int,
        mock_leak_monitor: MagicMock,
        mock_create_leak_monitor: MagicMock,
    ) -> None:
        """
        Test that the leak_monitor decorator works with different parameter combinations.
        """

        @leak_monitor(warmup_calls=warmup_calls, max_object_age_calls=max_object_age_calls)
        def test_function(value: int) -> int:
            return value * 2

        result = test_function(10)

        assert result == 20
        mock_create_leak_monitor.assert_called_once_with(
            function_name="test_function",
            warmup_calls=warmup_calls,
            max_object_age_calls=max_object_age_calls,
            included_type_names=frozenset(),
            excluded_type_names=frozenset(),
            max_types_in_leak_summary=500,
            compute_size_in_leak_summary=False,
            max_untracked_search_depth=3,
            check_referrers=True,
            max_object_details=30,
            referrers_max_depth=50,
            referrers_search_timeout=300.0,
            single_object_referrer_limit=100,
            referrers_module_prefixes=None,
            referrers_max_untracked_search_depth=30,
            save_reports=True,
            report_directory=None,
            str_func=None,
            str_max_length=100,
            force_terminal=None,
            output_func=None,
            tee_console=False,
            color=True,
        )
        mock_leak_monitor.__enter__.assert_called_once()
        mock_leak_monitor.__exit__.assert_called_once()

    @pytest.mark.parametrize(
        "kwargs,expected_kwargs",
        [
            (
                {"force_terminal": True, "color": False},
                {"force_terminal": True, "color": False},
            ),
            (
                {"max_types_in_leak_summary": 100, "check_referrers": False},
                {"max_types_in_leak_summary": 100, "check_referrers": False},
            ),
            (
                {"max_object_details": 50, "referrers_max_depth": 25},
                {"max_object_details": 50, "referrers_max_depth": 25},
            ),
        ],
    )
    def test_leak_monitor_decorator__with_options_kwargs(
        self,
        kwargs: Dict[str, Any],
        expected_kwargs: Dict[str, Any],
        mock_leak_monitor: MagicMock,
        mock_create_leak_monitor: MagicMock,
    ) -> None:
        """
        Test that the leak_monitor decorator passes options kwargs correctly.
        """

        if "force_terminal" in kwargs and "color" in kwargs:

            @leak_monitor(
                warmup_calls=2,
                max_object_age_calls=3,
                force_terminal=kwargs["force_terminal"],
                color=kwargs["color"],
            )
            def test_function() -> str:
                return "success"

        elif "max_types_in_leak_summary" in kwargs and "check_referrers" in kwargs:

            @leak_monitor(
                warmup_calls=2,
                max_object_age_calls=3,
                max_types_in_leak_summary=kwargs["max_types_in_leak_summary"],
                check_referrers=kwargs["check_referrers"],
            )
            def test_function() -> str:
                return "success"

        elif "max_object_details" in kwargs and "referrers_max_depth" in kwargs:

            @leak_monitor(
                warmup_calls=2,
                max_object_age_calls=3,
                max_object_details=kwargs["max_object_details"],
                referrers_max_depth=kwargs["referrers_max_depth"],
            )
            def test_function() -> str:
                return "success"

        else:
            raise ValueError(f"Invalid kwargs: {kwargs}")

        result = test_function()

        assert result == "success"
        # Build the full expected call with all defaults
        expected_call_kwargs = {
            "function_name": "test_function",
            "warmup_calls": 2,
            "max_object_age_calls": 3,
            "included_type_names": frozenset(),
            "excluded_type_names": frozenset(),
            "max_types_in_leak_summary": 500,
            "compute_size_in_leak_summary": False,
            "max_untracked_search_depth": 3,
            "check_referrers": True,
            "max_object_details": 30,
            "referrers_max_depth": 50,
            "referrers_search_timeout": 300.0,
            "single_object_referrer_limit": 100,
            "referrers_module_prefixes": None,
            "referrers_max_untracked_search_depth": 30,
            "save_reports": True,
            "report_directory": None,
            "str_func": None,
            "str_max_length": 100,
            "force_terminal": None,
            "output_func": None,
            "tee_console": False,
            "color": True,
        }
        # Override with the specific expected kwargs
        expected_call_kwargs.update(expected_kwargs)
        mock_create_leak_monitor.assert_called_once_with(**expected_call_kwargs)
        mock_leak_monitor.__enter__.assert_called_once()
        mock_leak_monitor.__exit__.assert_called_once()

    def test_leak_monitor_decorator__exception_handling(
        self,
        mock_leak_monitor: MagicMock,
        mock_create_leak_monitor: MagicMock,
    ) -> None:
        """
        Test that the decorator properly handles exceptions from the decorated function.
        """

        @leak_monitor()
        def test_function() -> None:
            raise ValueError("test exception")

        with pytest.raises(ValueError, match="test exception"):
            test_function()

        self._check_create_leak_monitor_call_default(mock_create_leak_monitor)
        mock_leak_monitor.__enter__.assert_called_once()
        mock_leak_monitor.__exit__.assert_called_once()

    def _check_create_leak_monitor_call_default(self, mock_create_leak_monitor: MagicMock) -> None:
        mock_create_leak_monitor.assert_called_once_with(
            function_name="test_function",
            warmup_calls=1,
            max_object_age_calls=1,
            included_type_names=frozenset(),
            excluded_type_names=frozenset(),
            max_types_in_leak_summary=500,
            compute_size_in_leak_summary=False,
            max_untracked_search_depth=3,
            check_referrers=True,
            max_object_details=30,
            referrers_max_depth=50,
            referrers_search_timeout=300.0,
            single_object_referrer_limit=100,
            referrers_module_prefixes=None,
            referrers_max_untracked_search_depth=30,
            save_reports=True,
            report_directory=None,
            str_func=None,
            str_max_length=100,
            force_terminal=None,
            output_func=None,
            tee_console=False,
            color=True,
        )


class TestCreateLeakMonitor:
    """
    Tests for the _create_leak_monitor function.
    """

    def test_create_leak_monitor(
        self,
        mock_output_writer: MagicMock,
        mock_get_output_writer: MagicMock,
        mock_report_writer: MagicMock,
        mock_get_report_writer: MagicMock,
        mocker: MockerFixture,
    ) -> None:
        """
        Test that _create_leak_monitor creates a LeakMonitor with correct parameters.
        """
        mock_leak_monitor_impl = create_mock(spec=LeakMonitorImpl)
        mock_leak_monitor_impl_class = mocker.patch(
            f"{_MODULE_UNDER_TEST}.LeakMonitorImpl", return_value=mock_leak_monitor_impl
        )

        expected_options = Options(save_reports=True)

        result = create_leak_monitor(
            warmup_calls=5,
            max_object_age_calls=3,
        )

        assert result == mock_leak_monitor_impl
        mock_get_output_writer.assert_called_once_with(options=expected_options)
        mock_get_report_writer.assert_called_once_with(options=expected_options)
        mock_leak_monitor_impl_class.assert_called_once_with(
            writer=mock_output_writer,
            report_writer=mock_report_writer,
            warmup_calls=5,
            calls_per_report=3,
            options=expected_options,
            snapshot_manager=ANY,
            object_getter=ANY,
            function_name=None,
        )
