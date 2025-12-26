"""
Comprehensive unit tests for TrelloReader (Trello API client)

Consolidated from:
- test_board_discovery.py
- test_list_boards.py
- test_enhanced_card_reading.py
- test_pagination.py
- test_url_resolution.py
- test_retry_logic.py
"""

import sys
from pathlib import Path

# Add parent directory to path to import trello2beads module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import re
from unittest.mock import MagicMock, patch

import pytest
import requests

from trello2beads import (
    TrelloAPIError,
    TrelloAuthenticationError,
    TrelloNotFoundError,
    TrelloRateLimitError,
    TrelloReader,
    TrelloServerError,
)

# ===== Board URL Parsing Tests (from test_board_discovery.py) =====


class TestBoardURLParsing:
    """Test parse_board_url() static method"""

    def test_parse_full_https_url(self):
        """Should extract board ID from full HTTPS URL"""
        url = "https://trello.com/b/Bm0nnz1R/my-board-name"
        board_id = TrelloReader.parse_board_url(url)
        assert board_id == "Bm0nnz1R"

    def test_parse_full_http_url(self):
        """Should extract board ID from HTTP URL"""
        url = "http://trello.com/b/ABC123XY/test-board"
        board_id = TrelloReader.parse_board_url(url)
        assert board_id == "ABC123XY"

    def test_parse_url_without_protocol(self):
        """Should extract board ID from URL without protocol"""
        url = "trello.com/b/XYZ789AB/board"
        board_id = TrelloReader.parse_board_url(url)
        assert board_id == "XYZ789AB"

    def test_parse_url_without_board_name(self):
        """Should extract board ID from URL without board name"""
        url = "https://trello.com/b/12345678"
        board_id = TrelloReader.parse_board_url(url)
        assert board_id == "12345678"

    def test_parse_url_with_trailing_slash(self):
        """Should handle URLs with trailing slash"""
        url = "https://trello.com/b/ABCD1234/"
        board_id = TrelloReader.parse_board_url(url)
        assert board_id == "ABCD1234"

    def test_parse_url_with_query_params(self):
        """Should extract board ID even with query parameters"""
        url = "https://trello.com/b/TEST123A/board?menu=filter&filter=members"
        board_id = TrelloReader.parse_board_url(url)
        assert board_id == "TEST123A"

    def test_parse_url_with_mixed_case(self):
        """Should handle mixed case board IDs"""
        url = "https://trello.com/b/AbCd1234/board-name"
        board_id = TrelloReader.parse_board_url(url)
        assert board_id == "AbCd1234"

    def test_parse_url_alphanumeric_id(self):
        """Should handle alphanumeric board IDs"""
        url = "https://trello.com/b/aB12cD34/board"
        board_id = TrelloReader.parse_board_url(url)
        assert board_id == "aB12cD34"

    def test_parse_empty_url_raises_error(self):
        """Should raise ValueError for empty URL"""
        with pytest.raises(ValueError, match="URL cannot be empty"):
            TrelloReader.parse_board_url("")

    def test_parse_none_url_raises_error(self):
        """Should raise ValueError for None URL"""
        with pytest.raises(ValueError, match="URL cannot be empty"):
            TrelloReader.parse_board_url(None)  # type: ignore

    def test_parse_invalid_url_raises_error(self):
        """Should raise ValueError for invalid URL"""
        with pytest.raises(ValueError, match="Could not extract board ID"):
            TrelloReader.parse_board_url("https://example.com/not-trello")

    def test_parse_card_url_raises_error(self):
        """Should raise ValueError for card URL (not a board URL)"""
        with pytest.raises(ValueError, match="Could not extract board ID"):
            TrelloReader.parse_board_url("https://trello.com/c/ABC12345/card-name")

    def test_parse_workspace_url_raises_error(self):
        """Should raise ValueError for workspace URL"""
        with pytest.raises(ValueError, match="Could not extract board ID"):
            TrelloReader.parse_board_url("https://trello.com/w/myworkspace")

    def test_parse_url_with_subdomain(self):
        """Should handle URLs with www subdomain"""
        url = "https://www.trello.com/b/TEST1234/board"
        board_id = TrelloReader.parse_board_url(url)
        assert board_id == "TEST1234"


class TestTrelloReaderInit:
    """Test TrelloReader initialization with board_id vs board_url"""

    def test_init_with_board_id(self):
        """Should initialize successfully with board_id"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="ABCD1234")
        assert reader.board_id == "ABCD1234"

    def test_init_with_board_url(self):
        """Should initialize successfully with board_url and extract ID"""
        reader = TrelloReader(
            api_key="test_key",
            token="test_token",
            board_url="https://trello.com/b/XYZ789AB/my-board",
        )
        assert reader.board_id == "XYZ789AB"

    def test_init_with_both_board_id_and_url(self):
        """Should prefer board_url when both are provided"""
        reader = TrelloReader(
            api_key="test_key",
            token="test_token",
            board_id="OLD123",
            board_url="https://trello.com/b/NEW456/board",
        )
        # board_url takes precedence
        assert reader.board_id == "NEW456"

    def test_init_without_board_identifier_succeeds(self):
        """Should succeed without board_id (for list_boards use case)"""
        reader = TrelloReader(api_key="test_key", token="test_token")

        # Should initialize successfully with board_id=None
        assert reader.board_id is None

        # But board-specific methods should raise an error
        with pytest.raises(ValueError, match="board_id is required"):
            reader.get_board()

    def test_init_with_invalid_board_url_raises_error(self):
        """Should raise ValueError when board_url is invalid"""
        with pytest.raises(ValueError, match="Could not extract board ID"):
            TrelloReader(
                api_key="test_key",
                token="test_token",
                board_url="https://example.com/invalid",
            )


class TestBoardURLExamples:
    """Test real-world Trello board URL examples"""

    def test_public_board_url(self):
        """Should parse typical public board URL"""
        url = "https://trello.com/b/nC8QJJoZ/trello-development-roadmap"
        board_id = TrelloReader.parse_board_url(url)
        assert board_id == "nC8QJJoZ"

    def test_short_board_url(self):
        """Should parse board URL with minimal name"""
        url = "https://trello.com/b/a1B2c3D4/x"
        board_id = TrelloReader.parse_board_url(url)
        assert board_id == "a1B2c3D4"

    def test_board_url_with_dashes_in_name(self):
        """Should handle board names with multiple dashes"""
        url = "https://trello.com/b/TEST1234/my-super-long-board-name-with-dashes"
        board_id = TrelloReader.parse_board_url(url)
        assert board_id == "TEST1234"

    def test_board_url_with_numbers_in_name(self):
        """Should handle board names with numbers"""
        url = "https://trello.com/b/ABC12345/q4-2024-planning"
        board_id = TrelloReader.parse_board_url(url)
        assert board_id == "ABC12345"

    def test_board_url_from_mobile(self):
        """Should handle URLs from Trello mobile app (same format)"""
        url = "https://trello.com/b/MOB1234A/mobile-board"
        board_id = TrelloReader.parse_board_url(url)
        assert board_id == "MOB1234A"


# ===== List Boards Tests (from test_list_boards.py) =====


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


# ===== enhanced_card_reading Tests (from test_enhanced_card_reading.py) =====


class TestEnhancedCardReading:
    """Test get_cards() with full relationship data"""

    def test_get_cards_includes_all_relationships(self):
        """Should request all relationship fields: attachments, checklists, members, customFieldItems, stickers"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        mock_response = [
            {
                "id": "card1",
                "name": "Test Card",
                "attachments": [{"id": "att1", "name": "file.pdf"}],
                "checklists": [{"id": "check1", "name": "Checklist"}],
                "members": [{"id": "mem1", "fullName": "John Doe"}],
                "customFieldItems": [{"id": "cf1", "value": {"text": "Value"}}],
                "stickers": [{"id": "sticker1", "image": "thumbsup"}],
            }
        ]

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
        ):
            # Mock the response
            mock_get_response = MagicMock()
            mock_get_response.json.return_value = mock_response
            mock_get_response.raise_for_status.return_value = None
            mock_get.return_value = mock_get_response

            result = reader.get_cards()

            # Verify the API was called with correct parameters
            assert mock_get.call_count == 1
            call_args = mock_get.call_args
            params = call_args[1]["params"]

            # Check all relationship parameters are included
            assert params["attachments"] == "true"
            assert params["checklists"] == "all"
            assert params["members"] == "true"
            assert params["customFieldItems"] == "true"
            assert params["stickers"] == "true"
            assert params["fields"] == "all"

            # Verify response structure
            assert len(result) == 1
            assert result[0]["id"] == "card1"
            assert "attachments" in result[0]
            assert "checklists" in result[0]
            assert "members" in result[0]
            assert "customFieldItems" in result[0]
            assert "stickers" in result[0]

    def test_get_cards_with_empty_relationships(self):
        """Should handle cards with no relationships gracefully"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        mock_response = [
            {
                "id": "card2",
                "name": "Simple Card",
                "attachments": [],
                "checklists": [],
                "members": [],
                "customFieldItems": [],
                "stickers": [],
            }
        ]

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
        ):
            mock_get_response = MagicMock()
            mock_get_response.json.return_value = mock_response
            mock_get_response.raise_for_status.return_value = None
            mock_get.return_value = mock_get_response

            result = reader.get_cards()

            assert len(result) == 1
            assert result[0]["id"] == "card2"
            # Empty arrays should be present
            assert result[0]["attachments"] == []
            assert result[0]["members"] == []

    def test_get_cards_with_multiple_members(self):
        """Should handle cards with multiple assigned members"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        mock_response = [
            {
                "id": "card3",
                "name": "Team Card",
                "members": [
                    {"id": "mem1", "fullName": "Alice", "username": "alice"},
                    {"id": "mem2", "fullName": "Bob", "username": "bob"},
                    {"id": "mem3", "fullName": "Charlie", "username": "charlie"},
                ],
            }
        ]

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
        ):
            mock_get_response = MagicMock()
            mock_get_response.json.return_value = mock_response
            mock_get_response.raise_for_status.return_value = None
            mock_get.return_value = mock_get_response

            result = reader.get_cards()

            assert len(result[0]["members"]) == 3
            assert result[0]["members"][0]["fullName"] == "Alice"
            assert result[0]["members"][1]["fullName"] == "Bob"
            assert result[0]["members"][2]["fullName"] == "Charlie"

    def test_get_cards_with_custom_fields(self):
        """Should handle cards with various custom field types"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        mock_response = [
            {
                "id": "card4",
                "name": "Card with Custom Fields",
                "customFieldItems": [
                    {"idCustomField": "cf1", "value": {"text": "Text value"}},
                    {"idCustomField": "cf2", "value": {"number": "42"}},
                    {"idCustomField": "cf3", "value": {"checked": "true"}},
                    {"idCustomField": "cf4", "value": {"date": "2025-01-01T00:00:00.000Z"}},
                ],
            }
        ]

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
        ):
            mock_get_response = MagicMock()
            mock_get_response.json.return_value = mock_response
            mock_get_response.raise_for_status.return_value = None
            mock_get.return_value = mock_get_response

            result = reader.get_cards()

            custom_fields = result[0]["customFieldItems"]
            assert len(custom_fields) == 4
            # Verify different field types are present
            assert custom_fields[0]["value"]["text"] == "Text value"
            assert custom_fields[1]["value"]["number"] == "42"
            assert custom_fields[2]["value"]["checked"] == "true"

    def test_get_cards_with_stickers(self):
        """Should handle cards with stickers"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        mock_response = [
            {
                "id": "card5",
                "name": "Card with Stickers",
                "stickers": [
                    {"id": "sticker1", "image": "thumbsup", "top": 10, "left": 20},
                    {"id": "sticker2", "image": "heart", "top": 50, "left": 60},
                ],
            }
        ]

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
        ):
            mock_get_response = MagicMock()
            mock_get_response.json.return_value = mock_response
            mock_get_response.raise_for_status.return_value = None
            mock_get.return_value = mock_get_response

            result = reader.get_cards()

            stickers = result[0]["stickers"]
            assert len(stickers) == 2
            assert stickers[0]["image"] == "thumbsup"
            assert stickers[1]["image"] == "heart"

    def test_get_cards_pagination_preserves_relationship_params(self):
        """Should maintain all relationship parameters across paginated requests"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        # Create 1000 mock cards for first page (triggers pagination)
        page1 = [{"id": f"card{i}", "name": f"Card {i}"} for i in range(1000)]
        page2 = [{"id": "card1000", "name": "Card 1000"}]

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
        ):
            mock_response1 = MagicMock()
            mock_response1.json.return_value = page1
            mock_response1.raise_for_status.return_value = None

            mock_response2 = MagicMock()
            mock_response2.json.return_value = page2
            mock_response2.raise_for_status.return_value = None

            mock_get.side_effect = [mock_response1, mock_response2]

            result = reader.get_cards()

            # Should have made 2 paginated requests
            assert mock_get.call_count == 2

            # Both requests should have all relationship parameters
            for call in mock_get.call_args_list:
                params = call[1]["params"]
                assert params["attachments"] == "true"
                assert params["checklists"] == "all"
                assert params["members"] == "true"
                assert params["customFieldItems"] == "true"
                assert params["stickers"] == "true"
                assert params["fields"] == "all"
                assert params["limit"] == 1000

            # Verify all cards returned
            assert len(result) == 1001

    def test_get_cards_comprehensive_card_data(self):
        """Should handle a card with all types of relationship data simultaneously"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        mock_response = [
            {
                "id": "comprehensive_card",
                "name": "Comprehensive Test Card",
                "desc": "A card with everything",
                "attachments": [
                    {"id": "att1", "name": "document.pdf", "bytes": 1024},
                    {"id": "att2", "name": "image.png", "bytes": 2048},
                ],
                "checklists": [
                    {
                        "id": "check1",
                        "name": "Tasks",
                        "checkItems": [
                            {"id": "item1", "name": "Task 1", "state": "complete"},
                            {"id": "item2", "name": "Task 2", "state": "incomplete"},
                        ],
                    }
                ],
                "members": [
                    {"id": "mem1", "fullName": "Project Manager", "username": "pm"},
                    {"id": "mem2", "fullName": "Developer", "username": "dev"},
                ],
                "customFieldItems": [
                    {"idCustomField": "cf_priority", "value": {"text": "High"}},
                    {"idCustomField": "cf_estimate", "value": {"number": "8"}},
                ],
                "stickers": [{"id": "sticker_flag", "image": "flag", "top": 0, "left": 0}],
                "labels": [{"id": "label1", "name": "bug", "color": "red"}],
            }
        ]

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
        ):
            mock_get_response = MagicMock()
            mock_get_response.json.return_value = mock_response
            mock_get_response.raise_for_status.return_value = None
            mock_get.return_value = mock_get_response

            result = reader.get_cards()

            card = result[0]
            assert card["id"] == "comprehensive_card"
            assert len(card["attachments"]) == 2
            assert len(card["checklists"]) == 1
            assert len(card["checklists"][0]["checkItems"]) == 2
            assert len(card["members"]) == 2
            assert len(card["customFieldItems"]) == 2
            assert len(card["stickers"]) == 1
            assert len(card["labels"]) == 1


# ===== pagination Tests (from test_pagination.py) =====


class TestPagination:
    """Test pagination logic in TrelloReader"""

    def test_paginated_request_single_page_under_limit(self):
        """Should return all items when less than 1000 items"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="test_board")

        # Mock 500 cards (under limit)
        mock_cards = [{"id": f"card_{i}", "name": f"Card {i}"} for i in range(500)]

        with patch.object(reader, "_request", return_value=mock_cards) as mock_request:
            result = reader._paginated_request("boards/test/cards")

            # Should make only one request
            assert mock_request.call_count == 1
            assert len(result) == 500
            assert result == mock_cards

    def test_paginated_request_single_page_exactly_limit(self):
        """Should handle exactly 1000 items correctly"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="test_board")

        # Mock exactly 1000 cards
        mock_cards = [{"id": f"card_{i}", "name": f"Card {i}"} for i in range(1000)]

        with patch.object(reader, "_request") as mock_request:
            # First call returns 1000 items, second call returns empty
            mock_request.side_effect = [mock_cards, []]

            result = reader._paginated_request("boards/test/cards")

            # Should make two requests (one page + check for more)
            assert mock_request.call_count == 2
            assert len(result) == 1000

            # Verify second request used 'before' parameter
            second_call_params = mock_request.call_args_list[1][0][1]
            assert second_call_params["before"] == "card_999"

    def test_paginated_request_multiple_pages(self):
        """Should paginate correctly across multiple pages"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="test_board")

        # Mock 2500 total cards across 3 pages
        page1 = [{"id": f"card_{i}", "name": f"Card {i}"} for i in range(1000)]
        page2 = [{"id": f"card_{i}", "name": f"Card {i}"} for i in range(1000, 2000)]
        page3 = [{"id": f"card_{i}", "name": f"Card {i}"} for i in range(2000, 2500)]

        with patch.object(reader, "_request") as mock_request:
            mock_request.side_effect = [page1, page2, page3]

            result = reader._paginated_request("boards/test/cards")

            # Should make 3 requests
            assert mock_request.call_count == 3
            assert len(result) == 2500

            # Verify pagination parameters
            # Note: params dict is reused, so we check the sequence of 'before' values
            # First call should have limit but no before initially
            # Subsequent calls add 'before' parameter

            # Check that limit is set for all calls
            for call_args in mock_request.call_args_list:
                params = call_args[0][1]
                assert params["limit"] == 1000

    def test_paginated_request_empty_response(self):
        """Should handle empty response gracefully"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="test_board")

        with patch.object(reader, "_request", return_value=[]) as mock_request:
            result = reader._paginated_request("boards/test/cards")

            assert mock_request.call_count == 1
            assert result == []

    def test_paginated_request_preserves_params(self):
        """Should preserve custom parameters across pages"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="test_board")

        page1 = [{"id": f"card_{i}"} for i in range(1000)]
        page2 = [{"id": f"card_{i}"} for i in range(1000, 1500)]

        with patch.object(reader, "_request") as mock_request:
            mock_request.side_effect = [page1, page2]

            result = reader._paginated_request(
                "boards/test/cards", {"fields": "all", "filter": "open"}
            )

            assert len(result) == 1500

            # Verify custom params preserved in both requests
            for call in mock_request.call_args_list:
                params = call[0][1]
                assert params["fields"] == "all"
                assert params["filter"] == "open"
                assert params["limit"] == 1000

    def test_paginated_request_no_id_field(self):
        """Should stop pagination if items don't have ID field"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="test_board")

        # Mock items without ID field
        mock_items = [{"name": f"Item {i}"} for i in range(1000)]

        with patch.object(reader, "_request", return_value=mock_items) as mock_request:
            result = reader._paginated_request("some/endpoint")

            # Should make only one request (can't paginate without IDs)
            assert mock_request.call_count == 1
            assert len(result) == 1000

    def test_paginated_request_non_list_response(self):
        """Should handle non-list responses gracefully"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="test_board")

        mock_dict = {"key": "value"}

        with patch.object(reader, "_request", return_value=mock_dict) as mock_request:
            result = reader._paginated_request("some/endpoint")

            assert mock_request.call_count == 1
            assert result == mock_dict

    def test_get_cards_uses_pagination(self):
        """get_cards() should use pagination"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="test_board")

        mock_cards = [{"id": f"card_{i}", "name": f"Card {i}"} for i in range(1500)]

        with patch.object(reader, "_paginated_request", return_value=mock_cards) as mock_pag:
            result = reader.get_cards()

            # Should call _paginated_request
            assert mock_pag.called
            assert len(result) == 1500

            # Verify correct endpoint and params
            call_args = mock_pag.call_args
            assert "boards/test_board/cards" in call_args[0][0]
            assert call_args[0][1]["attachments"] == "true"
            assert call_args[0][1]["checklists"] == "all"

    def test_get_card_comments_uses_pagination(self):
        """get_card_comments() should use pagination"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="test_board")

        mock_comments = [
            {"id": f"comment_{i}", "data": {"text": f"Comment {i}"}} for i in range(1200)
        ]

        with patch.object(reader, "_paginated_request", return_value=mock_comments) as mock_pag:
            result = reader.get_card_comments("card123")

            # Should call _paginated_request
            assert mock_pag.called
            assert len(result) == 1200

            # Verify correct endpoint and params
            call_args = mock_pag.call_args
            assert "cards/card123/actions" in call_args[0][0]
            assert call_args[0][1]["filter"] == "commentCard"

    def test_pagination_with_rate_limiting(self):
        """Pagination should work with rate limiting"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="test_board")

        # Mock multiple pages
        page1 = [{"id": f"card_{i}"} for i in range(1000)]
        page2 = [{"id": f"card_{i}"} for i in range(1000, 1500)]

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True) as mock_acquire,
            patch("requests.get") as mock_get,
        ):
            # Mock successful responses
            mock_response = MagicMock()
            mock_response.json.side_effect = [page1, page2]
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            result = reader._paginated_request("boards/test/cards")

            # Should acquire rate limiter token for each page
            assert mock_acquire.call_count == 2
            assert len(result) == 1500

    # ===== url_resolution Tests (from test_url_resolution.py) =====

    # Recreate the pattern from trello2beads.py
    TRELLO_URL_PATTERN = re.compile(r"(?:https?://)?trello\.com/c/([a-zA-Z0-9]+)(?:/[^\s\)]*)?")

    def test_https_full_url(self):
        """Match full HTTPS URL with card name"""
        text = "See https://trello.com/c/abc123/card-name-here"
        match = self.TRELLO_URL_PATTERN.search(text)
        assert match is not None
        assert match.group(0) == "https://trello.com/c/abc123/card-name-here"
        assert match.group(1) == "abc123"  # short link

    def test_http_full_url(self):
        """Match full HTTP URL (less common)"""
        text = "See http://trello.com/c/xyz789/task-details"
        match = self.TRELLO_URL_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "xyz789"

    def test_no_protocol_url(self):
        """Match URL without protocol"""
        text = "Check trello.com/c/def456/review-this"
        match = self.TRELLO_URL_PATTERN.search(text)
        assert match is not None
        assert match.group(0) == "trello.com/c/def456/review-this"
        assert match.group(1) == "def456"

    def test_short_url_no_name(self):
        """Match short URL without card name"""
        text = "See https://trello.com/c/ghi789"
        match = self.TRELLO_URL_PATTERN.search(text)
        assert match is not None
        assert match.group(0) == "https://trello.com/c/ghi789"
        assert match.group(1) == "ghi789"

    def test_url_in_sentence(self):
        """URL embedded in sentence should match"""
        text = "Blocked by https://trello.com/c/jkl012/authentication until completed"
        match = self.TRELLO_URL_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "jkl012"

    def test_url_in_markdown_link(self):
        """URL in markdown link format"""
        text = "See [Auth task](https://trello.com/c/mno345/auth)"
        match = self.TRELLO_URL_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "mno345"

    def test_url_at_end_of_sentence(self):
        """URL at end of sentence (no trailing slash)"""
        text = "Related: https://trello.com/c/pqr678."
        match = self.TRELLO_URL_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "pqr678"

    def test_url_with_dashes_in_name(self):
        """Card name with multiple dashes"""
        text = "https://trello.com/c/stu901/my-long-card-name-with-dashes"
        match = self.TRELLO_URL_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "stu901"

    def test_url_with_numbers_in_name(self):
        """Card name with numbers"""
        text = "https://trello.com/c/vwx234/sprint-2024-q1-tasks"
        match = self.TRELLO_URL_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "vwx234"

    def test_multiple_urls_finditer(self):
        """Multiple URLs in same text"""
        text = "See https://trello.com/c/aaa111 and https://trello.com/c/bbb222 for context"
        matches = list(self.TRELLO_URL_PATTERN.finditer(text))
        assert len(matches) == 2
        assert matches[0].group(1) == "aaa111"
        assert matches[1].group(1) == "bbb222"

    def test_url_in_parentheses(self):
        """URL in parentheses should stop at closing paren"""
        text = "Related task (see https://trello.com/c/ccc333) for details"
        match = self.TRELLO_URL_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "ccc333"
        # Should not include the closing paren
        assert ")" not in match.group(0)

    def test_url_with_whitespace_after(self):
        """URL followed by whitespace"""
        text = "Check https://trello.com/c/ddd444/task and continue"
        match = self.TRELLO_URL_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "ddd444"

    def test_alphanumeric_short_link(self):
        """Short links can be alphanumeric"""
        text = "https://trello.com/c/Ab12Cd34"
        match = self.TRELLO_URL_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "Ab12Cd34"

    def test_case_sensitive_short_link(self):
        """Short links preserve case"""
        text = "https://trello.com/c/XyZ789"
        match = self.TRELLO_URL_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "XyZ789"

    def test_no_match_board_url(self):
        """Board URLs should not match (different format)"""
        text = "https://trello.com/b/boardid123/board-name"
        match = self.TRELLO_URL_PATTERN.search(text)
        assert match is None

    def test_no_match_other_domain(self):
        """Other domains should not match"""
        text = "https://github.com/c/abc123"
        match = self.TRELLO_URL_PATTERN.search(text)
        assert match is None

    def test_no_match_incomplete_url(self):
        """Incomplete Trello URLs should not match"""
        text = "trello.com/abc123"
        match = self.TRELLO_URL_PATTERN.search(text)
        assert match is None

    def test_url_with_query_params_not_matched(self):
        """URLs with query params - pattern doesn't include them"""
        # The pattern stops at whitespace, so query params would be included
        # if there's no whitespace after
        text = "https://trello.com/c/eee555/card?filter=members"
        match = self.TRELLO_URL_PATTERN.search(text)
        # This will match up to the query param
        assert match is not None
        assert match.group(1) == "eee555"


class TestURLReplacement:
    """Test URL replacement logic"""

    @staticmethod
    def replace_trello_urls(text: str, url_map: dict) -> str:
        """
        Simulate URL replacement logic from trello2beads.py

        Args:
            text: Text containing Trello URLs
            url_map: Mapping of short_link -> beads_id

        Returns:
            Text with Trello URLs replaced by beads references
        """
        import re

        pattern = re.compile(r"(?:https?://)?trello\.com/c/([a-zA-Z0-9]+)(?:/[^\s\)]*)?")

        result = text
        for match in pattern.finditer(text):
            full_url = match.group(0)
            short_link = match.group(1)

            if short_link in url_map:
                beads_ref = f"See {url_map[short_link]}"
                result = result.replace(full_url, beads_ref)

        return result

    def test_single_url_replacement(self):
        """Replace single Trello URL with beads reference"""
        text = "Check https://trello.com/c/abc123/auth-task for details"
        url_map = {"abc123": "myproject-xyz"}

        result = self.replace_trello_urls(text, url_map)
        assert result == "Check See myproject-xyz for details"

    def test_multiple_url_replacement(self):
        """Replace multiple Trello URLs"""
        text = "See https://trello.com/c/abc123 and https://trello.com/c/def456"
        url_map = {"abc123": "myproject-111", "def456": "myproject-222"}

        result = self.replace_trello_urls(text, url_map)
        assert result == "See See myproject-111 and See myproject-222"

    def test_url_not_in_map_unchanged(self):
        """URLs not in map should remain unchanged"""
        text = "Check https://trello.com/c/unknown123"
        url_map = {"abc123": "myproject-xyz"}

        result = self.replace_trello_urls(text, url_map)
        assert result == text  # Unchanged

    def test_partial_replacement(self):
        """Mix of known and unknown URLs"""
        text = "See https://trello.com/c/known and https://trello.com/c/unknown"
        url_map = {"known": "myproject-123"}

        result = self.replace_trello_urls(text, url_map)
        assert "See myproject-123" in result
        assert "https://trello.com/c/unknown" in result

    def test_replacement_with_card_name(self):
        """Replace URL that includes card name"""
        text = "Blocked by https://trello.com/c/abc123/implement-authentication"
        url_map = {"abc123": "myproject-auth"}

        result = self.replace_trello_urls(text, url_map)
        assert result == "Blocked by See myproject-auth"

    def test_no_protocol_replacement(self):
        """Replace URL without protocol"""
        text = "See trello.com/c/xyz789/task"
        url_map = {"xyz789": "myproject-task"}

        result = self.replace_trello_urls(text, url_map)
        assert result == "See See myproject-task"

    def test_empty_text(self):
        """Empty text should remain empty"""
        result = self.replace_trello_urls("", {"abc": "xyz"})
        assert result == ""

    def test_empty_map(self):
        """Empty map means no replacements"""
        text = "See https://trello.com/c/abc123"
        result = self.replace_trello_urls(text, {})
        assert result == text

    def test_replacement_in_markdown(self):
        """Replace URLs in markdown links"""
        text = "[Auth Task](https://trello.com/c/auth001/authentication)"
        url_map = {"auth001": "myproject-auth"}

        result = self.replace_trello_urls(text, url_map)
        assert result == "[Auth Task](See myproject-auth)"

    def test_case_sensitive_short_link_lookup(self):
        """Short link lookup is case-sensitive"""
        text = "https://trello.com/c/AbC123"
        url_map = {"abc123": "myproject-lower"}  # Lowercase key

        result = self.replace_trello_urls(text, url_map)
        # Should NOT match because case differs
        assert result == text

    def test_case_exact_match_required(self):
        """Exact case match required for replacement"""
        text = "https://trello.com/c/XyZ789"
        url_map = {"XyZ789": "myproject-exact"}  # Exact case

        result = self.replace_trello_urls(text, url_map)
        assert result == "See myproject-exact"

    def test_multiple_references_to_same_card(self):
        """Multiple references to same card all replaced"""
        text = "See https://trello.com/c/abc123 and also https://trello.com/c/abc123 again"
        url_map = {"abc123": "myproject-task"}

        result = self.replace_trello_urls(text, url_map)
        assert result.count("See myproject-task") == 2

    def test_url_in_comment_format(self):
        """URL in comment-style text"""
        text = "Don't forget to check trello.com/c/abc123 before starting"
        url_map = {"abc123": "myproject-prereq"}

        result = self.replace_trello_urls(text, url_map)
        assert result == "Don't forget to check See myproject-prereq before starting"

    def test_url_at_paragraph_end(self):
        """URL at end of paragraph"""
        text = "Related to authentication.\nhttps://trello.com/c/auth999"
        url_map = {"auth999": "myproject-auth"}

        result = self.replace_trello_urls(text, url_map)
        assert "See myproject-auth" in result

    def test_multiline_text_with_urls(self):
        """Multiple lines with URLs"""
        text = """First task: https://trello.com/c/task001
Second task: https://trello.com/c/task002
Third task: https://trello.com/c/task003"""
        url_map = {"task001": "myproject-t1", "task002": "myproject-t2", "task003": "myproject-t3"}

        result = self.replace_trello_urls(text, url_map)
        assert "See myproject-t1" in result
        assert "See myproject-t2" in result
        assert "See myproject-t3" in result


class TestAttachmentURLHandling:
    """Test handling of Trello URLs in attachments"""

    def test_attachment_url_extraction(self):
        """Extract short link from attachment URL"""
        pattern = re.compile(r"(?:https?://)?trello\.com/c/([a-zA-Z0-9]+)(?:/[^\s\)]*)?")

        attachment_url = "https://trello.com/c/ref003/database-schema"
        match = pattern.search(attachment_url)

        assert match is not None
        assert match.group(1) == "ref003"

    def test_attachment_url_without_name(self):
        """Attachment URL without card name"""
        pattern = re.compile(r"(?:https?://)?trello\.com/c/([a-zA-Z0-9]+)(?:/[^\s\)]*)?")

        attachment_url = "https://trello.com/c/att123"
        match = pattern.search(attachment_url)

        assert match is not None
        assert match.group(1) == "att123"

    def test_non_trello_attachment_url(self):
        """Non-Trello attachment URLs should not match"""
        pattern = re.compile(r"(?:https?://)?trello\.com/c/([a-zA-Z0-9]+)(?:/[^\s\)]*)?")

        attachment_url = "https://docs.google.com/document/123"
        match = pattern.search(attachment_url)

        assert match is None


class TestEdgeCases:
    """Test edge cases and corner scenarios"""

    def test_url_with_special_chars_after(self):
        """URL followed by special characters"""
        pattern = re.compile(r"(?:https?://)?trello\.com/c/([a-zA-Z0-9]+)(?:/[^\s\)]*)?")

        test_cases = [
            ("https://trello.com/c/abc123.", "abc123"),
            ("https://trello.com/c/abc123,", "abc123"),
            ("https://trello.com/c/abc123;", "abc123"),
            ("https://trello.com/c/abc123!", "abc123"),
            ("https://trello.com/c/abc123?", "abc123"),
        ]

        for text, expected_link in test_cases:
            match = pattern.search(text)
            assert match is not None, f"Should match: {text}"
            assert match.group(1) == expected_link

    def test_very_long_card_name(self):
        """Very long card names should still work"""
        pattern = re.compile(r"(?:https?://)?trello\.com/c/([a-zA-Z0-9]+)(?:/[^\s\)]*)?")

        url = "https://trello.com/c/abc123/this-is-a-very-long-card-name-with-many-words-and-dashes"
        match = pattern.search(url)

        assert match is not None
        assert match.group(1) == "abc123"

    def test_unicode_in_surrounding_text(self):
        """Unicode characters in surrounding text"""
        pattern = re.compile(r"(?:https?://)?trello\.com/c/([a-zA-Z0-9]+)(?:/[^\s\)]*)?")

        text = "Related: https://trello.com/c/abc123 ✓ Done"
        match = pattern.search(text)

        assert match is not None
        assert match.group(1) == "abc123"

    def test_url_only_text(self):
        """Text containing only a URL"""
        pattern = re.compile(r"(?:https?://)?trello\.com/c/([a-zA-Z0-9]+)(?:/[^\s\)]*)?")

        text = "https://trello.com/c/abc123"
        match = pattern.search(text)

        assert match is not None
        assert match.group(0) == text
        assert match.group(1) == "abc123"

    def test_url_with_fragment(self):
        """URL with fragment identifier"""
        pattern = re.compile(r"(?:https?://)?trello\.com/c/([a-zA-Z0-9]+)(?:/[^\s\)]*)?")

        # Fragment would be included in the card name part
        text = "https://trello.com/c/abc123/card#comment-123"
        match = pattern.search(text)

        assert match is not None
        assert match.group(1) == "abc123"


# ===== retry_logic Tests (from test_retry_logic.py) =====


class TestRetryLogic:
    """Test retry logic and exponential backoff in TrelloReader"""

    def test_successful_request_no_retry(self):
        """Should succeed on first attempt without retrying"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "test", "name": "Test Board"}
        mock_response.raise_for_status.return_value = None

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", return_value=mock_response) as mock_get,
        ):
            result = reader._request("boards/TEST1234")

            # Should make only one request
            assert mock_get.call_count == 1
            assert result == {"id": "test", "name": "Test Board"}

    def test_retry_on_429_rate_limit(self):
        """Should retry on 429 (rate limit) with exponential backoff"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        # First two attempts return 429, third succeeds
        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.raise_for_status.side_effect = requests.HTTPError(response=response_429)

        response_success = MagicMock()
        response_success.json.return_value = {"success": True}
        response_success.raise_for_status.return_value = None

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
            patch("time.sleep") as mock_sleep,  # Mock sleep to speed up test
        ):
            mock_get.side_effect = [
                response_429,  # Attempt 1: fail
                response_429,  # Attempt 2: fail
                response_success,  # Attempt 3: success
            ]

            result = reader._request("boards/TEST1234")

            # Should have retried 3 times
            assert mock_get.call_count == 3
            assert result == {"success": True}

            # Should have slept with exponential backoff (1s, 2s)
            assert mock_sleep.call_count == 2
            assert mock_sleep.call_args_list[0][0][0] == 1.0  # 1s delay
            assert mock_sleep.call_args_list[1][0][0] == 2.0  # 2s delay

    def test_retry_on_500_server_error(self):
        """Should retry on 500 (internal server error)"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_500 = MagicMock()
        response_500.status_code = 500
        response_500.raise_for_status.side_effect = requests.HTTPError(response=response_500)

        response_success = MagicMock()
        response_success.json.return_value = {"recovered": True}
        response_success.raise_for_status.return_value = None

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
            patch("time.sleep") as mock_sleep,
        ):
            mock_get.side_effect = [response_500, response_success]

            result = reader._request("boards/TEST1234")

            assert mock_get.call_count == 2
            assert result == {"recovered": True}
            assert mock_sleep.call_count == 1  # Slept once between attempts

    def test_retry_on_503_service_unavailable(self):
        """Should retry on 503 (service unavailable)"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_503 = MagicMock()
        response_503.status_code = 503
        response_503.raise_for_status.side_effect = requests.HTTPError(response=response_503)

        response_success = MagicMock()
        response_success.json.return_value = {"recovered": True}
        response_success.raise_for_status.return_value = None

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
            patch("time.sleep"),
        ):
            mock_get.side_effect = [response_503, response_success]

            result = reader._request("boards/TEST1234")

            assert mock_get.call_count == 2
            assert result == {"recovered": True}

    def test_no_retry_on_401_unauthorized(self):
        """Should NOT retry on 401 (unauthorized) - non-transient error"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_401 = MagicMock()
        response_401.status_code = 401
        response_401.text = "Unauthorized"
        response_401.raise_for_status.side_effect = requests.HTTPError(response=response_401)

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", return_value=response_401) as mock_get,
        ):
            with pytest.raises(TrelloAuthenticationError):
                reader._request("boards/TEST1234")

            # Should NOT retry - only one attempt
            assert mock_get.call_count == 1

    def test_no_retry_on_404_not_found(self):
        """Should NOT retry on 404 (not found) - non-transient error"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_404 = MagicMock()
        response_404.status_code = 404
        response_404.text = "Not Found"
        response_404.raise_for_status.side_effect = requests.HTTPError(response=response_404)

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", return_value=response_404) as mock_get,
        ):
            with pytest.raises(TrelloNotFoundError):
                reader._request("boards/TEST1234")

            # Should NOT retry - only one attempt
            assert mock_get.call_count == 1

    def test_exhaust_all_retries(self):
        """Should raise exception after exhausting all retries"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_503 = MagicMock()
        response_503.status_code = 503
        response_503.text = "Service Unavailable"
        response_503.raise_for_status.side_effect = requests.HTTPError(response=response_503)

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", return_value=response_503) as mock_get,
            patch("time.sleep") as mock_sleep,
        ):
            with pytest.raises(TrelloServerError):
                reader._request("boards/TEST1234")

            # Should have tried 3 times (max retries)
            assert mock_get.call_count == 3

            # Should have slept between attempts (not after last)
            assert mock_sleep.call_count == 2

    def test_exponential_backoff_delays(self):
        """Should use exponential backoff: 1s, 2s, 4s"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.text = "Too Many Requests"
        response_429.raise_for_status.side_effect = requests.HTTPError(response=response_429)

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", return_value=response_429),
            patch("time.sleep") as mock_sleep,
        ):
            with pytest.raises(TrelloRateLimitError):
                reader._request("boards/TEST1234")

            # Check exponential backoff delays: 1s, 2s
            assert mock_sleep.call_count == 2
            assert mock_sleep.call_args_list[0][0][0] == 1.0  # 2^0 = 1s
            assert mock_sleep.call_args_list[1][0][0] == 2.0  # 2^1 = 2s

    def test_retry_on_network_timeout(self):
        """Should retry on network timeout (RequestException)"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_success = MagicMock()
        response_success.json.return_value = {"recovered": True}
        response_success.raise_for_status.return_value = None

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
            patch("time.sleep") as mock_sleep,
        ):
            mock_get.side_effect = [
                requests.Timeout("Connection timeout"),
                response_success,
            ]

            result = reader._request("boards/TEST1234")

            assert mock_get.call_count == 2
            assert result == {"recovered": True}
            assert mock_sleep.call_count == 1

    def test_retry_on_connection_error(self):
        """Should retry on connection error"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_success = MagicMock()
        response_success.json.return_value = {"recovered": True}
        response_success.raise_for_status.return_value = None

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
            patch("time.sleep"),
        ):
            mock_get.side_effect = [
                requests.ConnectionError("Network unreachable"),
                response_success,
            ]

            result = reader._request("boards/TEST1234")

            assert mock_get.call_count == 2
            assert result == {"recovered": True}

    def test_retry_exhaustion_on_network_error(self):
        """Should raise after exhausting retries on persistent network errors"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
            patch("time.sleep"),
        ):
            mock_get.side_effect = requests.Timeout("Persistent timeout")

            with pytest.raises(TrelloAPIError):
                reader._request("boards/TEST1234")

            # Should have tried 3 times
            assert mock_get.call_count == 3

    def test_retry_preserves_request_params(self):
        """Should preserve all request parameters across retries"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.raise_for_status.side_effect = requests.HTTPError(response=response_429)

        response_success = MagicMock()
        response_success.json.return_value = {"success": True}
        response_success.raise_for_status.return_value = None

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
            patch("time.sleep"),
        ):
            mock_get.side_effect = [response_429, response_success]

            reader._request("boards/TEST1234/cards", {"fields": "all", "limit": 1000})

            # Check that all calls had the same parameters
            assert mock_get.call_count == 2
            for call in mock_get.call_args_list:
                params = call[1]["params"]
                assert params["fields"] == "all"
                assert params["limit"] == 1000
                assert params["key"] == "test_key"
                assert params["token"] == "test_token"
