"""
Unit tests for enhanced card reading with full relationships
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directory to path to import trello2beads module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from trello2beads import TrelloReader


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
