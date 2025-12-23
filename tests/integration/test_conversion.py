"""
Integration tests for full Trello → beads conversion flow

Tests the complete conversion process with mocked Trello API responses.
Uses the `responses` library to avoid real API calls.
Uses mocking to avoid requiring `bd` CLI in test environment.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import responses

# Add parent directory to path to import trello2beads module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from trello2beads import BeadsWriter, TrelloReader, TrelloToBeadsConverter


@pytest.fixture
def mock_bd_cli():
    """
    Mock subprocess.run to simulate `bd` CLI behavior

    Returns a list of all `bd create` commands that would have been executed
    """
    created_issues = []
    issue_counter = [0]  # Use list to allow modification in nested function

    def mock_subprocess_run(cmd, *args, **kwargs):
        """Mock subprocess.run to capture bd commands"""
        result = Mock()
        result.returncode = 0
        result.stderr = ""

        if cmd[0] == "bd" and len(cmd) > 1:
            if cmd[1] == "create":
                # Generate fake issue ID
                issue_counter[0] += 1
                issue_id = f"testproject-{issue_counter[0]:03d}"

                # Parse command to extract issue details
                issue_data = {"id": issue_id}
                for i, arg in enumerate(cmd):
                    if arg == "--title" and i + 1 < len(cmd):
                        issue_data["title"] = cmd[i + 1]
                    elif arg == "--description" and i + 1 < len(cmd):
                        issue_data["description"] = cmd[i + 1]
                    elif arg == "--status" and i + 1 < len(cmd):
                        issue_data["status"] = cmd[i + 1]
                    elif arg == "--labels" and i + 1 < len(cmd):
                        issue_data["labels"] = cmd[i + 1].split(",")

                created_issues.append(issue_data)
                result.stdout = f"✓ Created issue: {issue_id}\n"

            elif cmd[1] == "update":
                # Mock update command
                result.stdout = f"✓ Updated issue: {cmd[2]}\n"

        return result

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        yield created_issues


class TestSimpleBoardConversion:
    """Test conversion of simple board fixture"""

    @responses.activate
    def test_simple_board_conversion(self, simple_board_fixture, mock_bd_cli):
        """Test converting simple_board.json fixture"""

        # Mock Trello API endpoints
        board_data = simple_board_fixture["board"]
        lists_data = simple_board_fixture["lists"]
        cards_data = simple_board_fixture["cards"]
        comments_data = simple_board_fixture.get("comments", {})

        # Mock board endpoint
        responses.add(
            responses.GET,
            "https://api.trello.com/1/boards/test_board_123",
            json=board_data,
            status=200,
        )

        # Mock lists endpoint
        responses.add(
            responses.GET,
            "https://api.trello.com/1/boards/test_board_123/lists",
            json=lists_data,
            status=200,
        )

        # Mock cards endpoint
        responses.add(
            responses.GET,
            "https://api.trello.com/1/boards/test_board_123/cards",
            json=cards_data,
            status=200,
        )

        # Mock comments for each card (if any)
        for card in cards_data:
            card_id = card["id"]
            card_comments = comments_data.get(card_id, [])
            responses.add(
                responses.GET,
                f"https://api.trello.com/1/cards/{card_id}/actions",
                json=card_comments,
                status=200,
            )

        # Run conversion
        trello = TrelloReader("fake-api-key", "fake-token", "test_board_123")
        beads = BeadsWriter()  # No db_path needed with mocked subprocess
        converter = TrelloToBeadsConverter(trello, beads)

        # Convert with snapshot
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "snapshot.json"
            converter.convert(dry_run=False, snapshot_path=str(snapshot_path))

            # Verify snapshot was created
            assert Path(snapshot_path).exists()

            # Verify conversion results from mocked bd CLI calls
            assert len(mock_bd_cli) == len(cards_data), (
                f"Expected {len(cards_data)} issues, got {len(mock_bd_cli)}"
            )

            # Count status distribution
            status_counts = {}
            for issue in mock_bd_cli:
                # Status might be in initial create or in update call
                # For now, check labels to infer list
                if "labels" in issue:
                    for label in issue["labels"]:
                        if label.startswith("list:"):
                            list_name = label[5:]  # Remove 'list:' prefix
                            # Map list to status
                            if list_name == "Done":
                                status = "closed"
                            elif list_name == "Doing":
                                status = "in_progress"
                            else:
                                status = "open"
                            status_counts[status] = status_counts.get(status, 0) + 1

            # Based on simple_board.json:
            # - 3 cards in "To Do" → open
            # - 2 cards in "Doing" → in_progress
            # - 5 cards in "Done" → closed
            assert status_counts.get("open", 0) == 3
            assert status_counts.get("in_progress", 0) == 2
            assert status_counts.get("closed", 0) == 5

            # Verify specific card titles
            titles = [issue["title"] for issue in mock_bd_cli]
            assert "Write README" in titles
            assert "Setup CI/CD" in titles
            assert "Add tests" in titles


class TestBoardWithComments:
    """Test conversion of board with comments"""

    @responses.activate
    def test_comments_preserved(self, board_with_comments_fixture, mock_bd_cli):
        """Test that comments are preserved in issue descriptions"""

        # Mock Trello API endpoints
        board_data = board_with_comments_fixture["board"]
        lists_data = board_with_comments_fixture["lists"]
        cards_data = board_with_comments_fixture["cards"]
        comments_data = board_with_comments_fixture.get("comments", {})

        responses.add(
            responses.GET,
            f"https://api.trello.com/1/boards/{board_data['id']}",
            json=board_data,
            status=200,
        )

        responses.add(
            responses.GET,
            f"https://api.trello.com/1/boards/{board_data['id']}/lists",
            json=lists_data,
            status=200,
        )

        responses.add(
            responses.GET,
            f"https://api.trello.com/1/boards/{board_data['id']}/cards",
            json=cards_data,
            status=200,
        )

        # Mock comments for each card
        for card in cards_data:
            card_id = card["id"]
            card_comments = comments_data.get(card_id, [])
            responses.add(
                responses.GET,
                f"https://api.trello.com/1/cards/{card_id}/actions",
                json=card_comments,
                status=200,
            )

        # Run conversion
        trello = TrelloReader("fake-api-key", "fake-token", board_data["id"])
        beads = BeadsWriter()
        converter = TrelloToBeadsConverter(trello, beads)

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "snapshot.json"
            converter.convert(dry_run=False, snapshot_path=str(snapshot_path))

            # Verify correct number of issues created
            assert len(mock_bd_cli) == len(cards_data)

            # Find the card with comments in mock_bd_cli
            dark_mode_issue = next(
                (i for i in mock_bd_cli if "Dark Mode" in i.get("title", "")), None
            )
            assert dark_mode_issue is not None, "Dark Mode issue not found"

            # Verify comment content is in description
            description = dark_mode_issue.get("description", "")
            assert "Alice Developer" in description
            assert "CSS variables" in description
            assert "Bob Designer" in description
            assert "next sprint" in description
            assert "## Comments" in description


class TestBoardWithReferences:
    """Test conversion of board with Trello card references"""

    @responses.activate
    def test_url_resolution(self, board_with_references_fixture, mock_bd_cli):
        """Test that Trello URLs are resolved (basic check)"""

        # Mock Trello API endpoints
        board_data = board_with_references_fixture["board"]
        lists_data = board_with_references_fixture["lists"]
        cards_data = board_with_references_fixture["cards"]
        comments_data = board_with_references_fixture.get("comments", {})

        responses.add(
            responses.GET,
            f"https://api.trello.com/1/boards/{board_data['id']}",
            json=board_data,
            status=200,
        )

        responses.add(
            responses.GET,
            f"https://api.trello.com/1/boards/{board_data['id']}/lists",
            json=lists_data,
            status=200,
        )

        responses.add(
            responses.GET,
            f"https://api.trello.com/1/boards/{board_data['id']}/cards",
            json=cards_data,
            status=200,
        )

        # Mock comments for each card
        for card in cards_data:
            card_id = card["id"]
            card_comments = comments_data.get(card_id, [])
            responses.add(
                responses.GET,
                f"https://api.trello.com/1/cards/{card_id}/actions",
                json=card_comments,
                status=200,
            )

        # Run conversion
        trello = TrelloReader("fake-api-key", "fake-token", board_data["id"])
        beads = BeadsWriter()
        converter = TrelloToBeadsConverter(trello, beads)

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "snapshot.json"
            converter.convert(dry_run=False, snapshot_path=str(snapshot_path))

            # Verify correct number of cards created
            assert len(mock_bd_cli) == 3


class TestEmptyBoard:
    """Test conversion of empty board (edge case)"""

    @responses.activate
    def test_empty_board_handling(self, empty_board_fixture, mock_bd_cli):
        """Test graceful handling of boards with no cards"""

        # Mock Trello API endpoints
        board_data = empty_board_fixture["board"]
        lists_data = empty_board_fixture["lists"]
        cards_data = empty_board_fixture["cards"]  # Empty list

        responses.add(
            responses.GET,
            f"https://api.trello.com/1/boards/{board_data['id']}",
            json=board_data,
            status=200,
        )

        responses.add(
            responses.GET,
            f"https://api.trello.com/1/boards/{board_data['id']}/lists",
            json=lists_data,
            status=200,
        )

        responses.add(
            responses.GET,
            f"https://api.trello.com/1/boards/{board_data['id']}/cards",
            json=cards_data,
            status=200,
        )

        # Run conversion
        trello = TrelloReader("fake-api-key", "fake-token", board_data["id"])
        beads = BeadsWriter()
        converter = TrelloToBeadsConverter(trello, beads)

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "snapshot.json"

            # Should not crash on empty board
            converter.convert(dry_run=False, snapshot_path=str(snapshot_path))

            # Verify no issues created
            assert len(mock_bd_cli) == 0


class TestDryRun:
    """Test dry-run mode (no actual beads issues created)"""

    @responses.activate
    def test_dry_run_no_issues_created(self, simple_board_fixture, mock_bd_cli):
        """Test that dry-run mode doesn't create actual issues"""

        # Mock Trello API endpoints
        board_data = simple_board_fixture["board"]
        lists_data = simple_board_fixture["lists"]
        cards_data = simple_board_fixture["cards"]

        responses.add(
            responses.GET,
            "https://api.trello.com/1/boards/test_board_123",
            json=board_data,
            status=200,
        )

        responses.add(
            responses.GET,
            "https://api.trello.com/1/boards/test_board_123/lists",
            json=lists_data,
            status=200,
        )

        responses.add(
            responses.GET,
            "https://api.trello.com/1/boards/test_board_123/cards",
            json=cards_data,
            status=200,
        )

        # Mock comments (even though dry-run shouldn't fetch them)
        for card in cards_data:
            responses.add(
                responses.GET,
                f"https://api.trello.com/1/cards/{card['id']}/actions",
                json=[],
                status=200,
            )

        # Run dry-run conversion
        trello = TrelloReader("fake-api-key", "fake-token", "test_board_123")
        beads = BeadsWriter()
        converter = TrelloToBeadsConverter(trello, beads)

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "snapshot.json"
            converter.convert(dry_run=True, snapshot_path=str(snapshot_path))

            # Verify NO issues were created
            assert len(mock_bd_cli) == 0, "Dry-run should not create issues"
