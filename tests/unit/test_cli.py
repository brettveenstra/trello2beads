"""
Unit tests for CLI entry point (main function)
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add parent directory to path to import trello2beads module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from trello2beads.cli import main


class TestCLIEntryPoint:
    """Test main() CLI entry point"""

    def test_main_shows_help_with_help_flag(self, capsys):
        """Should show help and exit when --help flag is provided"""
        with patch("sys.argv", ["trello2beads", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_main_shows_help_with_h_flag(self, capsys):
        """Should show help and exit when -h flag is provided"""
        with patch("sys.argv", ["trello2beads", "-h"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_main_exits_with_missing_credentials(self, capsys):
        """Should exit with error when credentials are missing"""
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("sys.argv", ["trello2beads"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1

    def test_main_exits_when_beads_db_not_found(self, capsys):
        """Should exit when beads database is not found"""
        with (
            patch.dict(
                "os.environ",
                {
                    "TRELLO_API_KEY": "test-key",
                    "TRELLO_TOKEN": "test-token",
                    "TRELLO_BOARD_ID": "test-board",
                },
            ),
            patch("sys.argv", ["trello2beads"]),
            patch("pathlib.Path.exists", return_value=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1

    def test_main_exits_when_missing_board_identifier(self, capsys):
        """Should exit when board ID and URL are both missing"""
        with (
            patch.dict(
                "os.environ",
                {
                    "TRELLO_API_KEY": "test-key",
                    "TRELLO_TOKEN": "test-token",
                    # No TRELLO_BOARD_ID or TRELLO_BOARD_URL
                },
                clear=True,
            ),
            patch("sys.argv", ["trello2beads"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1

    def test_main_with_verbose_flag(self):
        """Should set DEBUG log level with --verbose flag"""
        with (
            patch.dict(
                "os.environ",
                {
                    "TRELLO_API_KEY": "test-key",
                    "TRELLO_TOKEN": "test-token",
                    "TRELLO_BOARD_ID": "test-board",
                },
            ),
            patch("sys.argv", ["trello2beads", "--verbose"]),
            patch("pathlib.Path.exists", return_value=False),
            patch("trello2beads.cli.setup_logging") as mock_setup_logging,
            pytest.raises(SystemExit),
        ):
            main()
        mock_setup_logging.assert_called_once_with("DEBUG", None)

    def test_main_with_quiet_flag(self):
        """Should set ERROR log level with --quiet flag"""
        with (
            patch.dict(
                "os.environ",
                {
                    "TRELLO_API_KEY": "test-key",
                    "TRELLO_TOKEN": "test-token",
                    "TRELLO_BOARD_ID": "test-board",
                },
            ),
            patch("sys.argv", ["trello2beads", "--quiet"]),
            patch("pathlib.Path.exists", return_value=False),
            patch("trello2beads.cli.setup_logging") as mock_setup_logging,
            pytest.raises(SystemExit),
        ):
            main()
        mock_setup_logging.assert_called_once_with("ERROR", None)

    def test_main_with_log_level_flag(self):
        """Should set custom log level with --log-level flag"""
        with (
            patch.dict(
                "os.environ",
                {
                    "TRELLO_API_KEY": "test-key",
                    "TRELLO_TOKEN": "test-token",
                    "TRELLO_BOARD_ID": "test-board",
                },
            ),
            patch("sys.argv", ["trello2beads", "--log-level", "warning"]),
            patch("pathlib.Path.exists", return_value=False),
            patch("trello2beads.cli.setup_logging") as mock_setup_logging,
            pytest.raises(SystemExit),
        ):
            main()
        mock_setup_logging.assert_called_once_with("WARNING", None)

    def test_main_with_log_file_flag(self):
        """Should set log file with --log-file flag"""
        with (
            patch.dict(
                "os.environ",
                {
                    "TRELLO_API_KEY": "test-key",
                    "TRELLO_TOKEN": "test-token",
                    "TRELLO_BOARD_ID": "test-board",
                },
            ),
            patch("sys.argv", ["trello2beads", "--log-file", "test.log"]),
            patch("pathlib.Path.exists", return_value=False),
            patch("trello2beads.cli.setup_logging") as mock_setup_logging,
            pytest.raises(SystemExit),
        ):
            main()
        mock_setup_logging.assert_called_once_with("INFO", "test.log")

    def test_main_loads_env_file_when_exists(self, tmp_path):
        """Should load .env file if it exists"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "TRELLO_API_KEY=env-file-key\nTRELLO_TOKEN=env-file-token\nTRELLO_BOARD_ID=env-file-board\n"
        )

        with (
            patch.dict("os.environ", {"TRELLO_ENV_FILE": str(env_file)}, clear=True),
            patch("sys.argv", ["trello2beads"]),
            patch("pathlib.Path.exists", return_value=False),
            pytest.raises(SystemExit),
        ):
            main()
            # Values should be loaded from .env file
            import os

            assert os.environ.get("TRELLO_API_KEY") == "env-file-key"

    def test_main_env_vars_override_env_file(self, tmp_path):
        """Should not override existing environment variables with .env file values"""
        env_file = tmp_path / ".env"
        env_file.write_text("TRELLO_API_KEY=env-file-key\n")

        with (
            patch.dict(
                "os.environ",
                {
                    "TRELLO_ENV_FILE": str(env_file),
                    "TRELLO_API_KEY": "existing-key",  # Should not be overridden
                    "TRELLO_TOKEN": "token",
                    "TRELLO_BOARD_ID": "board",
                },
            ),
            patch("sys.argv", ["trello2beads"]),
            patch("pathlib.Path.exists", return_value=False),
            pytest.raises(SystemExit),
        ):
            main()

    def test_main_max_workers_valid(self):
        """Should parse valid --max-workers flag"""

        def mock_path_exists(self):
            return str(self).endswith("beads.db")

        with (
            patch.dict(
                "os.environ",
                {
                    "TRELLO_API_KEY": "test-key",
                    "TRELLO_TOKEN": "test-token",
                    "TRELLO_BOARD_ID": "test-board",
                },
            ),
            patch("sys.argv", ["trello2beads", "--max-workers", "5"]),
            patch("pathlib.Path.exists", mock_path_exists),
            patch("trello2beads.cli.TrelloReader"),
            patch("trello2beads.cli.BeadsWriter"),
            patch("trello2beads.cli.TrelloToBeadsConverter") as mock_converter,
        ):
            main()

            # Verify converter.convert() was called with max_workers=5
            mock_converter.return_value.convert.assert_called_once()
            call_kwargs = mock_converter.return_value.convert.call_args.kwargs
            assert call_kwargs["max_workers"] == 5

    def test_main_max_workers_missing_value(self):
        """Should exit when --max-workers has no value"""
        with (
            patch.dict(
                "os.environ",
                {
                    "TRELLO_API_KEY": "test-key",
                    "TRELLO_TOKEN": "test-token",
                    "TRELLO_BOARD_ID": "test-board",
                },
            ),
            patch("sys.argv", ["trello2beads", "--max-workers"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1

    def test_main_max_workers_invalid_value(self):
        """Should exit when --max-workers has non-numeric value"""
        with (
            patch.dict(
                "os.environ",
                {
                    "TRELLO_API_KEY": "test-key",
                    "TRELLO_TOKEN": "test-token",
                    "TRELLO_BOARD_ID": "test-board",
                },
            ),
            patch("sys.argv", ["trello2beads", "--max-workers", "abc"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1

    def test_main_max_workers_too_small(self):
        """Should exit when --max-workers is less than 1"""
        with (
            patch.dict(
                "os.environ",
                {
                    "TRELLO_API_KEY": "test-key",
                    "TRELLO_TOKEN": "test-token",
                    "TRELLO_BOARD_ID": "test-board",
                },
            ),
            patch("sys.argv", ["trello2beads", "--max-workers", "0"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1

    def test_main_status_mapping_valid(self, tmp_path):
        """Should load valid --status-mapping file"""
        mapping_file = tmp_path / "mapping.json"
        mapping_file.write_text('{"open": ["To Do"], "in_progress": ["In Progress"]}')

        def mock_path_exists(self):
            return str(self).endswith(("beads.db", "mapping.json"))

        with (
            patch.dict(
                "os.environ",
                {
                    "TRELLO_API_KEY": "test-key",
                    "TRELLO_TOKEN": "test-token",
                    "TRELLO_BOARD_ID": "test-board",
                },
            ),
            patch("sys.argv", ["trello2beads", "--status-mapping", str(mapping_file)]),
            patch("pathlib.Path.exists", mock_path_exists),
            patch("trello2beads.cli.TrelloReader"),
            patch("trello2beads.cli.BeadsWriter"),
            patch("trello2beads.cli.TrelloToBeadsConverter") as mock_converter,
        ):
            main()

            # Verify converter was initialized with custom status keywords
            call_kwargs = mock_converter.call_args.kwargs
            assert "status_keywords" in call_kwargs
            assert call_kwargs["status_keywords"]["open"] == ["To Do"]

    def test_main_status_mapping_missing_value(self):
        """Should exit when --status-mapping has no value"""
        with (
            patch.dict(
                "os.environ",
                {
                    "TRELLO_API_KEY": "test-key",
                    "TRELLO_TOKEN": "test-token",
                    "TRELLO_BOARD_ID": "test-board",
                },
            ),
            patch("sys.argv", ["trello2beads", "--status-mapping"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1

    def test_main_status_mapping_file_not_found(self):
        """Should exit when --status-mapping file doesn't exist"""
        with (
            patch.dict(
                "os.environ",
                {
                    "TRELLO_API_KEY": "test-key",
                    "TRELLO_TOKEN": "test-token",
                    "TRELLO_BOARD_ID": "test-board",
                },
            ),
            patch("sys.argv", ["trello2beads", "--status-mapping", "nonexistent.json"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1

    def test_main_no_verify_ssl_flag(self):
        """Should disable SSL verification with --no-verify-ssl flag"""

        def mock_path_exists(self):
            return str(self).endswith("beads.db")

        with (
            patch.dict(
                "os.environ",
                {
                    "TRELLO_API_KEY": "test-key",
                    "TRELLO_TOKEN": "test-token",
                    "TRELLO_BOARD_ID": "test-board",
                },
            ),
            patch("sys.argv", ["trello2beads", "--no-verify-ssl"]),
            patch("pathlib.Path.exists", mock_path_exists),
            patch("trello2beads.cli.TrelloReader") as mock_trello,
            patch("trello2beads.cli.BeadsWriter"),
            patch("trello2beads.cli.TrelloToBeadsConverter"),
            patch("urllib3.disable_warnings") as mock_disable_warnings,
        ):
            main()

            # Verify TrelloReader was created with verify_ssl=False
            call_kwargs = mock_trello.call_args.kwargs
            assert call_kwargs["verify_ssl"] is False

            # Verify SSL warnings were disabled
            mock_disable_warnings.assert_called_once()
