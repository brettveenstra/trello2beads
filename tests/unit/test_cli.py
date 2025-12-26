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
