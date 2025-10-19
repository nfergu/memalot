from pathlib import Path

import pytest
from _pytest.capture import CaptureFixture

from memalot.cli import entrypoint


class TestListReports:
    """
    Functional tests for the "list" cli command.
    """

    @pytest.fixture(name="test_reports_dir")
    def _test_reports_dir(self) -> Path:
        """
        Fixture providing the path to test reports directory.
        """
        return Path(__file__).parent / "test_data" / "reports" / "v1"

    def test_list_command_basic(self, capsys: CaptureFixture[str], test_reports_dir: Path) -> None:
        """
        Test basic list command functionality with existing test data.
        """
        # Act
        result = entrypoint(["list", "--report-directory", str(test_reports_dir)])

        # Assert
        assert result == 0
        captured = capsys.readouterr()

        assert "Reports" in captured.out
        assert "Report ID" in captured.out
        assert "Iterations" in captured.out
        assert "Start Time" in captured.out
        assert "Entrypoint" in captured.out
        assert "Arguments" in captured.out

        assert "d6wf-uw2w" in captured.out
        assert "2025-09-29 20:54:18" in captured.out
        assert "utils_for_tes" in captured.out  # Truncated in table display

        assert "lyy0-uf3p" in captured.out
        assert "2025-09-29 20:54:06" in captured.out
        assert "utils_for_tes" in captured.out  # Truncated in table display

        assert "ykik-ab4l" in captured.out
        assert "2025-09-29 20:53:39" in captured.out
        assert "utils_for_tes" in captured.out  # Truncated in table display
        assert "dummy_arg1" in captured.out
        assert "dummy_arg2" in captured.out

    def test_list_command_with_num_reports(
        self, capsys: CaptureFixture[str], test_reports_dir: Path
    ) -> None:
        """
        Test list command with --num-reports option.
        """
        # Act
        result = entrypoint(
            ["list", "--num-reports", "2", "--report-directory", str(test_reports_dir)]
        )

        # Assert
        assert result == 0
        captured = capsys.readouterr()

        # Should show the most recent two reports from test data
        assert "d6wf-uw2w" in captured.out
        assert "lyy0-uf3p" in captured.out
        assert "ykik-ab4l" not in captured.out

    def test_list_command_empty_directory(
        self, capsys: CaptureFixture[str], tmp_path: Path
    ) -> None:
        """
        Test list command with empty report directory.
        """
        # Create empty directory
        empty_dir = tmp_path / "empty_reports"
        empty_dir.mkdir()

        # Act
        result = entrypoint(["list", "--report-directory", str(empty_dir)])

        # Assert
        assert result == 0
        captured = capsys.readouterr()

        # Should show "no reports found" message
        assert "No reports found" in captured.out

    def test_list_command_nonexistent_directory(
        self, capsys: CaptureFixture[str], tmp_path: Path
    ) -> None:
        """
        Test list command with nonexistent report directory.
        """
        nonexistent_dir = tmp_path / "does_not_exist"

        # Act
        result = entrypoint(["list", "--report-directory", str(nonexistent_dir)])

        # Assert
        assert result == 0
        captured = capsys.readouterr()

        # Should show "no reports found" message since directory doesn't exist
        assert "No reports found" in captured.out

    def test_list_command_high_num_reports(
        self, capsys: CaptureFixture[str], test_reports_dir: Path
    ) -> None:
        """
        Test list command with higher --num-reports than available reports.
        """
        # Act - request more reports than exist in test data
        result = entrypoint(
            ["list", "--num-reports", "100", "--report-directory", str(test_reports_dir)]
        )

        # Assert
        assert result == 0
        captured = capsys.readouterr()

        # Should show all reports from test data
        assert "d6wf-uw2w" in captured.out
        assert "lyy0-uf3p" in captured.out
        assert "ykik-ab4l" in captured.out


class TestPrintReports:
    """
    Functional tests for the "print" cli command.
    """

    @pytest.fixture(name="test_reports_dir")
    def _test_reports_dir(self) -> Path:
        """
        Fixture providing the path to test reports directory.
        """
        return Path(__file__).parent / "test_data" / "reports" / "v1"

    def test_print_basic_latest(self, capsys: CaptureFixture[str], test_reports_dir: Path) -> None:
        """
        Print the most recent iteration of a report and check for key information.
        """
        # Act
        result = entrypoint(["print", "lyy0-uf3p", "--report-directory", str(test_reports_dir)])

        # Assert
        assert result == 0
        captured = capsys.readouterr()
        assert "Memalot Report (iteration 3)" in captured.out
        assert "Possible New Leaks (iteration 3)" in captured.out
        assert "Object Type" in captured.out
        assert "Count" in captured.out
        assert "Details for __main__.MemalotObject" in captured.out
        assert "Deep size (estimated): ~1.4 KiB" in captured.out
        assert "End of Memalot Report (iteration 3)" in captured.out

    def test_print_no_leaks_message(
        self, capsys: CaptureFixture[str], test_reports_dir: Path
    ) -> None:
        """
        Print a report that contains an iteration with no leaks and check for the message.
        """
        # Act
        result = entrypoint(
            [
                "print",
                "d6wf-uw2w",
                "--num-iterations",
                "3",
                "--report-directory",
                str(test_reports_dir),
            ]
        )

        # Assert
        assert result == 0
        captured = capsys.readouterr()
        assert (
            "This is a warmup iteration. Reports will be available from the next iteration."
        ) in captured.out

    def test_print_num_iterations_two(
        self, capsys: CaptureFixture[str], test_reports_dir: Path
    ) -> None:
        """
        Print two most recent iterations and check that both are present.
        """
        # Act
        result = entrypoint(
            [
                "print",
                "lyy0-uf3p",
                "--num-iterations",
                "2",
                "--report-directory",
                str(test_reports_dir),
            ]
        )

        # Assert
        assert result == 0
        captured = capsys.readouterr()
        assert "Memalot Report (iteration 2)" in captured.out
        assert "Memalot Report (iteration 3)" in captured.out
        assert "Possible New Leaks (iteration 2)" in captured.out
        assert "Possible New Leaks (iteration 3)" in captured.out
        assert "End of Memalot Report (iteration 2)" in captured.out
        assert "End of Memalot Report (iteration 3)" in captured.out

    def test_print_filter_types(self, capsys: CaptureFixture[str], test_reports_dir: Path) -> None:
        """
        Print a report filtered by object types and verify filtering takes effect.
        """
        # Act
        result = entrypoint(
            [
                "print",
                "ykik-ab4l",
                "--report-directory",
                str(test_reports_dir),
                "--filter-types",
                "list",
            ]
        )

        # Assert
        assert result == 0
        captured = capsys.readouterr()
        assert "Possible New Leaks (iteration 3)" in captured.out
        assert "Details for __main__.MemalotObject" not in captured.out
        assert "Details for builtins.list" in captured.out

    def test_print_summary_only(self, capsys: CaptureFixture[str], test_reports_dir: Path) -> None:
        """
        Print a report with summary only and verify object details are not printed.
        """
        # Act
        result = entrypoint(
            [
                "print",
                "ykik-ab4l",
                "--report-directory",
                str(test_reports_dir),
                "--summary-only",
            ]
        )

        # Assert
        assert result == 0
        captured = capsys.readouterr()
        assert "Possible New Leaks (iteration 3)" in captured.out
        assert "Details for" not in captured.out

    def test_print_invalid_report_id(self, test_reports_dir: Path) -> None:
        """
        Attempt to print a non-existent report and expect an error.
        """
        with pytest.raises(ValueError):
            entrypoint(["print", "does-not-exist", "--report-directory", str(test_reports_dir)])
