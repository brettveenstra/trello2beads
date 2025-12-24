#!/usr/bin/env python3
"""
trello2beads - High-fidelity Trello board migration to beads issue tracking

Usage:
    export TRELLO_API_KEY="your-key"
    export TRELLO_TOKEN="your-token"
    export TRELLO_BOARD_ID="your-board-id"

    # Initialize beads database
    mkdir my-project && cd my-project
    bd init --prefix myproject

    # Run conversion
    python3 trello2beads.py

    # Or dry-run to preview
    python3 trello2beads.py --dry-run

    # Use custom status mapping
    python3 trello2beads.py --status-mapping custom_mapping.json

For full documentation, see README.md
"""

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, cast

import requests

# Configure logging
logger = logging.getLogger(__name__)


class TrelloAPIError(Exception):
    """Base exception for Trello API errors"""

    def __init__(
        self, message: str, status_code: int | None = None, response_text: str | None = None
    ):
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(message)


class TrelloAuthenticationError(TrelloAPIError):
    """Raised when API credentials are invalid or expired (401/403)"""

    pass


class TrelloNotFoundError(TrelloAPIError):
    """Raised when a board, card, or resource is not found (404)"""

    pass


class TrelloRateLimitError(TrelloAPIError):
    """Raised when rate limit is exceeded (429) after retries"""

    pass


class TrelloServerError(TrelloAPIError):
    """Raised when Trello's servers return an error (500/502/503/504)"""

    pass


class BeadsWriterError(Exception):
    """Base exception for BeadsWriter errors"""

    def __init__(
        self,
        message: str,
        command: list[str] | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        returncode: int | None = None,
    ):
        self.command = command
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        super().__init__(message)


class BeadsCommandError(BeadsWriterError):
    """Raised when bd CLI is not found or not executable"""

    pass


class BeadsIssueCreationError(BeadsWriterError):
    """Raised when issue creation fails"""

    pass


class BeadsUpdateError(BeadsWriterError):
    """Raised when issue update fails"""

    pass


class RateLimiter:
    """Token bucket rate limiter for API requests

    Implements a token bucket algorithm to ensure API requests respect rate limits.
    Tokens are replenished at a constant rate and consumed for each request.
    """

    def __init__(self, requests_per_second: float, burst_allowance: int = 5):
        """
        Initialize rate limiter

        Args:
            requests_per_second: Sustained rate limit (tokens added per second)
            burst_allowance: Maximum tokens in bucket (allows short bursts)
        """
        self.rate = requests_per_second
        self.burst_allowance = burst_allowance
        self.tokens = float(burst_allowance)
        self.last_update = time.time()
        self._lock = threading.Lock()

    def acquire(self, timeout: float = 5.0) -> bool:
        """
        Acquire permission to make a request

        Blocks until a token is available or timeout is reached.

        Args:
            timeout: Maximum time to wait for permission (seconds)

        Returns:
            True if permission granted, False if timeout
        """
        deadline = time.time() + timeout

        while time.time() < deadline:
            with self._lock:
                now = time.time()
                # Add tokens based on time elapsed
                time_passed = now - self.last_update
                self.tokens = min(self.burst_allowance, self.tokens + time_passed * self.rate)
                self.last_update = now

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return True

            # Wait a short time before trying again
            time.sleep(0.01)

        return False  # Timeout

    def get_status(self) -> dict[str, Any]:
        """Get current rate limiter status for debugging"""
        with self._lock:
            return {
                "available_tokens": self.tokens,
                "max_tokens": self.burst_allowance,
                "rate_per_second": self.rate,
                "utilization_percent": (1 - self.tokens / self.burst_allowance) * 100,
            }


class TrelloReader:
    """Read data from Trello API with rate limiting

    Trello API rate limits (per token):
    - 100 requests per 10 seconds = 10 req/sec sustained
    - 300 requests per 10 seconds per API key = 30 req/sec

    We use 10 req/sec with burst allowance of 10 for conservative usage.
    """

    def __init__(
        self, api_key: str, token: str, board_id: str | None = None, board_url: str | None = None
    ):
        self.api_key = api_key
        self.token = token
        self.base_url = "https://api.trello.com/1"

        # Rate limiter: 10 requests/sec, burst up to 10
        # Conservative limit to respect Trello's 100 req/10sec token limit
        self.rate_limiter = RateLimiter(requests_per_second=10.0, burst_allowance=10)

        # Board ID can be provided directly or extracted from URL
        # Note: board_id is optional - only required for board-specific operations
        self.board_id: str | None
        if board_url:
            self.board_id = self.parse_board_url(board_url)
        elif board_id:
            self.board_id = board_id
        else:
            self.board_id = None  # Will be required for board-specific methods

    @staticmethod
    def parse_board_url(url: str) -> str:
        """Extract board ID from Trello URL

        Supports formats:
        - https://trello.com/b/Bm0nnz1R/board-name
        - https://trello.com/b/Bm0nnz1R
        - trello.com/b/Bm0nnz1R/board-name

        Args:
            url: Trello board URL

        Returns:
            Board ID (8-character alphanumeric string)

        Raises:
            ValueError: If URL format is invalid or board ID cannot be extracted
        """
        import re

        if not url:
            raise ValueError("URL cannot be empty")

        # Match Trello board URL patterns
        # Captures the board ID (e.g., Bm0nnz1R) from various URL formats
        patterns = [
            r"trello\.com/b/([a-zA-Z0-9]+)",  # Matches with or without https://
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        raise ValueError(f"Could not extract board ID from URL: {url}")

    def _request(self, endpoint: str, params: dict | None = None) -> Any:
        """Make authenticated request to Trello API with rate limiting and retry logic"""
        # Acquire rate limiter token before making request
        if not self.rate_limiter.acquire(timeout=30.0):
            raise RuntimeError("Rate limiter timeout - too many requests queued")

        url = f"{self.base_url}/{endpoint}"
        auth_params = {"key": self.api_key, "token": self.token}
        if params:
            auth_params.update(params)

        # Retry logic with exponential backoff for transient failures
        max_retries = 3
        base_delay = 1.0
        retry_statuses = {429, 500, 502, 503, 504}  # Transient errors

        last_exception: requests.RequestException | None = None
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=auth_params, timeout=30)
                response.raise_for_status()
                return cast(Any, response.json())

            except requests.HTTPError as e:
                last_exception = e
                status_code = e.response.status_code if e.response else 0
                response_text = e.response.text if e.response else ""

                # Handle non-retryable errors with helpful messages
                if status_code not in retry_statuses:
                    if status_code == 401:
                        raise TrelloAuthenticationError(
                            "Invalid API credentials. Check your TRELLO_API_KEY and TRELLO_TOKEN.\n"
                            "Get credentials at: https://trello.com/power-ups/admin",
                            status_code=status_code,
                            response_text=response_text,
                        ) from e
                    elif status_code == 403:
                        raise TrelloAuthenticationError(
                            f"Access forbidden to resource: {endpoint}\n"
                            "Your API token may not have permission to access this board.",
                            status_code=status_code,
                            response_text=response_text,
                        ) from e
                    elif status_code == 404:
                        raise TrelloNotFoundError(
                            f"Resource not found: {endpoint}\n"
                            "Check that your board ID is correct and the board exists.",
                            status_code=status_code,
                            response_text=response_text,
                        ) from e
                    else:
                        # Other non-retryable HTTP errors
                        raise TrelloAPIError(
                            f"HTTP {status_code} error for {endpoint}: {response_text[:200]}",
                            status_code=status_code,
                            response_text=response_text,
                        ) from e

                # Don't delay after last attempt
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)  # Exponential backoff: 1s, 2s, 4s
                    time.sleep(delay)

            except requests.RequestException as e:
                # Network errors, timeouts, etc.
                last_exception = e
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    time.sleep(delay)
                else:
                    # Network error after all retries
                    raise TrelloAPIError(
                        f"Network error after {max_retries} attempts: {str(e)}\n"
                        "Check your internet connection and try again.",
                        status_code=None,
                        response_text=None,
                    ) from e

        # All retries exhausted for transient HTTP errors
        if last_exception and isinstance(last_exception, requests.HTTPError):
            status_code = last_exception.response.status_code if last_exception.response else 0
            response_text = last_exception.response.text if last_exception.response else ""

            if status_code == 429:
                raise TrelloRateLimitError(
                    f"Rate limit exceeded after {max_retries} retry attempts.\n"
                    "Trello's API rate limit: 100 requests per 10 seconds.\n"
                    "Wait a few minutes and try again.",
                    status_code=status_code,
                    response_text=response_text,
                ) from last_exception
            elif status_code in {500, 502, 503, 504}:
                raise TrelloServerError(
                    f"Trello server error (HTTP {status_code}) persisted after {max_retries} retries.\n"
                    "Trello's servers may be experiencing issues. Try again later.",
                    status_code=status_code,
                    response_text=response_text,
                ) from last_exception

        # Fallback for unexpected cases
        if last_exception:
            raise TrelloAPIError(
                f"Request failed after {max_retries} retries: {str(last_exception)}",
                status_code=None,
                response_text=None,
            ) from last_exception

        raise RuntimeError("Request failed after retries")

    def _paginated_request(self, endpoint: str, params: dict | None = None) -> list[dict]:
        """Make paginated requests to handle Trello's 1000-item limit

        Trello API limits responses to 1000 items. This method automatically
        paginates using the 'before' parameter to fetch all results.

        Args:
            endpoint: API endpoint to request
            params: Query parameters (will add limit=1000 and before as needed)

        Returns:
            Complete list of all items across all pages
        """
        all_items: list[dict] = []
        request_params = params.copy() if params else {}
        request_params["limit"] = 1000  # Maximum allowed by Trello

        while True:
            # Fetch one page
            page_items = self._request(endpoint, request_params)

            if not isinstance(page_items, list):
                # Not a list response, return as-is
                return cast(list[dict], page_items)

            if not page_items:
                # Empty page means we're done
                break

            all_items.extend(page_items)

            # If we got less than 1000 items, we've reached the end
            if len(page_items) < 1000:
                break

            # Use the ID of the last item as the 'before' parameter for next page
            # Trello accepts IDs directly (converts to timestamp internally)
            last_item_id = page_items[-1].get("id")
            if not last_item_id:
                # No ID field, can't paginate further
                break

            request_params["before"] = last_item_id

        return all_items

    def get_board(self) -> dict:
        """Get board info"""
        if not self.board_id:
            raise ValueError(
                "board_id is required for this operation. "
                "Initialize TrelloReader with board_id or board_url parameter."
            )
        return cast(dict, self._request(f"boards/{self.board_id}", {"fields": "name,desc,url"}))

    def list_boards(self, filter_status: str = "open") -> list[dict]:
        """List all boards accessible to the authenticated user

        Useful for discovering board IDs and URLs when you're not sure which
        board to migrate.

        Args:
            filter_status: Filter boards by status. Options:
                - "open" (default): Only open (active) boards
                - "closed": Only closed (archived) boards
                - "all": Both open and closed boards

        Returns:
            List of board dictionaries with id, name, url, and closed status

        Example:
            >>> reader = TrelloReader(api_key="...", token="...")
            >>> boards = reader.list_boards()
            >>> for board in boards:
            ...     print(f"{board['name']}: {board['url']}")
        """
        valid_filters = {"open", "closed", "all"}
        if filter_status not in valid_filters:
            raise ValueError(
                f"Invalid filter_status: '{filter_status}'. Must be one of: {valid_filters}"
            )

        boards = self._request(
            "members/me/boards",
            {"fields": "name,url,closed,dateLastActivity", "filter": filter_status},
        )
        return cast(list[dict], boards)

    def get_lists(self) -> list[dict]:
        """Get all lists on the board"""
        if not self.board_id:
            raise ValueError(
                "board_id is required for this operation. "
                "Initialize TrelloReader with board_id or board_url parameter."
            )
        return cast(
            list[dict], self._request(f"boards/{self.board_id}/lists", {"fields": "name,id,pos"})
        )

    def get_cards(self) -> list[dict]:
        """Get all cards with full relationships (supports pagination for >1000 cards)

        Fetches cards with complete relationship data in a single request:
        - Attachments (files, links)
        - Checklists (with completion status)
        - Members (assigned users)
        - Custom field items (custom field values)
        - Stickers (visual decorations)
        """
        if not self.board_id:
            raise ValueError(
                "board_id is required for this operation. "
                "Initialize TrelloReader with board_id or board_url parameter."
            )
        cards = self._paginated_request(
            f"boards/{self.board_id}/cards",
            {
                "attachments": "true",
                "checklists": "all",
                "members": "true",
                "customFieldItems": "true",
                "stickers": "true",
                "fields": "all",
            },
        )
        return cards

    def get_card_comments(self, card_id: str) -> list[dict]:
        """Get all comments for a card (supports pagination for >1000 comments)"""
        comments = self._paginated_request(f"cards/{card_id}/actions", {"filter": "commentCard"})
        return comments


class BeadsWriter:
    """Write issues to beads via bd CLI"""

    def __init__(self, db_path: str | None = None, dry_run: bool = False):
        """Initialize with optional custom database path and dry-run mode

        Args:
            db_path: Path to beads database file (optional)
            dry_run: If True, print commands instead of executing them (default: False)

        Raises:
            BeadsCommandError: If bd CLI is not available (skipped in dry-run mode)
        """
        self.db_path = db_path
        self.dry_run = dry_run

        # Skip pre-flight check in dry-run mode
        if not dry_run:
            self._check_bd_available()

        mode = " (dry-run mode)" if dry_run else ""
        db_info = f" with db_path={db_path}" if db_path else ""
        logger.info("BeadsWriter initialized%s%s", db_info, mode)

    def _check_bd_available(self) -> None:
        """Verify that bd CLI is available and executable

        Raises:
            BeadsCommandError: If bd CLI is not found or not executable
        """
        try:
            result = subprocess.run(
                ["bd", "--help"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                raise BeadsCommandError(
                    "bd CLI is not working properly. "
                    "Ensure beads is installed and in your PATH.\n"
                    "Install: https://github.com/niutech/beads",
                    command=["bd", "--help"],
                    stdout=result.stdout,
                    stderr=result.stderr,
                    returncode=result.returncode,
                )
            logger.debug("bd CLI pre-flight check passed")
        except FileNotFoundError as e:
            raise BeadsCommandError(
                "bd CLI not found. Ensure beads is installed and in your PATH.\n"
                "Install: https://github.com/niutech/beads",
                command=["bd", "--help"],
            ) from e
        except subprocess.TimeoutExpired as e:
            raise BeadsCommandError(
                "bd CLI timed out. There may be an issue with your beads installation.",
                command=["bd", "--help"],
            ) from e

    def _parse_issue_id(self, output: str) -> str | None:
        """Parse issue ID from bd CLI output using regex

        Args:
            output: The stdout output from bd create command

        Returns:
            Parsed issue ID if found, None otherwise

        Examples:
            >>> _parse_issue_id("✓ Created issue: trello2beads-abc")
            'trello2beads-abc'
            >>> _parse_issue_id("Created issue: myproject-123")
            'myproject-123'
        """
        # Pattern matches various bd output formats:
        # - "✓ Created issue: project-id"
        # - "Created issue: project-id"
        # - "Issue created: project-id"
        # Issue ID format: prefix-alphanumeric (e.g., trello2beads-abc, project-123)
        patterns = [
            r"Created issue:\s+([a-zA-Z0-9]+-[a-zA-Z0-9]+)",  # Standard format
            r"Issue created:\s+([a-zA-Z0-9]+-[a-zA-Z0-9]+)",  # Alternative format
            r"✓\s+Created\s+([a-zA-Z0-9]+-[a-zA-Z0-9]+)",  # Compact format
        ]

        for pattern in patterns:
            match = re.search(pattern, output, re.MULTILINE | re.IGNORECASE)
            if match:
                issue_id = match.group(1)
                logger.debug("Parsed issue ID: %s using pattern: %s", issue_id, pattern)
                return issue_id

        logger.debug("No issue ID found in output using any pattern")
        return None

    def _validate_issue_id(self, issue_id: str) -> bool:
        """Validate that issue ID matches expected beads format

        Args:
            issue_id: The issue ID to validate

        Returns:
            True if valid, False otherwise

        Examples:
            >>> _validate_issue_id("trello2beads-abc")
            True
            >>> _validate_issue_id("project-123")
            True
            >>> _validate_issue_id("invalid")
            False
            >>> _validate_issue_id("")
            False
        """
        # Beads issue IDs follow format: prefix-suffix
        # Prefix: project name (alphanumeric, hyphens allowed)
        # Suffix: short hash (alphanumeric, typically 3-8 chars)
        # Examples: trello2beads-abc, myproject-x7z, project-name-123
        pattern = r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+$"
        is_valid = bool(re.match(pattern, issue_id))

        if not is_valid:
            logger.warning(
                "Issue ID validation failed: %s (expected format: prefix-suffix)", issue_id
            )

        return is_valid

    def _validate_inputs(
        self,
        title: str,
        description: str,
        status: str,
        priority: int,
        issue_type: str,
        labels: list[str] | None,
    ) -> None:
        """Validate inputs before calling bd CLI

        Args:
            title: Issue title
            description: Issue description
            status: Issue status
            priority: Issue priority
            issue_type: Issue type
            labels: List of labels

        Raises:
            ValueError: If any input is invalid
        """
        # Validate title
        if not title or not title.strip():
            raise ValueError("Title cannot be empty")

        if len(title) > 500:
            raise ValueError(f"Title too long ({len(title)} chars). Maximum 500 characters.")

        # Validate description length (reasonable limit)
        if len(description) > 50000:
            raise ValueError(
                f"Description too long ({len(description)} chars). Maximum 50000 characters."
            )

        # Validate status
        valid_statuses = {"open", "in_progress", "blocked", "deferred", "closed"}
        if status not in valid_statuses:
            raise ValueError(
                f"Invalid status: '{status}'. Must be one of: {sorted(valid_statuses)}"
            )

        # Validate priority
        if not isinstance(priority, int):
            raise ValueError(f"Priority must be an integer, got: {type(priority).__name__}")

        if not 0 <= priority <= 4:
            raise ValueError(f"Priority must be 0-4, got: {priority}")

        # Validate issue_type
        valid_types = {"task", "bug", "feature", "epic", "chore"}
        if issue_type not in valid_types:
            raise ValueError(
                f"Invalid issue_type: '{issue_type}'. Must be one of: {sorted(valid_types)}"
            )

        # Validate labels
        if labels is not None:
            if not isinstance(labels, list):
                raise ValueError(f"Labels must be a list, got: {type(labels).__name__}")

            for label in labels:
                if not isinstance(label, str):
                    raise ValueError(
                        f"All labels must be strings, got: {type(label).__name__} in {labels}"
                    )

                if not label.strip():
                    raise ValueError("Labels cannot be empty strings")

                # Check for problematic characters that might break command line
                if "," in label:
                    raise ValueError(
                        f"Label contains comma (reserved separator): '{label}'. "
                        f"Use alternative punctuation."
                    )

    def create_issue(
        self,
        title: str,
        description: str = "",
        status: str = "open",
        priority: int = 2,
        issue_type: str = "task",
        labels: list[str] | None = None,
        external_ref: str | None = None,
    ) -> str:
        """Create a beads issue and return its ID

        Args:
            title: Issue title
            description: Issue description (optional)
            status: Issue status (default: "open")
            priority: Issue priority 0-4 (default: 2)
            issue_type: Issue type (default: "task")
            labels: List of labels (optional)
            external_ref: External reference ID (optional)

        Returns:
            Created issue ID

        Raises:
            ValueError: If inputs are invalid
            BeadsIssueCreationError: If issue creation fails
        """
        # Validate inputs before calling bd CLI
        self._validate_inputs(title, description, status, priority, issue_type, labels)

        cmd = ["bd"]

        # Add --db flag if custom database specified
        if self.db_path:
            cmd.extend(["--db", self.db_path])

        cmd.extend(
            [
                "create",
                "--title",
                title,
                "--description",
                description,
                "--priority",
                str(priority),
                "--type",
                issue_type,
            ]
        )

        # Add labels if provided
        if labels:
            cmd.extend(["--labels", ",".join(labels)])

        # Add external reference if provided
        if external_ref:
            cmd.extend(["--external-ref", external_ref])

        logger.info("Creating issue: %s (type=%s, priority=%d)", title, issue_type, priority)
        logger.debug("Command: %s", " ".join(cmd))

        # Dry-run mode: print command instead of executing
        if self.dry_run:
            print(f"[DRY-RUN] Would execute: {' '.join(cmd)}")
            # Return a mock issue ID for dry-run mode
            mock_id = "dryrun-mock"
            logger.info("[DRY-RUN] Mock issue ID: %s", mock_id)
            return mock_id

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired as e:
            raise BeadsIssueCreationError(
                f"Issue creation timed out after 30 seconds.\n"
                f"Title: {title}\n"
                f"Command: {' '.join(cmd)}",
                command=cmd,
            ) from e
        except Exception as e:
            raise BeadsIssueCreationError(
                f"Unexpected error creating issue.\nTitle: {title}\nError: {e}",
                command=cmd,
            ) from e

        if result.returncode != 0:
            error_msg = (
                f"Failed to create issue.\n"
                f"Title: {title}\n"
                f"Command: {' '.join(cmd)}\n"
                f"Exit code: {result.returncode}\n"
                f"Error output: {result.stderr.strip() if result.stderr else '(none)'}\n"
                f"\nSuggestion: Check that your beads database is initialized "
                f"(run 'bd init') and permissions are correct."
            )
            logger.error("Issue creation failed: %s", error_msg)
            raise BeadsIssueCreationError(
                error_msg,
                command=cmd,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )

        # Parse issue ID from output using regex (robust parsing)
        issue_id = self._parse_issue_id(result.stdout)

        if not issue_id:
            error_msg = (
                f"Could not parse issue ID from bd output.\n"
                f"Title: {title}\n"
                f"Output: {result.stdout}\n"
                f"\nSuggestion: This may indicate a bd CLI version incompatibility. "
                f"Update beads to the latest version."
            )
            logger.error("Issue ID parsing failed: %s", error_msg)
            raise BeadsIssueCreationError(
                error_msg,
                command=cmd,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )

        # Validate issue ID format
        if not self._validate_issue_id(issue_id):
            error_msg = (
                f"Parsed issue ID has invalid format: {issue_id}\n"
                f"Title: {title}\n"
                f"Expected format: prefix-suffix (e.g., trello2beads-abc)\n"
                f"\nSuggestion: This may indicate a bd CLI output format change. "
                f"Check bd version and update if needed."
            )
            logger.error("Issue ID validation failed: %s", error_msg)
            raise BeadsIssueCreationError(
                error_msg,
                command=cmd,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )

        logger.info("Created issue: %s", issue_id)

        # Update status if not 'open' (bd create defaults to open)
        if status != "open":
            self.update_status(issue_id, status)

        return issue_id

    def update_status(self, issue_id: str, status: str) -> None:
        """Update issue status

        Args:
            issue_id: Issue ID to update
            status: New status value

        Raises:
            ValueError: If inputs are invalid
            BeadsUpdateError: If status update fails
        """
        # Validate inputs
        if not issue_id or not issue_id.strip():
            raise ValueError("Issue ID cannot be empty")

        valid_statuses = {"open", "in_progress", "blocked", "deferred", "closed"}
        if status not in valid_statuses:
            raise ValueError(
                f"Invalid status: '{status}'. Must be one of: {sorted(valid_statuses)}"
            )

        cmd = ["bd"]

        if self.db_path:
            cmd.extend(["--db", self.db_path])

        cmd.extend(["update", issue_id, "--status", status])

        logger.info("Updating %s status to: %s", issue_id, status)
        logger.debug("Command: %s", " ".join(cmd))

        # Dry-run mode: print command instead of executing
        if self.dry_run:
            print(f"[DRY-RUN] Would execute: {' '.join(cmd)}")
            logger.info("[DRY-RUN] Would update %s status to %s", issue_id, status)
            return

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired as e:
            raise BeadsUpdateError(
                f"Status update timed out after 30 seconds.\n"
                f"Issue: {issue_id}\n"
                f"Status: {status}\n"
                f"Command: {' '.join(cmd)}",
                command=cmd,
            ) from e
        except Exception as e:
            raise BeadsUpdateError(
                f"Unexpected error updating status.\n"
                f"Issue: {issue_id}\n"
                f"Status: {status}\n"
                f"Error: {e}",
                command=cmd,
            ) from e

        if result.returncode != 0:
            error_msg = (
                f"Failed to update issue status.\n"
                f"Issue: {issue_id}\n"
                f"Status: {status}\n"
                f"Command: {' '.join(cmd)}\n"
                f"Exit code: {result.returncode}\n"
                f"Error output: {result.stderr.strip() if result.stderr else '(none)'}\n"
                f"\nSuggestion: Verify the issue ID exists and the status value is valid "
                f"(open, in_progress, blocked, deferred, closed)."
            )
            logger.error("Status update failed: %s", error_msg)
            raise BeadsUpdateError(
                error_msg,
                command=cmd,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )

        logger.debug("Status update successful")


class TrelloToBeadsConverter:
    """Convert Trello board to beads issues"""

    # Smart status mapping (conservative - only obvious cases)
    STATUS_KEYWORDS = {
        "closed": ["done", "completed", "closed", "archived", "finished"],
        "blocked": ["blocked", "waiting", "waiting on", "on hold", "paused"],
        "deferred": ["deferred", "someday", "maybe", "later", "backlog", "future"],
        "in_progress": ["doing", "in progress", "wip", "active", "current", "working"],
        "open": ["todo", "to do", "planned", "ready"],
    }

    def list_to_status(self, list_name: str) -> str:
        """Map list name to beads status (conservative)

        Priority order: closed > blocked > deferred > in_progress > open
        This ensures definitive states take precedence over ambiguous ones.
        """
        list_lower = list_name.lower()
        keywords = self.status_keywords

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

    def _resolve_card_references(
        self, cards: list[dict], comments_by_card: dict[str, list[dict]]
    ) -> int:
        """
        Second pass: Find Trello card URLs in descriptions/attachments/comments
        and replace with beads issue references
        """
        import re

        resolved_count = 0

        # Regex patterns for Trello card URLs
        # Matches: https://trello.com/c/abc123 or trello.com/c/abc123/card-name
        trello_url_pattern = re.compile(r"(?:https?://)?trello\.com/c/([a-zA-Z0-9]+)(?:/[^\s\)]*)?")

        for card in cards:
            beads_id = self.trello_to_beads.get(card["id"])
            if not beads_id:
                continue

            # Get current description from card
            original_desc = card.get("desc", "")
            updated_desc = original_desc
            replacements_made = False

            # Find all Trello URLs in description
            matches = trello_url_pattern.finditer(original_desc)

            for match in matches:
                full_url = match.group(0)
                short_link = match.group(1)  # The abc123 part

                # Look up what beads issue this Trello card maps to
                target_beads_id = self.card_url_map.get(short_link)

                if target_beads_id:
                    # Replace Trello URL with beads reference
                    beads_ref = f"See {target_beads_id}"
                    updated_desc = updated_desc.replace(full_url, beads_ref)
                    replacements_made = True
                    print(f"  ✓ Resolved {short_link} → {target_beads_id} in description")

            # Process comments for Trello URLs
            card_comments = comments_by_card.get(card["id"], [])
            updated_comments = []

            for comment in card_comments:
                comment_text = comment["data"]["text"]
                updated_text = comment_text

                # Find and replace Trello URLs in comment
                matches = trello_url_pattern.finditer(comment_text)
                for match in matches:
                    full_url = match.group(0)
                    short_link = match.group(1)
                    target_beads_id = self.card_url_map.get(short_link)

                    if target_beads_id:
                        beads_ref = f"See {target_beads_id}"
                        updated_text = updated_text.replace(full_url, beads_ref)
                        replacements_made = True
                        print(f"  ✓ Resolved {short_link} → {target_beads_id} in comment")

                # Store updated comment
                updated_comment = comment.copy()
                updated_comment["data"] = comment["data"].copy()
                updated_comment["data"]["text"] = updated_text
                updated_comments.append(updated_comment)

            # Also check attachments for Trello card links
            attachment_refs = []
            if card.get("attachments"):
                for att in card["attachments"]:
                    att_url = att.get("url", "")
                    att_match: re.Match[str] | None = trello_url_pattern.search(att_url)

                    if att_match:
                        short_link = att_match.group(1)
                        target_beads_id = self.card_url_map.get(short_link)

                        if target_beads_id:
                            attachment_refs.append(
                                {"name": att["name"], "beads_id": target_beads_id}
                            )
                            replacements_made = True
                            print(f"  ✓ Attachment '{att['name']}' → {target_beads_id}")

            # If we made any replacements, rebuild and update the full description
            if replacements_made:
                # Rebuild the full description with all sections
                desc_parts = []

                if updated_desc:
                    desc_parts.append(updated_desc)

                # Add checklists (unchanged)
                if card.get("checklists"):
                    desc_parts.append("\n## Checklists\n")
                    for checklist in card["checklists"]:
                        desc_parts.append(f"### {checklist['name']}\n")
                        for item in checklist.get("checkItems", []):
                            status_mark = "✓" if item["state"] == "complete" else "☐"
                            desc_parts.append(f"- [{status_mark}] {item['name']}")
                        desc_parts.append("")

                # Add attachments (with references if any)
                if card.get("attachments"):
                    desc_parts.append("\n## Attachments\n")
                    for att in card["attachments"]:
                        desc_parts.append(
                            f"- [{att['name']}]({att['url']}) ({att.get('bytes', 0)} bytes)"
                        )
                    desc_parts.append("")

                # Add attachment references if any
                if attachment_refs:
                    desc_parts.append("\n## Related Issues (from attachments)\n")
                    for ref in attachment_refs:
                        desc_parts.append(f"- **{ref['name']}**: See {ref['beads_id']}\n")

                # Add comments (with resolved URLs if changed)
                if updated_comments:
                    desc_parts.append("\n## Comments\n")
                    for comment in reversed(updated_comments):  # Oldest first
                        author = comment.get("memberCreator", {}).get("fullName", "Unknown")
                        date = comment.get("date", "")[:10]
                        text = comment["data"]["text"]

                        desc_parts.append(f"**{author}** ({date}):")
                        desc_parts.append(f"> {text}")
                        desc_parts.append("")

                full_description = "\n".join(desc_parts)

                # Update the beads issue description
                self._update_description(beads_id, full_description)
                resolved_count += 1

        return resolved_count

    def _update_description(self, issue_id: str, new_description: str) -> None:
        """Update beads issue description"""
        cmd = ["bd"]

        if self.beads.db_path:
            cmd.extend(["--db", self.beads.db_path])

        cmd.extend(["update", issue_id, "--description", new_description])

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"    ⚠️  Warning: Failed to update description for {issue_id}: {result.stderr}")

    def __init__(
        self,
        trello: TrelloReader,
        beads: BeadsWriter,
        status_keywords: dict[str, list[str]] | None = None,
    ):
        self.trello = trello
        self.beads = beads
        self.list_map: dict[str, str] = {}  # Trello list ID -> name
        self.trello_to_beads: dict[str, str] = {}  # Trello card ID -> beads issue ID
        self.card_url_map: dict[str, str] = {}  # Trello short URL -> beads issue ID

        # Use custom keywords or fall back to class defaults
        self.status_keywords = (
            status_keywords if status_keywords is not None else self.STATUS_KEYWORDS
        )

    def convert(self, dry_run: bool = False, snapshot_path: str | None = None) -> None:
        """Perform the conversion"""
        print("🔄 Starting Trello → Beads conversion...")
        print()

        # PASS 0: Fetch from Trello and save snapshot (or load existing)
        if snapshot_path and Path(snapshot_path).exists():
            print(f"📂 Loading existing snapshot: {snapshot_path}")
            with open(snapshot_path) as f:
                snapshot = json.load(f)
            board = snapshot["board"]
            lists = snapshot["lists"]
            cards = snapshot["cards"]
            comments_by_card = snapshot.get("comments", {})
            print(f"✅ Loaded {len(cards)} cards from snapshot")
        else:
            print("🌐 Fetching from Trello API...")
            board = self.trello.get_board()
            lists = self.trello.get_lists()
            cards = self.trello.get_cards()

            # Fetch comments for cards that have them
            print("💬 Fetching comments...")
            comments_by_card = {}
            cards_with_comments = [c for c in cards if c.get("badges", {}).get("comments", 0) > 0]

            for i, card in enumerate(cards_with_comments, 1):
                card_id = card["id"]
                comments = self.trello.get_card_comments(card_id)
                if comments:
                    comments_by_card[card_id] = comments
                    print(
                        f"  {i}/{len(cards_with_comments)}: {len(comments)} comments on '{card['name']}'"
                    )

            # Save snapshot for debugging/re-runs
            snapshot = {
                "board": board,
                "lists": lists,
                "cards": cards,
                "comments": comments_by_card,
                "timestamp": Path(__file__).stat().st_mtime,  # Use file mtime as proxy
            }

            if snapshot_path:
                Path(snapshot_path).parent.mkdir(parents=True, exist_ok=True)
                with open(snapshot_path, "w") as f:
                    json.dump(snapshot, f, indent=2)
                print(f"💾 Saved snapshot: {snapshot_path}")

        print(f"\n📋 Board: {board['name']}")
        print(f"   URL: {board['url']}")
        print(f"📝 Lists: {len(lists)}")
        print(f"🎴 Cards: {len(cards)}")
        print()

        # Build list map
        for lst in lists:
            self.list_map[lst["id"]] = lst["name"]

        # Sort cards by position
        cards_sorted = sorted(cards, key=lambda c: (c["idList"], c.get("pos", 0)))

        # FIRST PASS: Create all issues and build mapping
        print("🔄 Pass 1: Creating beads issues...")
        created_count = 0
        for card in cards_sorted:
            list_name = self.list_map.get(card["idList"], "Unknown")
            status = self.list_to_status(list_name)

            # Create labels: preserve list name for querying
            labels = [f"list:{list_name}"]

            # Add original Trello labels if present
            if card.get("labels"):
                for label in card["labels"]:
                    if label.get("name"):
                        labels.append(f"trello-label:{label['name']}")

            # External reference for debugging (Trello short link)
            external_ref = f"trello:{card['shortLink']}"

            # Build description
            desc_parts = []

            if card.get("desc"):
                desc_parts.append(card["desc"])

            # Add checklists
            if card.get("checklists"):
                desc_parts.append("\n## Checklists\n")
                for checklist in card["checklists"]:
                    desc_parts.append(f"### {checklist['name']}\n")
                    for item in checklist.get("checkItems", []):
                        status_mark = "✓" if item["state"] == "complete" else "☐"
                        desc_parts.append(f"- [{status_mark}] {item['name']}")
                    desc_parts.append("")

            # Add attachments
            if card.get("attachments"):
                desc_parts.append("\n## Attachments\n")
                for att in card["attachments"]:
                    desc_parts.append(
                        f"- [{att['name']}]({att['url']}) ({att.get('bytes', 0)} bytes)"
                    )
                desc_parts.append("")

            # Add comments
            card_comments = comments_by_card.get(card["id"], [])
            if card_comments:
                desc_parts.append("\n## Comments\n")
                for comment in reversed(card_comments):  # Reverse to show oldest first
                    author = comment.get("memberCreator", {}).get("fullName", "Unknown")
                    date = comment.get("date", "")[:10]  # YYYY-MM-DD
                    text = comment["data"]["text"]

                    desc_parts.append(f"**{author}** ({date}):")
                    desc_parts.append(f"> {text}")
                    desc_parts.append("")

            # Store Trello URL for potential reference resolution (second pass)
            # Don't add to description yet - will be resolved in pass 2

            description = "\n".join(desc_parts)

            if dry_run:
                print("[DRY RUN] Would create:")
                print(f"  Title: {card['name']}")
                print(f"  Status: {status}")
                print(f"  List: {list_name}")
                print(f"  Labels: {', '.join(labels)}")
                print()
            else:
                try:
                    issue_id = self.beads.create_issue(
                        title=card["name"],
                        description=description,
                        status=status,
                        priority=2,
                        issue_type="task",
                        labels=labels,
                        external_ref=external_ref,
                    )

                    # Build mapping for second pass
                    self.trello_to_beads[card["id"]] = issue_id
                    self.card_url_map[card["shortUrl"]] = issue_id
                    self.card_url_map[card["shortLink"]] = issue_id

                    print(f"✅ Created {issue_id}: {card['name']} (list:{list_name})")
                    created_count += 1
                except Exception as e:
                    print(f"❌ Failed to create '{card['name']}': {e}")

        # SECOND PASS: Resolve Trello card references (if not dry run)
        if not dry_run and self.trello_to_beads:
            print()
            print("🔄 Pass 2: Resolving Trello card references...")
            resolved_count = self._resolve_card_references(cards_sorted, comments_by_card)
            print(f"✅ Resolved {resolved_count} Trello card references")

        # Summary report
        print()
        print("=" * 60)
        print("📊 CONVERSION SUMMARY")
        print("=" * 60)
        print(f"Board: {board['name']}")
        print(f"Lists: {len(lists)}")
        print(f"Total Cards: {len(cards)}")

        if dry_run:
            print(f"\n🎯 Dry run complete. Would create {len(cards)} issues")
        else:
            print(f"Issues Created: {created_count}/{len(cards)}")

            # Count preserved features
            checklists_count = sum(1 for c in cards if c.get("checklists"))
            attachments_count = sum(1 for c in cards if c.get("attachments"))
            labels_count = sum(1 for c in cards if c.get("labels"))
            comments_count = len(comments_by_card)
            total_comments = sum(len(comments) for comments in comments_by_card.values())

            print("\nPreserved Features:")
            print(f"  Checklists: {checklists_count} cards")
            print(f"  Attachments: {attachments_count} cards")
            print(f"  Labels: {labels_count} cards")
            print(f"  Comments: {comments_count} cards ({total_comments} total comments)")

            print("\nStatus Distribution:")
            status_counts: dict[str, int] = {}
            for card in cards_sorted:
                list_name = self.list_map.get(card["idList"], "Unknown")
                status = self.list_to_status(list_name)
                status_counts[status] = status_counts.get(status, 0) + 1

            for status, count in sorted(status_counts.items()):
                print(f"  {status}: {count}")

            print("\n✅ Conversion complete!")
            print("\nView issues: bd list")
            print("Query by list: bd list --labels 'list:To Do'")
            print("Show issue: bd show <issue-id>")
        print("=" * 60)


def load_status_mapping(json_path: str) -> dict[str, list[str]]:
    """Load custom status mapping from JSON file

    Validates structure and merges with defaults for unspecified statuses.

    Args:
        json_path: Path to JSON file with status keyword mapping

    Returns:
        Merged status keywords dict (custom overrides + defaults)

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is invalid or contains bad data
    """
    if not Path(json_path).exists():
        raise FileNotFoundError(f"Status mapping file not found: {json_path}")

    try:
        with open(json_path) as f:
            custom_mapping = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in status mapping file: {e}") from e

    if not isinstance(custom_mapping, dict):
        raise ValueError("Status mapping must be a JSON object")

    # Valid beads statuses
    valid_statuses = {"open", "in_progress", "blocked", "deferred", "closed"}

    for status, keywords in custom_mapping.items():
        if status not in valid_statuses:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of: {', '.join(sorted(valid_statuses))}"
            )
        if not isinstance(keywords, list):
            raise ValueError(f"Keywords for '{status}' must be a list")
        if not all(isinstance(k, str) for k in keywords):
            raise ValueError(f"All keywords for '{status}' must be strings")

    # Merge custom with defaults (custom overrides defaults for specified keys)
    merged = TrelloToBeadsConverter.STATUS_KEYWORDS.copy()
    merged.update(custom_mapping)

    return merged


def main() -> None:
    # Show help
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)

    # Load credentials from environment (optionally from .env file)
    env_file = os.getenv("TRELLO_ENV_FILE", ".env")
    if Path(env_file).exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if key not in os.environ:  # Don't override existing env vars
                        os.environ[key] = value

    api_key = os.getenv("TRELLO_API_KEY")
    token = os.getenv("TRELLO_TOKEN")
    board_id = os.getenv("TRELLO_BOARD_ID")
    board_url = os.getenv("TRELLO_BOARD_URL")

    # Validate credentials (need either board_id OR board_url)
    if not api_key or not token:
        print("❌ Error: Missing required Trello credentials")
        print("\nRequired environment variables:")
        print("  TRELLO_API_KEY     - Your Trello API key")
        print("  TRELLO_TOKEN       - Your Trello API token")
        print("\nAnd one of:")
        print("  TRELLO_BOARD_ID    - The board ID (e.g., Bm0nnz1R)")
        print(
            "  TRELLO_BOARD_URL   - The full board URL (e.g., https://trello.com/b/Bm0nnz1R/my-board)"
        )
        print("\nSet them in your environment or create a .env file:")
        print('  export TRELLO_API_KEY="..."')
        print('  export TRELLO_TOKEN="..."')
        print('  export TRELLO_BOARD_ID="..." (or TRELLO_BOARD_URL="...")')
        print("\nFor setup instructions, see README.md")
        sys.exit(1)

    if not board_id and not board_url:
        print("❌ Error: Missing board identifier")
        print("\nYou must provide either:")
        print("  TRELLO_BOARD_ID    - The board ID (e.g., Bm0nnz1R)")
        print(
            "  TRELLO_BOARD_URL   - The full board URL (e.g., https://trello.com/b/Bm0nnz1R/my-board)"
        )
        print("\nFor setup instructions, see README.md")
        sys.exit(1)

    # Type narrowing for mypy
    assert api_key is not None
    assert token is not None

    # Check for flags
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv
    use_snapshot = "--use-snapshot" in sys.argv

    # Parse --status-mapping flag
    custom_status_keywords = None
    if "--status-mapping" in sys.argv:
        idx = sys.argv.index("--status-mapping")
        if idx + 1 >= len(sys.argv):
            print("❌ Error: --status-mapping requires a file path")
            print("Usage: --status-mapping path/to/mapping.json")
            sys.exit(1)

        status_mapping_path = sys.argv[idx + 1]
        try:
            custom_status_keywords = load_status_mapping(status_mapping_path)
            print(f"✅ Loaded custom status mapping from: {status_mapping_path}")
        except (FileNotFoundError, ValueError) as e:
            print(f"❌ Error loading status mapping: {e}")
            sys.exit(1)

    # Find beads database (current directory or override)
    beads_db_path = os.getenv("BEADS_DB_PATH") or str(Path.cwd() / ".beads/beads.db")

    if not Path(beads_db_path).exists():
        print(f"❌ Error: Beads database not found: {beads_db_path}")
        print("\nYou need to initialize a beads database first:")
        print("  bd init --prefix myproject")
        print("\nOr specify a custom path:")
        print("  export BEADS_DB_PATH=/path/to/.beads/beads.db")
        sys.exit(1)

    print(f"📂 Using beads database: {beads_db_path}")
    print()

    # Snapshot path for caching Trello API responses
    snapshot_path = os.getenv("SNAPSHOT_PATH") or str(Path.cwd() / "trello_snapshot.json")

    # Initialize components
    trello = TrelloReader(api_key, token, board_id=board_id, board_url=board_url)
    beads = BeadsWriter(db_path=beads_db_path)
    converter = TrelloToBeadsConverter(trello, beads, status_keywords=custom_status_keywords)

    # Run conversion
    try:
        converter.convert(
            dry_run=dry_run,
            snapshot_path=snapshot_path
            if use_snapshot
            else snapshot_path,  # Always save/use snapshot
        )
    except Exception as e:
        print(f"❌ Conversion failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
