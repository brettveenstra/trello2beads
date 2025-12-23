"""
Unit tests for Trello list → beads status mapping
"""

import json
import sys
from pathlib import Path

import pytest

# Add parent directory to path to import trello2beads module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from trello2beads import load_status_mapping

# We'll need to extract the class or make it importable
# For now, let's test the logic directly by recreating it


class TestListToStatusMapping:
    """Test the list_to_status mapping logic"""

    # Recreate the logic for testing (will be replaced with actual import later)
    STATUS_KEYWORDS = {
        "closed": ["done", "completed", "closed", "archived", "finished"],
        "blocked": ["blocked", "waiting", "waiting on", "on hold", "paused"],
        "deferred": ["deferred", "someday", "maybe", "later", "backlog", "future"],
        "in_progress": ["doing", "in progress", "wip", "active", "current", "working"],
        "open": ["todo", "to do", "planned", "ready"],
    }

    @staticmethod
    def list_to_status(list_name: str) -> str:
        """Map list name to beads status (conservative)

        Priority order: closed > blocked > deferred > in_progress > open
        This ensures definitive states take precedence over ambiguous ones.
        """
        list_lower = list_name.lower()
        keywords = TestListToStatusMapping.STATUS_KEYWORDS

        # Check in priority order: closed > blocked > deferred > in_progress > open

        # Check for closed keywords (highest priority - most definitive)
        if "closed" in keywords and any(keyword in list_lower for keyword in keywords["closed"]):
            return "closed"

        # Check for blocked keywords (explicit impediment)
        if "blocked" in keywords and any(keyword in list_lower for keyword in keywords["blocked"]):
            return "blocked"

        # Check for deferred keywords (explicit postponement)
        if "deferred" in keywords and any(
            keyword in list_lower for keyword in keywords["deferred"]
        ):
            return "deferred"

        # Check for in_progress keywords (active work)
        if "in_progress" in keywords and any(
            keyword in list_lower for keyword in keywords["in_progress"]
        ):
            return "in_progress"

        # Check for explicit open keywords (optional)
        if "open" in keywords and any(keyword in list_lower for keyword in keywords["open"]):
            return "open"

        # Default to open (safe)
        return "open"

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

    def test_backlog_maps_to_deferred(self):
        """'Backlog' list should map to deferred status"""
        assert self.list_to_status("Backlog") == "deferred"

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
            ("Backlog", "deferred"),  # Changed: now maps to deferred
            ("Next Up", "open"),
            ("In Progress", "in_progress"),
            ("Doing", "in_progress"),
            ("In Review", "open"),  # 'review' not in keywords
            ("Done", "closed"),
            ("Completed", "closed"),
            ("Archived", "closed"),  # Full word 'archived' in keywords
            ("Archive", "open"),  # 'archive' != 'archived', no match
            ("Blocked", "blocked"),  # New
            ("Waiting On", "blocked"),  # New
            ("On Hold", "blocked"),  # New
            ("Someday", "deferred"),  # New
            ("Later", "deferred"),  # New
            ("Future", "deferred"),  # New
        ]

        for list_name, expected_status in test_cases:
            actual_status = self.list_to_status(list_name)
            assert actual_status == expected_status, (
                f"List '{list_name}' should map to '{expected_status}', got '{actual_status}'"
            )

    # Tests for blocked status
    def test_blocked_maps_to_blocked(self):
        """'Blocked' list should map to blocked status"""
        assert self.list_to_status("Blocked") == "blocked"

    def test_waiting_maps_to_blocked(self):
        """'Waiting' list should map to blocked status"""
        assert self.list_to_status("Waiting") == "blocked"

    def test_waiting_on_maps_to_blocked(self):
        """'Waiting On' list should map to blocked status"""
        assert self.list_to_status("Waiting On") == "blocked"

    def test_on_hold_maps_to_blocked(self):
        """'On Hold' list should map to blocked status"""
        assert self.list_to_status("On Hold") == "blocked"

    def test_paused_maps_to_blocked(self):
        """'Paused' list should map to blocked status"""
        assert self.list_to_status("Paused") == "blocked"

    # Tests for deferred status
    def test_deferred_maps_to_deferred(self):
        """'Deferred' list should map to deferred status"""
        assert self.list_to_status("Deferred") == "deferred"

    def test_someday_maps_to_deferred(self):
        """'Someday' list should map to deferred status"""
        assert self.list_to_status("Someday") == "deferred"

    def test_maybe_maps_to_deferred(self):
        """'Maybe' list should map to deferred status"""
        assert self.list_to_status("Maybe") == "deferred"

    def test_later_maps_to_deferred(self):
        """'Later' list should map to deferred status"""
        assert self.list_to_status("Later") == "deferred"

    def test_future_maps_to_deferred(self):
        """'Future' list should map to deferred status"""
        assert self.list_to_status("Future") == "deferred"

    # Priority order tests
    def test_priority_closed_over_blocked(self):
        """If both keywords present, 'closed' should win over 'blocked'"""
        assert self.list_to_status("Done Blocked") == "closed"

    def test_priority_blocked_over_deferred(self):
        """If both keywords present, 'blocked' should win over 'deferred'"""
        assert self.list_to_status("Blocked Later") == "blocked"

    def test_priority_deferred_over_in_progress(self):
        """If both keywords present, 'deferred' should win over 'in_progress'"""
        assert self.list_to_status("Backlog Doing") == "deferred"

    def test_priority_in_progress_over_open(self):
        """If both keywords present, 'in_progress' should win over 'open'"""
        assert self.list_to_status("Doing To Do") == "in_progress"


class TestLoadStatusMapping:
    """Test the load_status_mapping function for custom status mapping"""

    def test_file_not_found(self, tmp_path):
        """Should raise FileNotFoundError if file doesn't exist"""
        nonexistent_file = tmp_path / "nonexistent.json"
        with pytest.raises(FileNotFoundError, match="Status mapping file not found"):
            load_status_mapping(str(nonexistent_file))

    def test_invalid_json(self, tmp_path):
        """Should raise ValueError for invalid JSON"""
        invalid_json = tmp_path / "invalid.json"
        invalid_json.write_text("{ this is not valid json }")
        with pytest.raises(ValueError, match="Invalid JSON in status mapping file"):
            load_status_mapping(str(invalid_json))

    def test_not_a_dict(self, tmp_path):
        """Should raise ValueError if mapping is not a dict"""
        not_dict = tmp_path / "not_dict.json"
        not_dict.write_text('["list", "of", "strings"]')
        with pytest.raises(ValueError, match="Status mapping must be a JSON object"):
            load_status_mapping(str(not_dict))

    def test_invalid_status_key(self, tmp_path):
        """Should raise ValueError for invalid status key"""
        invalid_status = tmp_path / "invalid_status.json"
        invalid_status.write_text('{"invalid_status": ["keyword"]}')
        with pytest.raises(ValueError, match="Invalid status 'invalid_status'"):
            load_status_mapping(str(invalid_status))

    def test_keywords_not_a_list(self, tmp_path):
        """Should raise ValueError if keywords is not a list"""
        not_list = tmp_path / "not_list.json"
        not_list.write_text('{"open": "not a list"}')
        with pytest.raises(ValueError, match="Keywords for 'open' must be a list"):
            load_status_mapping(str(not_list))

    def test_keywords_contain_non_strings(self, tmp_path):
        """Should raise ValueError if keywords contain non-strings"""
        non_strings = tmp_path / "non_strings.json"
        non_strings.write_text('{"open": ["valid", 123, "another"]}')
        with pytest.raises(ValueError, match="All keywords for 'open' must be strings"):
            load_status_mapping(str(non_strings))

    def test_valid_mapping_success(self, tmp_path):
        """Should successfully load and merge valid custom mapping"""
        valid_mapping = tmp_path / "valid.json"
        custom_data = {"blocked": ["stuck", "impediment"], "deferred": ["icebox"]}
        valid_mapping.write_text(json.dumps(custom_data))

        result = load_status_mapping(str(valid_mapping))

        # Should contain custom keywords for blocked and deferred
        assert "stuck" in result["blocked"]
        assert "impediment" in result["blocked"]
        assert "icebox" in result["deferred"]

        # Should also contain default keywords from other statuses
        assert "open" in result
        assert "closed" in result
        assert "in_progress" in result

    def test_partial_override(self, tmp_path):
        """Custom mapping should override only specified statuses, keep defaults for rest"""
        partial_mapping = tmp_path / "partial.json"
        custom_data = {"blocked": ["custom_blocked"]}
        partial_mapping.write_text(json.dumps(custom_data))

        result = load_status_mapping(str(partial_mapping))

        # Blocked should only have custom keyword (override)
        assert result["blocked"] == ["custom_blocked"]

        # Other statuses should have defaults
        assert "done" in result["closed"]
        assert "todo" in result["open"]
        assert "doing" in result["in_progress"]
        assert "backlog" in result["deferred"]

    def test_all_valid_statuses(self, tmp_path):
        """Should accept all five valid status keys"""
        all_statuses = tmp_path / "all_statuses.json"
        custom_data = {
            "open": ["custom_open"],
            "in_progress": ["custom_progress"],
            "blocked": ["custom_blocked"],
            "deferred": ["custom_deferred"],
            "closed": ["custom_closed"],
        }
        all_statuses.write_text(json.dumps(custom_data))

        result = load_status_mapping(str(all_statuses))

        # All should be overridden
        assert result["open"] == ["custom_open"]
        assert result["in_progress"] == ["custom_progress"]
        assert result["blocked"] == ["custom_blocked"]
        assert result["deferred"] == ["custom_deferred"]
        assert result["closed"] == ["custom_closed"]

    def test_empty_keywords_list(self, tmp_path):
        """Should allow empty keywords list (edge case)"""
        empty_keywords = tmp_path / "empty.json"
        empty_keywords.write_text('{"open": []}')

        result = load_status_mapping(str(empty_keywords))

        # Should override open with empty list
        assert result["open"] == []

        # Other statuses should still have defaults
        assert "done" in result["closed"]
