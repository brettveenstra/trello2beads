"""beads (bd CLI) integration for issue creation and management."""

from __future__ import annotations

import json
import logging
import re
import subprocess

from trello2beads.exceptions import (
    BeadsCommandError,
    BeadsIssueCreationError,
    BeadsUpdateError,
)

# Configure logging
logger = logging.getLogger(__name__)


class BeadsWriter:
    """Write issues to beads issue tracking system via bd CLI wrapper.

    BeadsWriter provides a Python interface to the beads command-line tool (bd),
    enabling programmatic creation and management of beads issues. It wraps the
    bd CLI with robust error handling, input validation, and parsing capabilities.

    Architecture:
        - Wraps bd CLI commands via subprocess calls
        - Validates all inputs before execution
        - Parses CLI output to extract issue IDs
        - Provides detailed error messages with diagnostics
        - Supports dry-run mode for testing without side effects

    Key Features:
        - Issue creation with full metadata (title, description, status, priority, type, labels)
        - Status updates for existing issues
        - Custom database path support for isolated environments
        - Dry-run mode for testing and validation
        - Comprehensive error handling with custom exception hierarchy
        - Automatic status updates after creation
        - Input validation with helpful error messages

    Error Handling:
        - BeadsCommandError: bd CLI not found or not executable
        - BeadsIssueCreationError: Issue creation failed (parse errors, subprocess failures)
        - BeadsUpdateError: Status update failed
        - ValueError: Invalid input parameters

    Example:
        >>> writer = BeadsWriter()
        >>> issue_id = writer.create_issue(
        ...     title="Fix authentication bug",
        ...     description="Users cannot log in with SSO",
        ...     priority=0,
        ...     issue_type="bug",
        ...     labels=["security", "auth"]
        ... )
        >>> print(f"Created: {issue_id}")
        Created: myproject-abc

    Example (dry-run mode):
        >>> writer = BeadsWriter(dry_run=True)
        >>> issue_id = writer.create_issue("Test issue")
        [DRY-RUN] Would execute: bd create --title Test issue ...
        >>> print(issue_id)
        dryrun-mock

    Thread Safety:
        Not thread-safe. Each thread should create its own BeadsWriter instance.

    See Also:
        - beads documentation: https://github.com/steveyegge/beads
        - bd CLI reference: Run `bd --help` for command documentation
    """

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
            logger.info(f"[DRY-RUN] Would execute: {' '.join(cmd)}")
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

    def batch_create_issues(
        self,
        issues: list[dict],
        max_workers: int = 1,
        show_progress: bool = True,
    ) -> list[str | None]:
        """Create multiple issues in parallel for better performance.

        Uses ThreadPoolExecutor to run multiple subprocess calls concurrently,
        reducing total conversion time for large boards (100+ cards).

        Args:
            issues: List of issue dicts with keys: title, description, status,
                    priority, issue_type, labels, external_ref (all optional except title)
            max_workers: Number of parallel subprocess workers (default: 1 for serial)
                        Use 5-10 for parallel execution on large boards (experimental)
            show_progress: Show progress indicator for large batches (default: True)

        Returns:
            List of issue IDs (same order as input). None for failed creations.

        Example:
            >>> issues = [
            ...     {"title": "Task 1", "status": "open", "priority": 2},
            ...     {"title": "Task 2", "status": "closed", "priority": 1},
            ... ]
            >>> ids = beads.batch_create_issues(issues)
            >>> # ['proj-abc', 'proj-def']

        Note:
            max_workers=1 uses serial execution (safe default).
            max_workers>1 uses parallel execution (faster but experimental).
            Individual issue failures don't break the entire batch.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if not issues:
            return []

        # Define results list at function level for type consistency
        results: list[str | None]

        # Serial execution for max_workers=1 (cleaner than ThreadPoolExecutor with 1 worker)
        if max_workers == 1:
            results = []
            for i, issue in enumerate(issues, 1):
                try:
                    issue_id = self.create_issue(
                        title=issue["title"],
                        description=issue.get("description", ""),
                        status=issue.get("status", "open"),
                        priority=issue.get("priority", 2),
                        issue_type=issue.get("issue_type", "task"),
                        labels=issue.get("labels"),
                        external_ref=issue.get("external_ref"),
                    )
                    results.append(issue_id)

                    if show_progress and len(issues) > 10 and i % 10 == 0:
                        logger.info(f"  Progress: {i}/{len(issues)} issues created")
                except Exception as e:
                    logger.warning(f"Failed to create issue '{issue.get('title')}': {e}")
                    results.append(None)

            if show_progress and len(issues) > 10:
                logger.info(f"  Progress: {len(issues)}/{len(issues)} issues created (complete)")

            return results

        # Pre-allocate results list to preserve order (parallel execution)
        results = [None] * len(issues)

        def create_with_index(index: int, issue: dict) -> tuple[int, str | None]:
            """Create issue and return (index, issue_id) tuple."""
            try:
                # Extract parameters with defaults
                issue_id = self.create_issue(
                    title=issue["title"],
                    description=issue.get("description", ""),
                    status=issue.get("status", "open"),
                    priority=issue.get("priority", 2),
                    issue_type=issue.get("issue_type", "task"),
                    labels=issue.get("labels"),
                    external_ref=issue.get("external_ref"),
                )
                return (index, issue_id)
            except Exception as e:
                logger.warning(f"Failed to create issue '{issue.get('title')}': {e}")
                return (index, None)

        try:
            # Parallel execution
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                futures = [
                    executor.submit(create_with_index, i, issue) for i, issue in enumerate(issues)
                ]

                # Collect results with optional progress indicator
                completed = 0
                for future in as_completed(futures):
                    idx: int
                    result_id: str | None
                    idx, result_id = future.result()
                    results[idx] = result_id
                    completed += 1

                    if show_progress and len(issues) > 10 and completed % 10 == 0:
                        logger.info(f"  Progress: {completed}/{len(issues)} issues created")

            # Final progress update
            if show_progress and len(issues) > 10:
                logger.info(f"  Progress: {completed}/{len(issues)} issues created (complete)")

        except Exception as e:
            # Fallback to serial creation if parallel execution fails
            logger.warning(f"Batch creation failed ({e}), falling back to serial...")
            results = []
            for issue in issues:
                try:
                    issue_id = self.create_issue(
                        title=issue["title"],
                        description=issue.get("description", ""),
                        status=issue.get("status", "open"),
                        priority=issue.get("priority", 2),
                        issue_type=issue.get("issue_type", "task"),
                        labels=issue.get("labels"),
                        external_ref=issue.get("external_ref"),
                    )
                    results.append(issue_id)
                except Exception:
                    results.append(None)

        return results

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
            logger.info(f"[DRY-RUN] Would execute: {' '.join(cmd)}")
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

    def add_dependency(
        self, issue_id: str, depends_on_id: str, dependency_type: str = "blocks"
    ) -> None:
        """Add a dependency between two issues.

        Args:
            issue_id: The issue that depends on another (the dependent)
            depends_on_id: The issue that must be completed first (the dependency)
            dependency_type: Type of dependency relationship (default: "blocks")
                - "blocks": depends_on_id must be resolved before issue_id (blocking dependency)
                - "parent-child": depends_on_id is parent of issue_id (epic/checklist relationship)
                - "related": Non-blocking informational link between issues
                - "discovered-from": Issue was discovered during work on another issue

        Raises:
            ValueError: If inputs are invalid
            BeadsUpdateError: If dependency creation fails

        Examples:
            >>> # Blocking dependency: Feature depends on API being ready
            >>> writer.add_dependency("feature-123", "api-456", "blocks")

            >>> # Parent-child: Checklist item belongs to epic
            >>> writer.add_dependency("checklist-item-789", "epic-123", "parent-child")

            >>> # Related: Cards reference each other (non-blocking)
            >>> writer.add_dependency("card-abc", "card-xyz", "related")
        """
        # Validate inputs
        if not issue_id or not issue_id.strip():
            raise ValueError("Issue ID cannot be empty")

        if not depends_on_id or not depends_on_id.strip():
            raise ValueError("Depends-on ID cannot be empty")

        valid_types = {"blocks", "related", "parent-child", "discovered-from"}
        if dependency_type not in valid_types:
            raise ValueError(
                f"Invalid dependency_type: '{dependency_type}'. "
                f"Must be one of: {sorted(valid_types)}"
            )

        cmd = ["bd"]

        if self.db_path:
            cmd.extend(["--db", self.db_path])

        cmd.extend(["dep", "add", issue_id, depends_on_id, "--type", dependency_type])

        logger.info("Adding %s dependency: %s → %s", dependency_type, issue_id, depends_on_id)
        logger.debug("Command: %s", " ".join(cmd))

        # Dry-run mode: print command instead of executing
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would execute: {' '.join(cmd)}")
            logger.info("[DRY-RUN] Would add dependency: %s → %s", issue_id, depends_on_id)
            return

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired as e:
            raise BeadsUpdateError(
                f"Dependency creation timed out after 30 seconds.\n"
                f"Issue: {issue_id}\n"
                f"Depends on: {depends_on_id}\n"
                f"Command: {' '.join(cmd)}",
                command=cmd,
            ) from e
        except Exception as e:
            raise BeadsUpdateError(
                f"Unexpected error adding dependency.\n"
                f"Issue: {issue_id}\n"
                f"Depends on: {depends_on_id}\n"
                f"Error: {e}",
                command=cmd,
            ) from e

        if result.returncode != 0:
            error_msg = (
                f"Failed to add dependency.\n"
                f"Issue: {issue_id}\n"
                f"Depends on: {depends_on_id}\n"
                f"Command: {' '.join(cmd)}\n"
                f"Exit code: {result.returncode}\n"
                f"Error output: {result.stderr.strip() if result.stderr else '(none)'}\n"
                f"\nSuggestion: Verify both issue IDs exist (run 'bd show <issue-id>')."
            )
            logger.error("Dependency creation failed: %s", error_msg)
            raise BeadsUpdateError(
                error_msg,
                command=cmd,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )

        logger.debug("Dependency added successfully")

    def add_comment(self, issue_id: str, text: str, author: str | None = None) -> None:
        """Add a comment to an issue.

        Args:
            issue_id: Issue ID to comment on
            text: Comment text
            author: Optional author name (default: current user from $USER)

        Raises:
            ValueError: If inputs are invalid
            BeadsUpdateError: If comment creation fails

        Example:
            >>> writer.add_comment("myproject-123", "Working on this now")
            >>> writer.add_comment("myproject-456", "Blocked by API issue", author="Alice")
        """
        # Validate inputs
        if not issue_id or not issue_id.strip():
            raise ValueError("Issue ID cannot be empty")

        if not text or not text.strip():
            raise ValueError("Comment text cannot be empty")

        if len(text) > 50000:
            raise ValueError(f"Comment too long ({len(text)} chars). Maximum 50000 characters.")

        cmd = ["bd"]

        if self.db_path:
            cmd.extend(["--db", self.db_path])

        cmd.extend(["comment", issue_id, text])

        if author:
            cmd.extend(["--author", author])

        logger.info("Adding comment to %s", issue_id)
        logger.debug("Command: %s", " ".join(cmd))

        # Dry-run mode: print command instead of executing
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would execute: {' '.join(cmd)}")
            logger.info("[DRY-RUN] Would add comment to %s", issue_id)
            return

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired as e:
            raise BeadsUpdateError(
                f"Comment creation timed out after 30 seconds.\n"
                f"Issue: {issue_id}\n"
                f"Command: {' '.join(cmd)}",
                command=cmd,
            ) from e
        except Exception as e:
            raise BeadsUpdateError(
                f"Unexpected error adding comment.\nIssue: {issue_id}\nError: {e}",
                command=cmd,
            ) from e

        if result.returncode != 0:
            error_msg = (
                f"Failed to add comment.\n"
                f"Issue: {issue_id}\n"
                f"Command: {' '.join(cmd)}\n"
                f"Exit code: {result.returncode}\n"
                f"Error output: {result.stderr.strip() if result.stderr else '(none)'}\n"
                f"\nSuggestion: Verify the issue ID exists (run 'bd show <issue-id>')."
            )
            logger.error("Comment creation failed: %s", error_msg)
            raise BeadsUpdateError(
                error_msg,
                command=cmd,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )

        logger.debug("Comment added successfully")

    def get_issue(self, issue_id: str) -> dict:
        """Get issue details in structured format.

        Args:
            issue_id: Issue ID to retrieve

        Returns:
            Dictionary containing issue data with keys like:
            - id, title, description, status, priority, type
            - labels, dependencies, comments, etc.

        Raises:
            ValueError: If issue_id is invalid
            BeadsUpdateError: If retrieval fails

        Example:
            >>> issue = writer.get_issue("myproject-123")
            >>> print(issue["title"])
            Fix authentication bug
            >>> print(issue["status"])
            in_progress
        """
        # Validate input
        if not issue_id or not issue_id.strip():
            raise ValueError("Issue ID cannot be empty")

        cmd = ["bd"]

        if self.db_path:
            cmd.extend(["--db", self.db_path])

        cmd.extend(["show", issue_id, "--json"])

        logger.info("Getting issue: %s", issue_id)
        logger.debug("Command: %s", " ".join(cmd))

        # Dry-run mode: return mock data
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would execute: {' '.join(cmd)}")
            logger.info("[DRY-RUN] Would get issue %s", issue_id)
            return {
                "id": "dryrun-mock",
                "title": "Mock Issue",
                "status": "open",
                "priority": 2,
                "type": "task",
            }

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired as e:
            raise BeadsUpdateError(
                f"Issue retrieval timed out after 30 seconds.\n"
                f"Issue: {issue_id}\n"
                f"Command: {' '.join(cmd)}",
                command=cmd,
            ) from e
        except Exception as e:
            raise BeadsUpdateError(
                f"Unexpected error retrieving issue.\nIssue: {issue_id}\nError: {e}",
                command=cmd,
            ) from e

        if result.returncode != 0:
            error_msg = (
                f"Failed to retrieve issue.\n"
                f"Issue: {issue_id}\n"
                f"Command: {' '.join(cmd)}\n"
                f"Exit code: {result.returncode}\n"
                f"Error output: {result.stderr.strip() if result.stderr else '(none)'}\n"
                f"\nSuggestion: Verify the issue ID exists (run 'bd list')."
            )
            logger.error("Issue retrieval failed: %s", error_msg)
            raise BeadsUpdateError(
                error_msg,
                command=cmd,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )

        # Parse JSON output
        try:
            issue_data: dict = json.loads(result.stdout)
            logger.debug("Retrieved issue: %s", issue_id)
            return issue_data
        except json.JSONDecodeError as e:
            error_msg = (
                f"Could not parse JSON output from bd show.\n"
                f"Issue: {issue_id}\n"
                f"Output: {result.stdout}\n"
                f"Parse error: {e}\n"
                f"\nSuggestion: This may indicate a bd CLI version incompatibility."
            )
            logger.error("JSON parsing failed: %s", error_msg)
            raise BeadsUpdateError(
                error_msg,
                command=cmd,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            ) from e
