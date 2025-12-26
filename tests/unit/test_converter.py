"""
Unit tests for TrelloToBeadsConverter class

Tests cover:
- Basic card-to-issue conversion (title, description, status, labels)
- List-to-status mapping integration
- Trello-to-beads ID mapping
- Card URL mapping for reference resolution
- Dry-run mode
- Snapshot loading and saving
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directory to path to import trello2beads module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from trello2beads import BeadsWriter, TrelloReader, TrelloToBeadsConverter


class TestTrelloToBeadsConverter:
    """Test TrelloToBeadsConverter initialization and basic setup"""

    def test_init_with_defaults(self):
        """Should initialize with default status keywords"""
        mock_trello = MagicMock(spec=TrelloReader)
        with patch.object(BeadsWriter, "_check_bd_available"):
            mock_beads = BeadsWriter()

        converter = TrelloToBeadsConverter(mock_trello, mock_beads)

        assert converter.trello is mock_trello
        assert converter.beads is mock_beads
        assert converter.list_map == {}
        assert converter.trello_to_beads == {}
        assert converter.card_url_map == {}
        assert converter.status_keywords == TrelloToBeadsConverter.STATUS_KEYWORDS

    def test_init_with_custom_status_keywords(self):
        """Should accept custom status keyword mapping"""
        mock_trello = MagicMock(spec=TrelloReader)
        with patch.object(BeadsWriter, "_check_bd_available"):
            mock_beads = BeadsWriter()

        custom_keywords = {
            "open": ["new", "planned"],
            "in_progress": ["active"],
            "closed": ["completed"],
            "blocked": ["stuck"],
            "deferred": ["later"],
        }

        converter = TrelloToBeadsConverter(mock_trello, mock_beads, custom_keywords)

        assert converter.status_keywords == custom_keywords
        assert converter.status_keywords != TrelloToBeadsConverter.STATUS_KEYWORDS


class TestBasicCardConversion:
    """Test basic card-to-issue conversion functionality"""

    def test_convert_single_card_minimal(self):
        """Should convert a single card with minimal data"""
        # Setup mocks
        mock_trello = MagicMock(spec=TrelloReader)
        mock_trello.get_board.return_value = {
            "id": "board123",
            "name": "Test Board",
            "url": "https://trello.com/b/abc123",
        }
        mock_trello.get_lists.return_value = [
            {"id": "list1", "name": "To Do", "pos": 1000}
        ]
        mock_trello.get_cards.return_value = [
            {
                "id": "card1",
                "name": "Test Card",
                "desc": "Simple description",
                "idList": "list1",
                "pos": 1000,
                "shortLink": "abc",
                "shortUrl": "https://trello.com/c/abc",
                "labels": [],
                "checklists": [],
                "attachments": [],
            }
        ]

        with patch.object(BeadsWriter, "_check_bd_available"):
            mock_beads = BeadsWriter(dry_run=True)

        converter = TrelloToBeadsConverter(mock_trello, mock_beads)

        # Patch create_issue to track calls
        created_issues = []

        def mock_create_issue(**kwargs):
            issue_id = f"test-{len(created_issues)}"
            created_issues.append({"id": issue_id, **kwargs})
            return issue_id

        with patch.object(converter.beads, "create_issue", side_effect=mock_create_issue):
            converter.convert()

        # Verify issue was created
        assert len(created_issues) == 1
        issue = created_issues[0]

        assert issue["title"] == "Test Card"
        assert issue["description"] == "Simple description"
        assert issue["status"] == "open"  # "To Do" maps to open
        assert "list:To Do" in issue["labels"]
        assert issue["external_ref"] == "trello:abc"
        assert issue["priority"] == 2
        assert issue["issue_type"] == "task"

    def test_convert_card_with_trello_labels(self):
        """Should preserve Trello labels in beads labels"""
        mock_trello = MagicMock(spec=TrelloReader)
        mock_trello.get_board.return_value = {
            "id": "board123",
            "name": "Test Board",
            "url": "https://trello.com/b/abc123",
        }
        mock_trello.get_lists.return_value = [
            {"id": "list1", "name": "Doing", "pos": 1000}
        ]
        mock_trello.get_cards.return_value = [
            {
                "id": "card1",
                "name": "Bug Fix",
                "desc": "Fix the thing",
                "idList": "list1",
                "pos": 1000,
                "shortLink": "xyz",
                "shortUrl": "https://trello.com/c/xyz",
                "labels": [
                    {"name": "urgent", "color": "red"},
                    {"name": "backend", "color": "blue"},
                ],
                "checklists": [],
                "attachments": [],
            }
        ]

        with patch.object(BeadsWriter, "_check_bd_available"):
            mock_beads = BeadsWriter(dry_run=True)

        converter = TrelloToBeadsConverter(mock_trello, mock_beads)

        created_issues = []

        def mock_create_issue(**kwargs):
            issue_id = f"test-{len(created_issues)}"
            created_issues.append({"id": issue_id, **kwargs})
            return issue_id

        with patch.object(converter.beads, "create_issue", side_effect=mock_create_issue):
            converter.convert()

        # Verify labels
        assert len(created_issues) == 1
        issue = created_issues[0]

        assert "list:Doing" in issue["labels"]
        assert "trello-label:urgent" in issue["labels"]
        assert "trello-label:backend" in issue["labels"]
        assert issue["status"] == "in_progress"  # "Doing" maps to in_progress

    def test_convert_multiple_cards_different_lists(self):
        """Should convert multiple cards from different lists with correct status"""
        mock_trello = MagicMock(spec=TrelloReader)
        mock_trello.get_board.return_value = {
            "id": "board123",
            "name": "Test Board",
            "url": "https://trello.com/b/abc123",
        }
        mock_trello.get_lists.return_value = [
            {"id": "list1", "name": "To Do", "pos": 1000},
            {"id": "list2", "name": "Doing", "pos": 2000},
            {"id": "list3", "name": "Done", "pos": 3000},
        ]
        mock_trello.get_cards.return_value = [
            {
                "id": "card1",
                "name": "Card 1",
                "desc": "Description 1",
                "idList": "list1",
                "pos": 1000,
                "shortLink": "a1",
                "shortUrl": "https://trello.com/c/a1",
                "labels": [],
                "checklists": [],
                "attachments": [],
            },
            {
                "id": "card2",
                "name": "Card 2",
                "desc": "Description 2",
                "idList": "list2",
                "pos": 1000,
                "shortLink": "a2",
                "shortUrl": "https://trello.com/c/a2",
                "labels": [],
                "checklists": [],
                "attachments": [],
            },
            {
                "id": "card3",
                "name": "Card 3",
                "desc": "Description 3",
                "idList": "list3",
                "pos": 1000,
                "shortLink": "a3",
                "shortUrl": "https://trello.com/c/a3",
                "labels": [],
                "checklists": [],
                "attachments": [],
            },
        ]

        with patch.object(BeadsWriter, "_check_bd_available"):
            mock_beads = BeadsWriter(dry_run=True)

        converter = TrelloToBeadsConverter(mock_trello, mock_beads)

        created_issues = []

        def mock_create_issue(**kwargs):
            issue_id = f"test-{len(created_issues)}"
            created_issues.append({"id": issue_id, **kwargs})
            return issue_id

        with patch.object(converter.beads, "create_issue", side_effect=mock_create_issue):
            converter.convert()

        # Verify all cards converted with correct status
        assert len(created_issues) == 3

        # Card 1: To Do → open
        assert created_issues[0]["title"] == "Card 1"
        assert created_issues[0]["status"] == "open"
        assert "list:To Do" in created_issues[0]["labels"]

        # Card 2: Doing → in_progress
        assert created_issues[1]["title"] == "Card 2"
        assert created_issues[1]["status"] == "in_progress"
        assert "list:Doing" in created_issues[1]["labels"]

        # Card 3: Done → closed
        assert created_issues[2]["title"] == "Card 3"
        assert created_issues[2]["status"] == "closed"
        assert "list:Done" in created_issues[2]["labels"]

    def test_convert_builds_mapping_structures(self):
        """Should build trello_to_beads and card_url_map during conversion"""
        mock_trello = MagicMock(spec=TrelloReader)
        mock_trello.get_board.return_value = {
            "id": "board123",
            "name": "Test Board",
            "url": "https://trello.com/b/abc123",
        }
        mock_trello.get_lists.return_value = [
            {"id": "list1", "name": "To Do", "pos": 1000}
        ]
        mock_trello.get_cards.return_value = [
            {
                "id": "card1",
                "name": "Test Card",
                "desc": "Description",
                "idList": "list1",
                "pos": 1000,
                "shortLink": "abc123",
                "shortUrl": "https://trello.com/c/abc123",
                "labels": [],
                "checklists": [],
                "attachments": [],
            }
        ]

        with patch.object(BeadsWriter, "_check_bd_available"):
            mock_beads = BeadsWriter(dry_run=True)

        converter = TrelloToBeadsConverter(mock_trello, mock_beads)

        def mock_create_issue(**kwargs):
            return "test-abc"

        with patch.object(converter.beads, "create_issue", side_effect=mock_create_issue):
            converter.convert()

        # Verify mappings built
        assert converter.trello_to_beads["card1"] == "test-abc"
        assert converter.card_url_map["abc123"] == "test-abc"
        assert converter.card_url_map["https://trello.com/c/abc123"] == "test-abc"


class TestDryRunMode:
    """Test dry-run mode doesn't create actual issues"""

    def test_dry_run_no_issues_created(self):
        """Should not create issues in dry-run mode"""
        mock_trello = MagicMock(spec=TrelloReader)
        mock_trello.get_board.return_value = {
            "id": "board123",
            "name": "Test Board",
            "url": "https://trello.com/b/abc123",
        }
        mock_trello.get_lists.return_value = [
            {"id": "list1", "name": "To Do", "pos": 1000}
        ]
        mock_trello.get_cards.return_value = [
            {
                "id": "card1",
                "name": "Test Card",
                "desc": "Description",
                "idList": "list1",
                "pos": 1000,
                "shortLink": "abc",
                "shortUrl": "https://trello.com/c/abc",
                "labels": [],
                "checklists": [],
                "attachments": [],
            }
        ]

        with patch.object(BeadsWriter, "_check_bd_available"):
            mock_beads = BeadsWriter(dry_run=True)

        converter = TrelloToBeadsConverter(mock_trello, mock_beads)

        with patch.object(converter.beads, "create_issue") as mock_create:
            converter.convert(dry_run=True)

            # Should not call create_issue in dry-run mode
            mock_create.assert_not_called()


class TestSnapshotHandling:
    """Test snapshot loading and saving functionality"""

    def test_save_snapshot_after_fetch(self, tmp_path):
        """Should save snapshot after fetching from Trello"""
        snapshot_path = tmp_path / "snapshot.json"

        mock_trello = MagicMock(spec=TrelloReader)
        mock_trello.get_board.return_value = {
            "id": "board123",
            "name": "Test Board",
            "url": "https://trello.com/b/abc123",
        }
        mock_trello.get_lists.return_value = [
            {"id": "list1", "name": "To Do", "pos": 1000}
        ]
        mock_trello.get_cards.return_value = [
            {
                "id": "card1",
                "name": "Test Card",
                "desc": "Description",
                "idList": "list1",
                "pos": 1000,
                "shortLink": "abc",
                "shortUrl": "https://trello.com/c/abc",
                "labels": [],
                "checklists": [],
                "attachments": [],
            }
        ]

        with patch.object(BeadsWriter, "_check_bd_available"):
            mock_beads = BeadsWriter(dry_run=True)

        converter = TrelloToBeadsConverter(mock_trello, mock_beads)

        # Convert with snapshot path
        converter.convert(dry_run=True, snapshot_path=str(snapshot_path))

        # Verify snapshot was saved
        assert snapshot_path.exists()

        with open(snapshot_path) as f:
            snapshot = json.load(f)

        assert snapshot["board"]["name"] == "Test Board"
        assert len(snapshot["lists"]) == 1
        assert len(snapshot["cards"]) == 1
        assert snapshot["cards"][0]["name"] == "Test Card"

    def test_load_existing_snapshot(self, tmp_path):
        """Should load from existing snapshot instead of fetching"""
        snapshot_path = tmp_path / "snapshot.json"

        # Create snapshot file
        snapshot_data = {
            "board": {"id": "board123", "name": "Snapshot Board", "url": "https://url"},
            "lists": [{"id": "list1", "name": "Done", "pos": 1000}],
            "cards": [
                {
                    "id": "card1",
                    "name": "Snapshot Card",
                    "desc": "From snapshot",
                    "idList": "list1",
                    "pos": 1000,
                    "shortLink": "snap",
                    "shortUrl": "https://trello.com/c/snap",
                    "labels": [],
                    "checklists": [],
                    "attachments": [],
                }
            ],
            "comments": {},
            "timestamp": 1234567890,
        }

        with open(snapshot_path, "w") as f:
            json.dump(snapshot_data, f)

        # Mock Trello (should NOT be called)
        mock_trello = MagicMock(spec=TrelloReader)

        with patch.object(BeadsWriter, "_check_bd_available"):
            mock_beads = BeadsWriter(dry_run=True)

        converter = TrelloToBeadsConverter(mock_trello, mock_beads)

        # Convert using snapshot
        converter.convert(dry_run=True, snapshot_path=str(snapshot_path))

        # Verify Trello API was NOT called
        mock_trello.get_board.assert_not_called()
        mock_trello.get_lists.assert_not_called()
        mock_trello.get_cards.assert_not_called()


class TestDescriptionBuilding:
    """Test description building with checklists and attachments"""

    def test_convert_card_with_checklists(self):
        """Should embed checklists in description (markdown format)"""
        mock_trello = MagicMock(spec=TrelloReader)
        mock_trello.get_board.return_value = {
            "id": "board123",
            "name": "Test Board",
            "url": "https://trello.com/b/abc123",
        }
        mock_trello.get_lists.return_value = [
            {"id": "list1", "name": "To Do", "pos": 1000}
        ]
        mock_trello.get_cards.return_value = [
            {
                "id": "card1",
                "name": "Card with Checklist",
                "desc": "Main description",
                "idList": "list1",
                "pos": 1000,
                "shortLink": "abc",
                "shortUrl": "https://trello.com/c/abc",
                "labels": [],
                "checklists": [
                    {
                        "name": "Setup",
                        "checkItems": [
                            {"name": "Install dependencies", "state": "complete"},
                            {"name": "Configure settings", "state": "incomplete"},
                        ],
                    }
                ],
                "attachments": [],
            }
        ]

        with patch.object(BeadsWriter, "_check_bd_available"):
            mock_beads = BeadsWriter(dry_run=True)

        converter = TrelloToBeadsConverter(mock_trello, mock_beads)

        created_issues = []

        def mock_create_issue(**kwargs):
            issue_id = f"test-{len(created_issues)}"
            created_issues.append({"id": issue_id, **kwargs})
            return issue_id

        with patch.object(converter.beads, "create_issue", side_effect=mock_create_issue):
            converter.convert()

        # Verify checklist was embedded in description
        assert len(created_issues) == 1
        desc = created_issues[0]["description"]

        assert "Main description" in desc
        assert "## Checklists" in desc
        assert "### Setup" in desc
        assert "Install dependencies" in desc
        assert "Configure settings" in desc
        assert "✓" in desc  # Complete marker
        assert "☐" in desc  # Incomplete marker

    def test_convert_card_with_attachments(self):
        """Should embed attachments in description"""
        mock_trello = MagicMock(spec=TrelloReader)
        mock_trello.get_board.return_value = {
            "id": "board123",
            "name": "Test Board",
            "url": "https://trello.com/b/abc123",
        }
        mock_trello.get_lists.return_value = [
            {"id": "list1", "name": "To Do", "pos": 1000}
        ]
        mock_trello.get_cards.return_value = [
            {
                "id": "card1",
                "name": "Card with Attachments",
                "desc": "Main description",
                "idList": "list1",
                "pos": 1000,
                "shortLink": "abc",
                "shortUrl": "https://trello.com/c/abc",
                "labels": [],
                "checklists": [],
                "attachments": [
                    {
                        "name": "screenshot.png",
                        "url": "https://example.com/screenshot.png",
                        "bytes": 12345,
                    },
                    {
                        "name": "document.pdf",
                        "url": "https://example.com/doc.pdf",
                        "bytes": 54321,
                    },
                ],
            }
        ]

        with patch.object(BeadsWriter, "_check_bd_available"):
            mock_beads = BeadsWriter(dry_run=True)

        converter = TrelloToBeadsConverter(mock_trello, mock_beads)

        created_issues = []

        def mock_create_issue(**kwargs):
            issue_id = f"test-{len(created_issues)}"
            created_issues.append({"id": issue_id, **kwargs})
            return issue_id

        with patch.object(converter.beads, "create_issue", side_effect=mock_create_issue):
            converter.convert()

        # Verify attachments were embedded in description
        assert len(created_issues) == 1
        desc = created_issues[0]["description"]

        assert "## Attachments" in desc
        assert "screenshot.png" in desc
        assert "document.pdf" in desc
        assert "12345 bytes" in desc
        assert "54321 bytes" in desc


class TestCommentFetching:
    """Test comment fetching during conversion"""

    def test_convert_fetches_comments_for_cards(self):
        """Should fetch comments for cards that have them"""
        mock_trello = MagicMock(spec=TrelloReader)
        mock_trello.get_board.return_value = {
            "id": "board123",
            "name": "Test Board",
            "url": "https://trello.com/b/abc123",
        }
        mock_trello.get_lists.return_value = [
            {"id": "list1", "name": "To Do", "pos": 1000}
        ]
        mock_trello.get_cards.return_value = [
            {
                "id": "card1",
                "name": "Card with Comments",
                "desc": "Description",
                "idList": "list1",
                "pos": 1000,
                "shortLink": "abc",
                "shortUrl": "https://trello.com/c/abc",
                "labels": [],
                "checklists": [],
                "attachments": [],
                "badges": {"comments": 2},  # Has comments
            }
        ]
        mock_trello.get_card_comments.return_value = [
            {
                "id": "comment1",
                "data": {"text": "First comment"},
                "date": "2024-01-15T10:30:00.000Z",
                "memberCreator": {"fullName": "John Doe"},
            },
            {
                "id": "comment2",
                "data": {"text": "Second comment"},
                "date": "2024-01-16T14:20:00.000Z",
                "memberCreator": {"fullName": "Jane Smith"},
            },
        ]

        with patch.object(BeadsWriter, "_check_bd_available"):
            mock_beads = BeadsWriter(dry_run=True)

        converter = TrelloToBeadsConverter(mock_trello, mock_beads)

        created_issues = []

        def mock_create_issue(**kwargs):
            issue_id = f"test-{len(created_issues)}"
            created_issues.append({"id": issue_id, **kwargs})
            return issue_id

        with patch.object(converter.beads, "create_issue", side_effect=mock_create_issue):
            converter.convert()

        # Verify comments were fetched
        mock_trello.get_card_comments.assert_called_once_with("card1")

        # Verify comments embedded in description (currently - will change in rmn.7)
        assert len(created_issues) == 1
        desc = created_issues[0]["description"]

        assert "## Comments" in desc
        assert "John Doe" in desc
        assert "Jane Smith" in desc
        assert "First comment" in desc
        assert "Second comment" in desc
        assert "2024-01-15" in desc
        assert "2024-01-16" in desc


class TestErrorHandling:
    """Test error handling during conversion"""

    def test_convert_continues_on_individual_card_failure(self):
        """Should continue converting other cards if one fails"""
        mock_trello = MagicMock(spec=TrelloReader)
        mock_trello.get_board.return_value = {
            "id": "board123",
            "name": "Test Board",
            "url": "https://trello.com/b/abc123",
        }
        mock_trello.get_lists.return_value = [
            {"id": "list1", "name": "To Do", "pos": 1000}
        ]
        mock_trello.get_cards.return_value = [
            {
                "id": "card1",
                "name": "Good Card",
                "desc": "Will succeed",
                "idList": "list1",
                "pos": 1000,
                "shortLink": "good",
                "shortUrl": "https://trello.com/c/good",
                "labels": [],
                "checklists": [],
                "attachments": [],
            },
            {
                "id": "card2",
                "name": "Bad Card",
                "desc": "Will fail",
                "idList": "list1",
                "pos": 2000,
                "shortLink": "bad",
                "shortUrl": "https://trello.com/c/bad",
                "labels": [],
                "checklists": [],
                "attachments": [],
            },
            {
                "id": "card3",
                "name": "Another Good Card",
                "desc": "Will succeed",
                "idList": "list1",
                "pos": 3000,
                "shortLink": "good2",
                "shortUrl": "https://trello.com/c/good2",
                "labels": [],
                "checklists": [],
                "attachments": [],
            },
        ]

        with patch.object(BeadsWriter, "_check_bd_available"):
            mock_beads = BeadsWriter(dry_run=True)

        converter = TrelloToBeadsConverter(mock_trello, mock_beads)

        created_count = [0]

        def mock_create_issue(**kwargs):
            if kwargs["title"] == "Bad Card":
                raise Exception("Simulated failure")
            created_count[0] += 1
            return f"test-{created_count[0]}"

        with patch.object(converter.beads, "create_issue", side_effect=mock_create_issue):
            # Should not raise, should continue
            converter.convert()

        # Should have created 2 issues (card1 and card3), skipped card2
        assert created_count[0] == 2
