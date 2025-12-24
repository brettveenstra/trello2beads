"""
Unit tests for list_boards() functionality
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path to import trello2beads module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from trello2beads import TrelloReader


class TestListBoards:
    """Test list_boards() method"""

    def test_list_boards_default_open_filter(self):
        """Should list open boards by default"""
        # No board_id required for list_boards()
        reader = TrelloReader(api_key="test_key", token="test_token")

        mock_boards = [
            {
                "id": "board1",
                "name": "Active Board 1",
                "url": "https://trello.com/b/board1/active-board-1",
                "closed": False,
                "dateLastActivity": "2025-12-24T00:00:00.000Z",
            },
            {
                "id": "board2",
                "name": "Active Board 2",
                "url": "https://trello.com/b/board2/active-board-2",
                "closed": False,
                "dateLastActivity": "2025-12-23T00:00:00.000Z",
            },
        ]

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = mock_boards
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            result = reader.list_boards()

            # Should call /members/me/boards with filter=open
            assert mock_get.call_count == 1
            call_args = mock_get.call_args
            params = call_args[1]["params"]
            assert params["filter"] == "open"
            assert params["fields"] == "name,url,closed,dateLastActivity"

            # Verify results
            assert len(result) == 2
            assert result[0]["name"] == "Active Board 1"
            assert result[1]["name"] == "Active Board 2"

    def test_list_boards_with_closed_filter(self):
        """Should list closed (archived) boards when filter_status='closed'"""
        reader = TrelloReader(api_key="test_key", token="test_token")

        mock_boards = [
            {
                "id": "archived1",
                "name": "Archived Board",
                "url": "https://trello.com/b/archived1/archived-board",
                "closed": True,
                "dateLastActivity": "2024-01-01T00:00:00.000Z",
            }
        ]

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = mock_boards
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            result = reader.list_boards(filter_status="closed")

            params = mock_get.call_args[1]["params"]
            assert params["filter"] == "closed"
            assert len(result) == 1
            assert result[0]["closed"] is True

    def test_list_boards_with_all_filter(self):
        """Should list all boards (open and closed) when filter_status='all'"""
        reader = TrelloReader(api_key="test_key", token="test_token")

        mock_boards = [
            {"id": "open1", "name": "Open Board", "closed": False},
            {"id": "closed1", "name": "Closed Board", "closed": True},
        ]

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = mock_boards
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            result = reader.list_boards(filter_status="all")

            params = mock_get.call_args[1]["params"]
            assert params["filter"] == "all"
            assert len(result) == 2

    def test_list_boards_invalid_filter_raises_error(self):
        """Should raise ValueError for invalid filter_status"""
        reader = TrelloReader(api_key="test_key", token="test_token")

        with pytest.raises(ValueError) as exc_info:
            reader.list_boards(filter_status="invalid")

        assert "Invalid filter_status" in str(exc_info.value)
        assert "invalid" in str(exc_info.value)
        assert "open" in str(exc_info.value)
        assert "closed" in str(exc_info.value)
        assert "all" in str(exc_info.value)

    def test_list_boards_empty_result(self):
        """Should handle empty board list gracefully"""
        reader = TrelloReader(api_key="test_key", token="test_token")

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = []
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            result = reader.list_boards()

            assert result == []

    def test_list_boards_without_board_id(self):
        """Should work without board_id initialization"""
        # This is the key feature - list_boards() doesn't need board_id
        reader = TrelloReader(api_key="test_key", token="test_token")

        assert reader.board_id is None

        mock_boards = [{"id": "board1", "name": "Board 1"}]

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = mock_boards
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            result = reader.list_boards()

            # Should succeed despite no board_id
            assert len(result) == 1

    def test_list_boards_includes_all_fields(self):
        """Should include all requested fields in response"""
        reader = TrelloReader(api_key="test_key", token="test_token")

        mock_boards = [
            {
                "id": "ABC12345",
                "name": "My Project Board",
                "url": "https://trello.com/b/ABC12345/my-project-board",
                "closed": False,
                "dateLastActivity": "2025-12-24T12:34:56.789Z",
            }
        ]

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = mock_boards
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            result = reader.list_boards()

            board = result[0]
            assert "id" in board
            assert "name" in board
            assert "url" in board
            assert "closed" in board
            assert "dateLastActivity" in board


class TestBoardIdRequirement:
    """Test that board_id is required for board-specific methods"""

    def test_get_board_requires_board_id(self):
        """Should raise ValueError when get_board() called without board_id"""
        reader = TrelloReader(api_key="test_key", token="test_token")

        with pytest.raises(ValueError) as exc_info:
            reader.get_board()

        assert "board_id is required" in str(exc_info.value)
        assert "Initialize TrelloReader" in str(exc_info.value)

    def test_get_lists_requires_board_id(self):
        """Should raise ValueError when get_lists() called without board_id"""
        reader = TrelloReader(api_key="test_key", token="test_token")

        with pytest.raises(ValueError) as exc_info:
            reader.get_lists()

        assert "board_id is required" in str(exc_info.value)

    def test_get_cards_requires_board_id(self):
        """Should raise ValueError when get_cards() called without board_id"""
        reader = TrelloReader(api_key="test_key", token="test_token")

        with pytest.raises(ValueError) as exc_info:
            reader.get_cards()

        assert "board_id is required" in str(exc_info.value)

    def test_board_specific_methods_work_with_board_id(self):
        """Should work normally when board_id is provided"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        assert reader.board_id == "TEST1234"

        # These should not raise ValueError (though they'll fail in other ways without mocks)
        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "TEST1234", "name": "Test"}
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            # Should succeed with board_id set
            result = reader.get_board()
            assert result["id"] == "TEST1234"
