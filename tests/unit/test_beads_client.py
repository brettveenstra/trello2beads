"""
Comprehensive unit tests for BeadsWriter class

Tests cover:
- Success cases (create_issue, update_status)
- Error handling (bd CLI not found, subprocess failures, parsing failures)
- Input validation (invalid inputs rejected)
- Dry-run mode (no subprocess calls)
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directory to path to import trello2beads module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from trello2beads import (
    BeadsCommandError,
    BeadsIssueCreationError,
    BeadsUpdateError,
    BeadsWriter,
)


class TestBeadsWriterInitialization:
    """Test BeadsWriter initialization and bd CLI availability checks"""

    def test_init_without_db_path(self):
        """Should initialize BeadsWriter without custom database path"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            assert writer.db_path is None
            assert writer.dry_run is False

    def test_init_with_db_path(self):
        """Should initialize BeadsWriter with custom database path"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter(db_path="/custom/path/beads.db")
            assert writer.db_path == "/custom/path/beads.db"
            assert writer.dry_run is False

    def test_init_with_dry_run_skips_check(self):
        """Should skip bd CLI check when dry_run=True"""
        # Should not raise even without bd CLI
        writer = BeadsWriter(dry_run=True)
        assert writer.dry_run is True

    def test_init_calls_check_bd_available(self):
        """Should call _check_bd_available during initialization"""
        with patch.object(BeadsWriter, "_check_bd_available") as mock_check:
            BeadsWriter()
            mock_check.assert_called_once()

    def test_check_bd_available_success(self):
        """Should pass pre-flight check when bd CLI is available"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "bd help output"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            BeadsWriter()
            # Should not raise

    def test_check_bd_available_bd_not_found(self):
        """Should raise BeadsCommandError when bd CLI is not found"""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(BeadsCommandError) as exc_info:
                BeadsWriter()

            error = exc_info.value
            assert "bd CLI not found" in str(error)
            assert "Install: https://github.com/niutech/beads" in str(error)

    def test_check_bd_available_bd_not_working(self):
        """Should raise BeadsCommandError when bd CLI returns non-zero exit code"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error output"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(BeadsCommandError) as exc_info:
                BeadsWriter()

            error = exc_info.value
            assert "bd CLI is not working properly" in str(error)
            assert error.returncode == 1

    def test_check_bd_available_timeout(self):
        """Should raise BeadsCommandError when bd CLI check times out"""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("bd", 5)):
            with pytest.raises(BeadsCommandError) as exc_info:
                BeadsWriter()

            error = exc_info.value
            assert "bd CLI timed out" in str(error)


class TestIssueIDParsing:
    """Test _parse_issue_id method"""

    def test_parse_issue_id_standard_format(self):
        """Should parse issue ID from standard 'Created issue:' format"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            output = "✓ Created issue: trello2beads-abc"
            issue_id = writer._parse_issue_id(output)
            assert issue_id == "trello2beads-abc"

    def test_parse_issue_id_alternative_format(self):
        """Should parse issue ID from 'Issue created:' format"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            output = "Issue created: myproject-123"
            issue_id = writer._parse_issue_id(output)
            assert issue_id == "myproject-123"

    def test_parse_issue_id_compact_format(self):
        """Should parse issue ID from compact format"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            output = "✓ Created project-xyz"
            issue_id = writer._parse_issue_id(output)
            assert issue_id == "project-xyz"

    def test_parse_issue_id_multiline_output(self):
        """Should parse issue ID from multiline output"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            output = """
Some debug info
Created issue: test-id1
More output
"""
            issue_id = writer._parse_issue_id(output)
            assert issue_id == "test-id1"

    def test_parse_issue_id_no_match(self):
        """Should return None when no issue ID is found"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            output = "Some random output without issue ID"
            issue_id = writer._parse_issue_id(output)
            assert issue_id is None


class TestIssueIDValidation:
    """Test _validate_issue_id method"""

    def test_validate_issue_id_valid_format(self):
        """Should validate correctly formatted issue IDs"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            assert writer._validate_issue_id("trello2beads-abc") is True
            assert writer._validate_issue_id("project-123") is True
            assert writer._validate_issue_id("myapp-x7z") is True

    def test_validate_issue_id_invalid_format(self):
        """Should reject invalid issue ID formats"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            assert writer._validate_issue_id("invalid") is False
            assert writer._validate_issue_id("") is False
            assert (
                writer._validate_issue_id("no-dashes-here-extra") is False
            )  # Multiple dashes not allowed
            assert writer._validate_issue_id("123") is False
            assert writer._validate_issue_id("only-one") is True  # Valid: single dash


class TestInputValidation:
    """Test _validate_inputs method"""

    def test_validate_inputs_empty_title(self):
        """Should raise ValueError for empty title"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            with pytest.raises(ValueError, match="Title cannot be empty"):
                writer._validate_inputs("", "desc", "open", 2, "task", None)

    def test_validate_inputs_whitespace_only_title(self):
        """Should raise ValueError for whitespace-only title"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            with pytest.raises(ValueError, match="Title cannot be empty"):
                writer._validate_inputs("   ", "desc", "open", 2, "task", None)

    def test_validate_inputs_title_too_long(self):
        """Should raise ValueError for title exceeding 500 characters"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            long_title = "a" * 501
            with pytest.raises(ValueError, match="Title too long"):
                writer._validate_inputs(long_title, "desc", "open", 2, "task", None)

    def test_validate_inputs_description_too_long(self):
        """Should raise ValueError for description exceeding 50000 characters"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            long_desc = "a" * 50001
            with pytest.raises(ValueError, match="Description too long"):
                writer._validate_inputs("title", long_desc, "open", 2, "task", None)

    def test_validate_inputs_invalid_status(self):
        """Should raise ValueError for invalid status"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            with pytest.raises(ValueError, match="Invalid status"):
                writer._validate_inputs("title", "desc", "invalid", 2, "task", None)

    def test_validate_inputs_valid_statuses(self):
        """Should accept all valid statuses"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            valid_statuses = ["open", "in_progress", "blocked", "deferred", "closed"]
            for status in valid_statuses:
                writer._validate_inputs("title", "desc", status, 2, "task", None)
                # Should not raise

    def test_validate_inputs_invalid_priority_type(self):
        """Should raise ValueError for non-integer priority"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            with pytest.raises(ValueError, match="Priority must be an integer"):
                writer._validate_inputs("title", "desc", "open", "2", "task", None)

    def test_validate_inputs_priority_out_of_range(self):
        """Should raise ValueError for priority outside 0-4 range"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            with pytest.raises(ValueError, match="Priority must be 0-4"):
                writer._validate_inputs("title", "desc", "open", 5, "task", None)
            with pytest.raises(ValueError, match="Priority must be 0-4"):
                writer._validate_inputs("title", "desc", "open", -1, "task", None)

    def test_validate_inputs_invalid_issue_type(self):
        """Should raise ValueError for invalid issue type"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            with pytest.raises(ValueError, match="Invalid issue_type"):
                writer._validate_inputs("title", "desc", "open", 2, "invalid", None)

    def test_validate_inputs_valid_issue_types(self):
        """Should accept all valid issue types"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            valid_types = ["task", "bug", "feature", "epic", "chore"]
            for issue_type in valid_types:
                writer._validate_inputs("title", "desc", "open", 2, issue_type, None)
                # Should not raise

    def test_validate_inputs_labels_not_list(self):
        """Should raise ValueError when labels is not a list"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            with pytest.raises(ValueError, match="Labels must be a list"):
                writer._validate_inputs("title", "desc", "open", 2, "task", "not-a-list")

    def test_validate_inputs_label_not_string(self):
        """Should raise ValueError when label is not a string"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            with pytest.raises(ValueError, match="All labels must be strings"):
                writer._validate_inputs("title", "desc", "open", 2, "task", [123, "valid"])

    def test_validate_inputs_empty_label(self):
        """Should raise ValueError for empty label strings"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            with pytest.raises(ValueError, match="Labels cannot be empty strings"):
                writer._validate_inputs("title", "desc", "open", 2, "task", ["valid", ""])

    def test_validate_inputs_label_with_comma(self):
        """Should raise ValueError for labels containing commas"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            with pytest.raises(ValueError, match="Label contains comma"):
                writer._validate_inputs("title", "desc", "open", 2, "task", ["valid", "has,comma"])

    def test_validate_inputs_success(self):
        """Should pass validation with valid inputs"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            # Should not raise
            writer._validate_inputs(
                "Valid title", "Valid description", "open", 2, "task", ["label1", "label2"]
            )


class TestCreateIssue:
    """Test create_issue method"""

    def test_create_issue_success_minimal(self):
        """Should create issue with minimal parameters"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "✓ Created issue: test-abc"
            mock_result.stderr = ""

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                issue_id = writer.create_issue("Test title")

                assert issue_id == "test-abc"
                mock_run.assert_called_once()
                cmd = mock_run.call_args[0][0]
                assert "bd" in cmd
                assert "create" in cmd
                assert "--title" in cmd
                assert "Test title" in cmd

    def test_create_issue_success_all_parameters(self):
        """Should create issue with all parameters"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "✓ Created issue: test-xyz"
            mock_result.stderr = ""

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                issue_id = writer.create_issue(
                    title="Test issue",
                    description="Test description",
                    status="open",
                    priority=1,
                    issue_type="bug",
                    labels=["urgent", "frontend"],
                    external_ref="TRELLO-123",
                )

                assert issue_id == "test-xyz"
                cmd = mock_run.call_args[0][0]
                assert "bd" in cmd
                assert "--title" in cmd
                assert "Test issue" in cmd
                assert "--description" in cmd
                assert "--priority" in cmd
                assert "1" in cmd
                assert "--type" in cmd
                assert "bug" in cmd
                assert "--labels" in cmd
                assert "urgent,frontend" in cmd
                assert "--external-ref" in cmd
                assert "TRELLO-123" in cmd

    def test_create_issue_with_custom_db_path(self):
        """Should include --db flag when db_path is set"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter(db_path="/custom/beads.db")

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "✓ Created issue: test-abc"
            mock_result.stderr = ""

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                writer.create_issue("Test title")

                cmd = mock_run.call_args[0][0]
                assert "--db" in cmd
                assert "/custom/beads.db" in cmd

    def test_create_issue_updates_status_when_not_open(self):
        """Should call update_status when status is not 'open'"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "✓ Created issue: test-abc"
            mock_result.stderr = ""

            with (
                patch("subprocess.run", return_value=mock_result),
                patch.object(writer, "update_status") as mock_update,
            ):
                writer.create_issue("Test title", status="in_progress")

                mock_update.assert_called_once_with("test-abc", "in_progress")

    def test_create_issue_subprocess_timeout(self):
        """Should raise BeadsIssueCreationError on subprocess timeout"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            with (
                patch("subprocess.run", side_effect=subprocess.TimeoutExpired("bd", 30)),
                pytest.raises(BeadsIssueCreationError, match="timed out"),
            ):
                writer.create_issue("Test title")

    def test_create_issue_subprocess_failure(self):
        """Should raise BeadsIssueCreationError when bd returns non-zero exit code"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_result.stderr = "Database not initialized"

            with (
                patch("subprocess.run", return_value=mock_result),
                pytest.raises(BeadsIssueCreationError, match="Failed to create issue"),
            ):
                writer.create_issue("Test title")

    def test_create_issue_parsing_failure(self):
        """Should raise BeadsIssueCreationError when issue ID cannot be parsed"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "Unexpected output format"
            mock_result.stderr = ""

            with (
                patch("subprocess.run", return_value=mock_result),
                pytest.raises(BeadsIssueCreationError, match="Could not parse issue ID"),
            ):
                writer.create_issue("Test title")

    def test_create_issue_invalid_issue_id_format(self):
        """Should raise BeadsIssueCreationError when parsed issue ID is invalid"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "Created issue: invalid-format-here-bad"
            mock_result.stderr = ""

            with (
                patch("subprocess.run", return_value=mock_result),
                patch.object(writer, "_parse_issue_id", return_value="invalid"),
                pytest.raises(BeadsIssueCreationError, match="invalid format"),
            ):
                writer.create_issue("Test title")

    def test_create_issue_validates_inputs(self):
        """Should validate inputs before creating issue"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            with pytest.raises(ValueError, match="Title cannot be empty"):
                writer.create_issue("")

    def test_create_issue_unexpected_error(self):
        """Should raise BeadsIssueCreationError on unexpected subprocess errors"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            # Simulate an unexpected error (e.g., OSError)
            with (
                patch("subprocess.run", side_effect=OSError("Unexpected OS error")),
                pytest.raises(BeadsIssueCreationError, match="Unexpected error creating issue"),
            ):
                writer.create_issue("Test title")


class TestUpdateStatus:
    """Test update_status method"""

    def test_update_status_success(self):
        """Should update issue status successfully"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "✓ Updated issue: test-abc"
            mock_result.stderr = ""

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                writer.update_status("test-abc", "in_progress")

                cmd = mock_run.call_args[0][0]
                assert "bd" in cmd
                assert "update" in cmd
                assert "test-abc" in cmd
                assert "--status" in cmd
                assert "in_progress" in cmd

    def test_update_status_with_custom_db_path(self):
        """Should include --db flag when db_path is set"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter(db_path="/custom/beads.db")

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "✓ Updated issue"
            mock_result.stderr = ""

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                writer.update_status("test-abc", "closed")

                cmd = mock_run.call_args[0][0]
                assert "--db" in cmd
                assert "/custom/beads.db" in cmd

    def test_update_status_empty_issue_id(self):
        """Should raise ValueError for empty issue ID"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            with pytest.raises(ValueError, match="Issue ID cannot be empty"):
                writer.update_status("", "open")

    def test_update_status_invalid_status(self):
        """Should raise ValueError for invalid status"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            with pytest.raises(ValueError, match="Invalid status"):
                writer.update_status("test-abc", "invalid_status")

    def test_update_status_subprocess_timeout(self):
        """Should raise BeadsUpdateError on subprocess timeout"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            with (
                patch("subprocess.run", side_effect=subprocess.TimeoutExpired("bd", 30)),
                pytest.raises(BeadsUpdateError, match="timed out"),
            ):
                writer.update_status("test-abc", "closed")

    def test_update_status_subprocess_failure(self):
        """Should raise BeadsUpdateError when bd returns non-zero exit code"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_result.stderr = "Issue not found"

            with (
                patch("subprocess.run", return_value=mock_result),
                pytest.raises(BeadsUpdateError, match="Failed to update issue status"),
            ):
                writer.update_status("test-abc", "closed")

    def test_update_status_unexpected_error(self):
        """Should raise BeadsUpdateError on unexpected subprocess errors"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            # Simulate an unexpected error (e.g., OSError)
            with (
                patch("subprocess.run", side_effect=RuntimeError("Unexpected runtime error")),
                pytest.raises(BeadsUpdateError, match="Unexpected error updating status"),
            ):
                writer.update_status("test-abc", "closed")


class TestDryRunMode:
    """Test dry-run mode functionality"""

    def test_dry_run_create_issue_no_subprocess(self):
        """Should not execute subprocess in dry-run mode"""
        writer = BeadsWriter(dry_run=True)

        with patch("subprocess.run") as mock_run:
            issue_id = writer.create_issue("Test title")

            # Should not call subprocess
            mock_run.assert_not_called()
            # Should return mock ID
            assert issue_id == "dryrun-mock"

    def test_dry_run_update_status_no_subprocess(self):
        """Should not execute subprocess in dry-run mode for update_status"""
        writer = BeadsWriter(dry_run=True)

        with patch("subprocess.run") as mock_run:
            writer.update_status("test-abc", "closed")

            # Should not call subprocess
            mock_run.assert_not_called()

    def test_dry_run_create_issue_with_all_params(self):
        """Should handle all parameters in dry-run mode"""
        writer = BeadsWriter(dry_run=True)

        with patch("subprocess.run") as mock_run:
            issue_id = writer.create_issue(
                title="Test",
                description="Desc",
                status="in_progress",
                priority=3,
                issue_type="feature",
                labels=["test"],
                external_ref="REF-1",
            )

            mock_run.assert_not_called()
            assert issue_id == "dryrun-mock"

    def test_dry_run_still_validates_inputs(self):
        """Should still validate inputs in dry-run mode"""
        writer = BeadsWriter(dry_run=True)

        with pytest.raises(ValueError, match="Title cannot be empty"):
            writer.create_issue("")

        with pytest.raises(ValueError, match="Invalid status"):
            writer.update_status("test-abc", "invalid")


class TestAddDependency:
    """Test add_dependency method"""

    def test_add_dependency_success_default_blocks(self):
        """Should add blocking dependency by default"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "✓ Added dependency"
            mock_result.stderr = ""

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                writer.add_dependency("issue-123", "issue-456")

                cmd = mock_run.call_args[0][0]
                assert "bd" in cmd
                assert "dep" in cmd
                assert "add" in cmd
                assert "issue-123" in cmd
                assert "issue-456" in cmd
                assert "--type" in cmd
                assert "blocks" in cmd

    def test_add_dependency_parent_child(self):
        """Should add parent-child dependency for epics"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "✓ Added dependency"
            mock_result.stderr = ""

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                writer.add_dependency("child-123", "parent-456", "parent-child")

                cmd = mock_run.call_args[0][0]
                assert "--type" in cmd
                assert "parent-child" in cmd

    def test_add_dependency_related(self):
        """Should add related (non-blocking) dependency"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "✓ Added dependency"
            mock_result.stderr = ""

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                writer.add_dependency("issue-123", "issue-456", "related")

                cmd = mock_run.call_args[0][0]
                assert "--type" in cmd
                assert "related" in cmd

    def test_add_dependency_with_custom_db_path(self):
        """Should include --db flag when db_path is set"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter(db_path="/custom/beads.db")

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "✓ Added dependency"
            mock_result.stderr = ""

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                writer.add_dependency("issue-123", "issue-456")

                cmd = mock_run.call_args[0][0]
                assert "--db" in cmd
                assert "/custom/beads.db" in cmd

    def test_add_dependency_empty_issue_id(self):
        """Should raise ValueError for empty issue ID"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            with pytest.raises(ValueError, match="Issue ID cannot be empty"):
                writer.add_dependency("", "issue-456")

    def test_add_dependency_empty_depends_on_id(self):
        """Should raise ValueError for empty depends-on ID"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            with pytest.raises(ValueError, match="Depends-on ID cannot be empty"):
                writer.add_dependency("issue-123", "")

    def test_add_dependency_invalid_type(self):
        """Should raise ValueError for invalid dependency type"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            with pytest.raises(ValueError, match="Invalid dependency_type"):
                writer.add_dependency("issue-123", "issue-456", "invalid-type")

    def test_add_dependency_subprocess_failure(self):
        """Should raise BeadsUpdateError when bd returns non-zero exit code"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_result.stderr = "Issue not found"

            with (
                patch("subprocess.run", return_value=mock_result),
                pytest.raises(BeadsUpdateError, match="Failed to add dependency"),
            ):
                writer.add_dependency("issue-123", "issue-456")

    def test_add_dependency_dry_run(self):
        """Should not execute subprocess in dry-run mode"""
        writer = BeadsWriter(dry_run=True)

        with patch("subprocess.run") as mock_run:
            writer.add_dependency("issue-123", "issue-456")

            # Should not call subprocess
            mock_run.assert_not_called()


class TestAddComment:
    """Test add_comment method"""

    def test_add_comment_success(self):
        """Should add comment successfully"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "✓ Added comment"
            mock_result.stderr = ""

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                writer.add_comment("issue-123", "This is a comment")

                cmd = mock_run.call_args[0][0]
                assert "bd" in cmd
                assert "comment" in cmd
                assert "issue-123" in cmd
                assert "This is a comment" in cmd

    def test_add_comment_with_author(self):
        """Should include author flag when provided"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "✓ Added comment"
            mock_result.stderr = ""

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                writer.add_comment("issue-123", "Comment text", author="Alice")

                cmd = mock_run.call_args[0][0]
                assert "--author" in cmd
                assert "Alice" in cmd

    def test_add_comment_empty_issue_id(self):
        """Should raise ValueError for empty issue ID"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            with pytest.raises(ValueError, match="Issue ID cannot be empty"):
                writer.add_comment("", "Comment text")

    def test_add_comment_empty_text(self):
        """Should raise ValueError for empty comment text"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            with pytest.raises(ValueError, match="Comment text cannot be empty"):
                writer.add_comment("issue-123", "")

    def test_add_comment_text_too_long(self):
        """Should raise ValueError for comment exceeding 50000 characters"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()
            long_text = "a" * 50001

            with pytest.raises(ValueError, match="Comment too long"):
                writer.add_comment("issue-123", long_text)

    def test_add_comment_subprocess_failure(self):
        """Should raise BeadsUpdateError when bd returns non-zero exit code"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_result.stderr = "Issue not found"

            with (
                patch("subprocess.run", return_value=mock_result),
                pytest.raises(BeadsUpdateError, match="Failed to add comment"),
            ):
                writer.add_comment("issue-123", "Comment text")

    def test_add_comment_dry_run(self):
        """Should not execute subprocess in dry-run mode"""
        writer = BeadsWriter(dry_run=True)

        with patch("subprocess.run") as mock_run:
            writer.add_comment("issue-123", "Comment text")

            # Should not call subprocess
            mock_run.assert_not_called()


class TestGetIssue:
    """Test get_issue method"""

    def test_get_issue_success(self):
        """Should retrieve issue successfully"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = '{"id": "test-123", "title": "Test Issue", "status": "open"}'
            mock_result.stderr = ""

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                issue = writer.get_issue("test-123")

                cmd = mock_run.call_args[0][0]
                assert "bd" in cmd
                assert "show" in cmd
                assert "test-123" in cmd
                assert "--json" in cmd

                assert issue["id"] == "test-123"
                assert issue["title"] == "Test Issue"
                assert issue["status"] == "open"

    def test_get_issue_empty_issue_id(self):
        """Should raise ValueError for empty issue ID"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            with pytest.raises(ValueError, match="Issue ID cannot be empty"):
                writer.get_issue("")

    def test_get_issue_subprocess_failure(self):
        """Should raise BeadsUpdateError when bd returns non-zero exit code"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_result.stderr = "Issue not found"

            with (
                patch("subprocess.run", return_value=mock_result),
                pytest.raises(BeadsUpdateError, match="Failed to retrieve issue"),
            ):
                writer.get_issue("test-123")

    def test_get_issue_json_parse_error(self):
        """Should raise BeadsUpdateError when JSON parsing fails"""
        with patch.object(BeadsWriter, "_check_bd_available"):
            writer = BeadsWriter()

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "Not valid JSON"
            mock_result.stderr = ""

            with (
                patch("subprocess.run", return_value=mock_result),
                pytest.raises(BeadsUpdateError, match="Could not parse JSON"),
            ):
                writer.get_issue("test-123")

    def test_get_issue_dry_run(self):
        """Should return mock data in dry-run mode"""
        writer = BeadsWriter(dry_run=True)

        with patch("subprocess.run") as mock_run:
            issue = writer.get_issue("test-123")

            # Should not call subprocess
            mock_run.assert_not_called()

            # Should return mock data
            assert issue["id"] == "dryrun-mock"
            assert issue["status"] == "open"
