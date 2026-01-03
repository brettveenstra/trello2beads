"""beads (bd CLI) integration for issue creation and management."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import Path

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

    def __init__(
        self, db_path: str | None = None, dry_run: bool = False, prefix_override: str | None = None
    ):
        """Initialize with optional custom database path and dry-run mode

        Args:
            db_path: Path to beads database file (optional)
            dry_run: If True, print commands instead of executing them (default: False)
            prefix_override: Override prefix detection (useful for troubleshooting, optional)

        Raises:
            BeadsCommandError: If bd CLI is not available (skipped in dry-run mode)
        """
        self.db_path = db_path
        self.dry_run = dry_run
        self.prefix_override = prefix_override

        # Skip pre-flight check in dry-run mode
        if not dry_run:
            self._check_bd_available()

        mode = " (dry-run mode)" if dry_run else ""
        db_info = f" with db_path={db_path}" if db_path else ""
        prefix_info = f" with prefix_override={prefix_override}" if prefix_override else ""
        logger.info("BeadsWriter initialized%s%s%s", db_info, mode, prefix_info)

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

    def _get_subprocess_env(self) -> dict[str, str]:
        """Get environment dict for subprocess calls with proper BEADS_DIR.

        When --db flag is used, we need to ensure BEADS_DIR matches the database
        directory to avoid conflicts with parent repo databases.

        Returns:
            Environment dict with BEADS_DIR properly set or unset
        """
        env = os.environ.copy()

        if self.db_path:
            # Extract .beads directory from db_path
            # Example: /mnt/c/_scratch/test4/.beads/beads.db → /mnt/c/_scratch/test4/.beads
            db_file = Path(self.db_path)
            beads_dir = db_file.parent

            # Override BEADS_DIR to match the database we're targeting
            env["BEADS_DIR"] = str(beads_dir.resolve())
            logger.debug(f"Setting BEADS_DIR={env['BEADS_DIR']} for subprocess")

        return env

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
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, env=self._get_subprocess_env()
            )
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
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, env=self._get_subprocess_env()
            )
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
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, env=self._get_subprocess_env()
            )
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
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, env=self._get_subprocess_env()
            )
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
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, env=self._get_subprocess_env()
            )
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

    def generate_issue_id(self, prefix: str, index: int) -> str:
        """Generate a beads-compatible issue ID.

        Uses Base36 encoding (lowercase alphanumeric) with 4-char suffix
        to match beads' native ID format expectations.

        Args:
            prefix: Database prefix (e.g., "myproject", or "import" as placeholder)
            index: Sequential index for uniqueness

        Returns:
            Issue ID like "import-a3f8" (valid beads format)
            Use with --rename-on-import to change prefix to match database
        """
        import hashlib

        # Generate hash from index for uniqueness (prefix will be renamed anyway)
        content = f"trello-import-{index}"
        hash_digest = hashlib.sha256(content.encode()).digest()

        # Base36 encode (0-9a-z lowercase ONLY - beads requirement)
        base36_chars = "0123456789abcdefghijklmnopqrstuvwxyz"
        num = int.from_bytes(hash_digest[:4], "big")  # 4 bytes for 4-char suffix

        result = []
        for _ in range(4):  # Exactly 4 chars (beads' default min_hash_length)
            result.append(base36_chars[num % 36])
            num //= 36

        suffix = "".join(reversed(result))
        return f"{prefix}-{suffix}"

    def get_prefix(self) -> str:
        """Get the beads database prefix using multiple detection methods with fallbacks.

        Detection order:
        1. Use override if provided (CLI flag)
        2. Try reading from SQLite database directly (most reliable)
        3. Try reading from .beads/config.yaml (legacy/fallback)
        4. Try `bd config get prefix` (subprocess)
        5. Try detecting from existing issues (bd list)

        Returns:
            The prefix (e.g., "myproject")

        Raises:
            BeadsUpdateError: If prefix cannot be detected by any method
        """
        # Use override if provided
        if self.prefix_override:
            logger.debug(f"Using override prefix: {self.prefix_override}")
            return self.prefix_override

        if self.dry_run:
            logger.debug("[DRY RUN] Would get beads prefix")
            return "test-prefix"

        # Method 1: Try reading from SQLite database directly (MOST RELIABLE)
        # This is where `bd init --prefix` stores the prefix
        prefix = self._read_prefix_from_database()
        if prefix:
            logger.debug(f"Retrieved prefix from database: '{prefix}'")
            return prefix

        # Method 2: Try reading .beads/config.yaml
        prefix = self._read_prefix_from_config_file()
        if prefix:
            logger.debug(f"Retrieved prefix from config.yaml: '{prefix}'")
            return prefix

        # Method 3: Try bd config get prefix (subprocess)
        prefix = self._read_prefix_from_bd_config()
        if prefix:
            logger.debug(f"Retrieved prefix from bd config: '{prefix}'")
            return prefix

        # Method 4: Try detecting from existing issues
        prefix = self._detect_prefix_from_issues()
        if prefix:
            logger.debug(f"Detected prefix from existing issues: '{prefix}'")
            return prefix

        # All methods failed
        raise BeadsUpdateError(
            "Could not detect beads database prefix using any method.\n\n"
            "Tried:\n"
            "  1. Reading from SQLite database (no config table or prefix not set)\n"
            "  2. Reading .beads/config.yaml (not found or invalid)\n"
            "  3. Running 'bd config get prefix' (failed or empty)\n"
            "  4. Detecting from existing issues (no issues or failed)\n\n"
            "Fix this by:\n"
            "  1. Set prefix manually: bd config set prefix your-project\n"
            "  2. Or use --prefix flag: trello2beads --prefix your-project\n"
            "  3. Or reinitialize database: bd init --prefix your-project\n",
            command=["bd", "config", "get", "prefix"],
        )

    def _read_prefix_from_database(self) -> str | None:
        """Try to read prefix from SQLite database directly.

        This is the most reliable method since `bd init --prefix` stores
        the prefix in the database, not necessarily in config.yaml.

        Returns:
            Prefix if found, None otherwise
        """
        try:
            import sqlite3

            # Determine database path
            db_file = Path(self.db_path) if self.db_path else Path.cwd() / ".beads" / "beads.db"

            if not db_file.exists():
                logger.debug(f"Database file not found: {db_file}")
                return None

            # Connect and query for prefix
            # Beads typically stores config in a 'config' or 'metadata' table
            # Try common table/column names
            with sqlite3.connect(db_file) as conn:
                cursor = conn.cursor()

                # First, get list of tables for debugging
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                logger.debug(f"Database tables: {tables}")

                # Try different possible schema locations
                queries = [
                    # Standard config table with key-value pairs
                    "SELECT value FROM config WHERE key = 'prefix'",
                    "SELECT value FROM metadata WHERE key = 'prefix'",
                    "SELECT prefix FROM config LIMIT 1",
                    "SELECT prefix FROM metadata LIMIT 1",
                    # Settings table (another common pattern)
                    "SELECT value FROM settings WHERE key = 'prefix'",
                    "SELECT prefix FROM settings LIMIT 1",
                ]

                for query in queries:
                    try:
                        cursor.execute(query)
                        result = cursor.fetchone()
                        if result and result[0]:
                            prefix = str(result[0]).strip()
                            if prefix:
                                logger.debug(f"Found prefix in database via query: {query}")
                                return prefix
                    except sqlite3.OperationalError as e:
                        # Table/column doesn't exist, try next query
                        logger.debug(f"Query failed (expected): {query} - {e}")
                        continue

                # If we have a config/metadata/settings table but queries failed,
                # try to dump its schema for debugging
                for table_name in ["config", "metadata", "settings"]:
                    if table_name in tables:
                        try:
                            cursor.execute(f"PRAGMA table_info({table_name})")
                            columns = cursor.fetchall()
                            logger.debug(f"Table '{table_name}' schema: {columns}")

                            # Try selecting all rows to see what's there
                            cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
                            rows = cursor.fetchall()
                            logger.debug(f"Table '{table_name}' sample data: {rows}")
                        except Exception as e:
                            logger.debug(f"Failed to inspect table {table_name}: {e}")

            logger.debug("No prefix found in database using standard queries")
            return None

        except Exception as e:
            logger.debug(f"Failed to read prefix from database: {e}")
            return None

    def _read_prefix_from_config_file(self) -> str | None:
        """Try to read prefix from .beads/config.yaml file.

        Returns:
            Prefix if found, None otherwise
        """
        try:
            # Determine config path based on db_path
            if self.db_path:
                config_path = Path(self.db_path).parent / "config.yaml"
            else:
                config_path = Path.cwd() / ".beads" / "config.yaml"

            if not config_path.exists():
                logger.debug(f"Config file not found: {config_path}")
                return None

            # Try to parse YAML (simple approach - avoid dependency)
            # Config format is typically: prefix: "myproject"
            with open(config_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("prefix:"):
                        # Extract prefix value (handle quotes)
                        value = line.split(":", 1)[1].strip()
                        value = value.strip('"').strip("'").strip()
                        if value:
                            logger.debug(f"Found prefix in config.yaml: {value}")
                            return value

            logger.debug("Config file exists but no prefix found")
            return None

        except Exception as e:
            logger.debug(f"Failed to read config file: {e}")
            return None

    def _read_prefix_from_bd_config(self) -> str | None:
        """Try to read prefix using bd config get prefix command.

        Returns:
            Prefix if found, None otherwise
        """
        try:
            cmd = ["bd"]
            if self.db_path:
                cmd.extend(["--db", self.db_path])
            cmd.extend(["config", "get", "prefix"])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
                env=self._get_subprocess_env(),
            )

            if result.returncode == 0 and result.stdout.strip():
                prefix = result.stdout.strip()
                logger.debug(f"bd config returned: '{prefix}'")
                return prefix

            logger.debug(f"bd config failed or returned empty (exit {result.returncode})")
            return None

        except Exception as e:
            logger.debug(f"bd config command failed: {e}")
            return None

    def _detect_prefix_from_issues(self) -> str | None:
        """Try to detect prefix by listing existing issues.

        Returns:
            Prefix if detected, None otherwise
        """
        try:
            cmd = ["bd"]
            if self.db_path:
                cmd.extend(["--db", self.db_path])
            cmd.extend(["list", "--format=id"])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
                env=self._get_subprocess_env(),
            )

            if result.returncode == 0 and result.stdout.strip():
                # Parse first issue ID to extract prefix
                # Format: "prefix-suffix"
                first_line = result.stdout.strip().split("\n")[0].strip()
                if "-" in first_line:
                    prefix = first_line.rsplit("-", 1)[0]  # Everything before last hyphen
                    if prefix:
                        logger.debug(f"Detected prefix from issue ID '{first_line}': {prefix}")
                        return prefix

            logger.debug("No existing issues to detect prefix from")
            return None

        except Exception as e:
            logger.debug(f"Failed to detect prefix from issues: {e}")
            return None

    def import_from_jsonl(
        self, jsonl_path: str, generated_id_to_external_ref: dict[str, str]
    ) -> dict[str, str]:
        """Import issues from JSONL file (preserves comment timestamps).

        Args:
            jsonl_path: Path to JSONL file containing issues with embedded comments
            generated_id_to_external_ref: Mapping of generated IDs to external_ref
                (e.g., {"import-a3f8": "trello:abc123"})

        Returns:
            Mapping of external_ref -> renamed issue_id for imported issues
            (e.g., {"trello:abc123": "accel-a3f8"})

        Raises:
            ValueError: If jsonl_path is invalid
            BeadsUpdateError: If import fails

        Example:
            >>> id_map = writer.import_from_jsonl("issues.jsonl", {"import-a3f8": "trello:abc"})
            >>> # {'trello:abc': 'accel-a3f8'}  # Note: prefix renamed by beads
        """
        if not jsonl_path or not jsonl_path.strip():
            raise ValueError("JSONL path cannot be empty")

        jsonl_file = Path(jsonl_path)
        if not jsonl_file.exists():
            raise ValueError(f"JSONL file not found: {jsonl_path}")

        # In dry-run mode, use the provided mapping (no actual import)
        if self.dry_run:
            logger.info("[DRY RUN] Would import issues from JSONL: %s", jsonl_path)
            # Invert the mapping: generated_id -> external_ref becomes external_ref -> generated_id
            external_ref_to_id = {
                ext_ref: gen_id for gen_id, ext_ref in generated_id_to_external_ref.items()
            }
            logger.debug("[DRY RUN] Would import %d issues with mapping", len(external_ref_to_id))
            return external_ref_to_id

        cmd = ["bd"]

        if self.db_path:
            cmd.extend(["--db", self.db_path])

        # Use --rename-on-import to fix prefix mismatch
        # Our JSONL has valid suffixes but placeholder "import-" prefix
        # This renames: import-a3f8 → accel-a3f8 (or whatever DB prefix is)
        cmd.extend(["import", "-i", str(jsonl_file), "--rename-on-import"])

        logger.info("Importing issues from JSONL: %s", jsonl_path)
        logger.info("Using --rename-on-import to fix prefix (import-* → <db-prefix>-*)")
        logger.debug("Command: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=300,  # 5 min timeout for large imports
                env=self._get_subprocess_env(),
            )
        except subprocess.TimeoutExpired as e:
            raise BeadsUpdateError(
                "Import timed out after 300s",
                command=cmd,
            ) from e
        except FileNotFoundError as e:
            raise BeadsUpdateError(
                "bd command not found. Is beads installed?",
                command=cmd,
            ) from e

        if result.returncode != 0:
            error_msg = (
                f"Failed to import JSONL.\n"
                f"File: {jsonl_path}\n"
                f"Command: {' '.join(cmd)}\n"
                f"Exit code: {result.returncode}\n"
                f"Error output: {result.stderr.strip() if result.stderr else '(none)'}\n"
            )
            logger.error("JSONL import failed: %s", error_msg)
            raise BeadsUpdateError(
                error_msg,
                command=cmd,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )

        logger.info("✅ Import completed successfully")
        if result.stdout:
            logger.info("Import stdout: %s", result.stdout)
        if result.stderr:
            logger.info("Import stderr: %s", result.stderr)

        # Build mapping: match generated IDs to renamed IDs by suffix
        # Note: bd import already wrote to both database AND JSONL, no sync needed
        # We generated IDs like "import-a3f8", beads renamed to "accel-a3f8"
        # Suffix stays same, only prefix changes
        logger.info("Matching renamed IDs by suffix...")
        external_ref_to_id = self._build_external_ref_mapping(generated_id_to_external_ref)

        logger.info(f"✅ Mapped {len(external_ref_to_id)} external refs to renamed issue IDs")
        return external_ref_to_id

    def _build_external_ref_mapping(
        self, generated_id_to_external_ref: dict[str, str]
    ) -> dict[str, str]:
        """Build external_ref -> renamed_id mapping by matching suffixes.

        After --rename-on-import, IDs have been renamed from placeholder prefix
        to database prefix (import-a3f8 → accel-a3f8). We match by suffix since
        beads preserves the suffix during rename.

        Args:
            generated_id_to_external_ref: Mapping of generated IDs to external_ref

        Returns:
            Dict mapping external_ref to renamed issue_id
        """
        # Get all issues from database (with unlimited limit)
        # Use --allow-stale since JSONL may not be committed to git yet
        # (bd import writes to JSONL but doesn't commit)
        cmd = ["bd"]
        if self.db_path:
            cmd.extend(["--db", self.db_path])
        cmd.extend(["--allow-stale", "list", "--json", "--limit", "0"])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
                env=self._get_subprocess_env(),
            )
        except subprocess.TimeoutExpired as e:
            raise BeadsUpdateError(
                "Query for issue list timed out",
                command=cmd,
            ) from e
        except Exception as e:
            raise BeadsUpdateError(
                f"Failed to query issue list: {e}",
                command=cmd,
            ) from e

        if result.returncode != 0:
            logger.error("bd list failed - returncode: %d", result.returncode)
            logger.error("bd list stderr: %s", result.stderr)
            raise BeadsUpdateError(
                f"Failed to query issue list\nError: {result.stderr}",
                command=cmd,
                stderr=result.stderr,
                returncode=result.returncode,
            )

        # Parse JSON output
        logger.debug("bd list returned %d bytes of JSON", len(result.stdout))
        try:
            issues = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise BeadsUpdateError(
                f"Failed to parse issue list JSON: {e}",
                command=cmd,
                stdout=result.stdout,
            ) from e

        # Build suffix -> renamed_id mapping from all issues
        suffix_to_renamed_id = {}
        for issue in issues:
            issue_id = issue.get("id", "")
            if "-" in issue_id:
                suffix = issue_id.split("-", 1)[1]  # Get everything after first hyphen
                suffix_to_renamed_id[suffix] = issue_id

        # Match generated IDs to renamed IDs by suffix
        external_ref_to_id = {}
        for generated_id, external_ref in generated_id_to_external_ref.items():
            if "-" in generated_id:
                suffix = generated_id.split("-", 1)[1]
                renamed_id = suffix_to_renamed_id.get(suffix)
                if renamed_id:
                    external_ref_to_id[external_ref] = renamed_id
                    logger.debug(
                        f"Matched: {generated_id} → {renamed_id} (external_ref: {external_ref})"
                    )
                else:
                    logger.warning(f"No renamed ID found for suffix: {suffix} ({external_ref})")

        return external_ref_to_id
