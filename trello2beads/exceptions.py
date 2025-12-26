"""Custom exception classes for trello2beads.

This module defines the exception hierarchy for both Trello API errors
and beads (bd CLI) integration errors.
"""

from __future__ import annotations


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
    """Base exception for all BeadsWriter errors.

    Provides structured error information including the command that failed,
    process output, and exit code for debugging.

    Attributes:
        command: The bd CLI command that was executed (if applicable)
        stdout: Standard output from the bd CLI process
        stderr: Standard error from the bd CLI process
        returncode: Exit code from the bd CLI process

    Example:
        >>> try:
        ...     writer.create_issue("")
        ... except BeadsWriterError as e:
        ...     print(f"Command: {e.command}")
        ...     print(f"Error: {e.stderr}")
    """

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
    """Raised when bd CLI is not found or not executable.

    This typically indicates that:
    - beads is not installed
    - beads is not in the system PATH
    - beads executable permissions are incorrect

    Resolution:
        Install beads from https://github.com/steveyegge/beads and ensure
        the 'bd' command is accessible in your PATH.
    """

    pass


class BeadsIssueCreationError(BeadsWriterError):
    """Raised when issue creation fails.

    This can occur when:
    - bd CLI returns non-zero exit code
    - Issue ID cannot be parsed from output
    - Parsed issue ID has invalid format
    - Subprocess times out or crashes
    - Database is not initialized

    Resolution:
        Check error message for specific cause. Common fixes:
        - Run 'bd init' to initialize database
        - Verify database permissions
        - Update beads to latest version
    """

    pass


class BeadsUpdateError(BeadsWriterError):
    """Raised when issue status update fails.

    This can occur when:
    - Issue ID does not exist
    - Status value is invalid
    - bd CLI returns non-zero exit code
    - Subprocess times out or crashes

    Resolution:
        - Verify issue ID exists (run 'bd show <issue-id>')
        - Check status is valid (open, in_progress, blocked, deferred, closed)
        - Verify database permissions
    """

    pass
