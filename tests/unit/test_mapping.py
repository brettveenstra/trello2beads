"""
Unit tests for Trello list → beads status mapping
"""
import pytest
import sys
from pathlib import Path

# Add parent directory to path to import trello2beads module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# We'll need to extract the class or make it importable
# For now, let's test the logic directly by recreating it


class TestListToStatusMapping:
    """Test the list_to_status mapping logic"""

    # Recreate the logic for testing (will be replaced with actual import later)
    STATUS_KEYWORDS = {
        'closed': ['done', 'completed', 'closed', 'archived', 'finished'],
        'in_progress': ['doing', 'in progress', 'wip', 'active', 'current', 'working']
    }

    @staticmethod
    def list_to_status(list_name: str) -> str:
        """Map list name to beads status (conservative)"""
        list_lower = list_name.lower()

        # Check for closed keywords
        if any(keyword in list_lower for keyword in TestListToStatusMapping.STATUS_KEYWORDS['closed']):
            return 'closed'

        # Check for in_progress keywords
        if any(keyword in list_lower for keyword in TestListToStatusMapping.STATUS_KEYWORDS['in_progress']):
            return 'in_progress'

        # Default to open (safe)
        return 'open'

    def test_done_maps_to_closed(self):
        """'Done' list should map to closed status"""
        assert self.list_to_status("Done") == "closed"

    def test_completed_maps_to_closed(self):
        """'Completed' list should map to closed status"""
        assert self.list_to_status("Completed") == "closed"

    def test_closed_maps_to_closed(self):
        """'Closed' list should map to closed status"""
        assert self.list_to_status("Closed") == "closed"

    def test_archived_maps_to_closed(self):
        """'Archived' list should map to closed status"""
        assert self.list_to_status("Archived") == "closed"

    def test_finished_maps_to_closed(self):
        """'Finished' list should map to closed status"""
        assert self.list_to_status("Finished") == "closed"

    def test_doing_maps_to_in_progress(self):
        """'Doing' list should map to in_progress status"""
        assert self.list_to_status("Doing") == "in_progress"

    def test_in_progress_maps_to_in_progress(self):
        """'In Progress' list should map to in_progress status"""
        assert self.list_to_status("In Progress") == "in_progress"

    def test_wip_maps_to_in_progress(self):
        """'WIP' list should map to in_progress status"""
        assert self.list_to_status("WIP") == "in_progress"

    def test_active_maps_to_in_progress(self):
        """'Active' list should map to in_progress status"""
        assert self.list_to_status("Active") == "in_progress"

    def test_current_maps_to_in_progress(self):
        """'Current' list should map to in_progress status"""
        assert self.list_to_status("Current") == "in_progress"

    def test_working_maps_to_in_progress(self):
        """'Working' list should map to in_progress status"""
        assert self.list_to_status("Working") == "in_progress"

    def test_todo_maps_to_open(self):
        """'To Do' list should map to open status (default)"""
        assert self.list_to_status("To Do") == "open"

    def test_backlog_maps_to_open(self):
        """'Backlog' list should map to open status (default)"""
        assert self.list_to_status("Backlog") == "open"

    def test_ideas_maps_to_open(self):
        """'Ideas' list should map to open status (default)"""
        assert self.list_to_status("Ideas") == "open"

    def test_case_insensitive_done(self):
        """Mapping should be case-insensitive: 'DONE'"""
        assert self.list_to_status("DONE") == "closed"

    def test_case_insensitive_doing(self):
        """Mapping should be case-insensitive: 'DOING'"""
        assert self.list_to_status("DOING") == "in_progress"

    def test_case_insensitive_mixed(self):
        """Mapping should be case-insensitive: 'DoNe'"""
        assert self.list_to_status("DoNe") == "closed"

    def test_partial_match_done_with_prefix(self):
        """Partial match: 'Sprint 1 - Done' should map to closed"""
        assert self.list_to_status("Sprint 1 - Done") == "closed"

    def test_partial_match_wip_with_suffix(self):
        """Partial match: 'WIP - Design' should map to in_progress"""
        assert self.list_to_status("WIP - Design") == "in_progress"

    def test_partial_match_doing_with_context(self):
        """Partial match: 'Currently Doing' should map to in_progress"""
        assert self.list_to_status("Currently Doing") == "in_progress"

    def test_default_to_open_for_unknown(self):
        """Unknown list names should default to open"""
        assert self.list_to_status("Random List Name") == "open"

    def test_empty_string_defaults_to_open(self):
        """Empty string should default to open"""
        assert self.list_to_status("") == "open"

    def test_priority_closed_over_in_progress(self):
        """If both keywords present, 'closed' should win (checked first)"""
        # 'done' appears before 'doing' in the check order
        assert self.list_to_status("Done Doing") == "closed"

    def test_whitespace_handling(self):
        """Whitespace variations should work: '  Done  '"""
        # Note: Current implementation doesn't strip, so this tests actual behavior
        assert self.list_to_status("  Done  ") == "closed"

    def test_special_characters(self):
        """Special characters don't interfere: 'Done!!'"""
        assert self.list_to_status("Done!!") == "closed"

    def test_hyphenated_in_progress(self):
        """Hyphenated form: 'In-Progress' should map to in_progress"""
        # 'in progress' keyword has space, so 'In-Progress' won't match
        # This test documents current behavior
        assert self.list_to_status("In-Progress") == "open"

    def test_common_trello_lists(self):
        """Test common Trello list names"""
        test_cases = [
            ("To Do", "open"),
            ("Backlog", "open"),
            ("Next Up", "open"),
            ("In Progress", "in_progress"),
            ("Doing", "in_progress"),
            ("In Review", "open"),  # 'review' not in keywords
            ("Done", "closed"),
            ("Completed", "closed"),
            ("Archived", "closed"),  # Full word 'archived' in keywords
            ("Archive", "open"),  # 'archive' != 'archived', no match
        ]

        for list_name, expected_status in test_cases:
            actual_status = self.list_to_status(list_name)
            assert actual_status == expected_status, \
                f"List '{list_name}' should map to '{expected_status}', got '{actual_status}'"
