"""
Unit tests for board discovery and URL parsing
"""

import sys
from pathlib import Path

import pytest

# Add parent directory to path to import trello2beads module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from trello2beads import TrelloReader


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

    def test_init_without_board_identifier_raises_error(self):
        """Should raise ValueError when neither board_id nor board_url provided"""
        with pytest.raises(ValueError, match="Either board_id or board_url must be provided"):
            TrelloReader(api_key="test_key", token="test_token")

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
