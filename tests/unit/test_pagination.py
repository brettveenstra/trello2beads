"""
Unit tests for pagination support in TrelloReader
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directory to path to import trello2beads module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from trello2beads import TrelloReader


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
