"""
Unit tests for Trello URL resolution logic
"""

import re

# Import the URL resolution logic
# For now, recreate the regex pattern here (will be refactored to import later)


class TestTrelloURLPattern:
    """Test the Trello URL regex pattern"""

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
