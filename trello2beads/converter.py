"""Trello to beads conversion orchestration with two-pass algorithm."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path

from trello2beads.beads_client import BeadsWriter
from trello2beads.trello_client import TrelloReader

# Configure logging
logger = logging.getLogger(__name__)


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

    def calculate_priority_from_position(self, card: dict, cards_in_list: list[dict]) -> int:
        """Calculate beads priority using hybrid position + recency approach.

        Algorithm:
        1. Base priority from position (top 1-2 cards = P1, bottom = P3, middle = P2)
        2. Recency boost: cards inactive >90 days bumped to P1 (surface forgotten work)

        Args:
            card: The card to calculate priority for
            cards_in_list: All cards in the same list (sorted by position)

        Returns:
            Priority (0-4): P1 for top cards or stale cards, P2 default, P3 for bottom
        """
        from datetime import datetime, timezone

        # Step 1: Calculate base priority from position
        if len(cards_in_list) <= 1:
            # Single card in list → default priority
            base_priority = 2
        else:
            # Sort cards by position to identify top/bottom
            sorted_cards = sorted(cards_in_list, key=lambda c: c.get("pos", 0))
            card_index = next((i for i, c in enumerate(sorted_cards) if c["id"] == card["id"]), -1)

            if card_index < 0:
                # Card not found (shouldn't happen) → default
                base_priority = 2
            elif card_index <= 1:
                # Top 1-2 cards → P1 (top of mind)
                base_priority = 1
            elif card_index == len(sorted_cards) - 1:
                # Bottom card → P3 (low priority)
                base_priority = 3
            else:
                # Middle cards → P2 (default)
                base_priority = 2

        # Step 2: Apply recency boost for forgotten cards
        date_last_activity = card.get("dateLastActivity")
        if date_last_activity:
            try:
                # Parse ISO 8601 timestamp
                last_activity = datetime.fromisoformat(date_last_activity.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                days_since_activity = (now - last_activity).days

                # Boost stale cards (90+ days old) to P1 unless already P1
                if days_since_activity >= 90 and base_priority > 1:
                    logger.debug(
                        f"Recency boost: '{card['name']}' inactive for {days_since_activity} days "
                        f"(P{base_priority} → P1)"
                    )
                    return 1  # Surface forgotten work

            except (ValueError, AttributeError):
                # Invalid date format → ignore recency boost
                pass

        return base_priority

    def _build_comments_with_timestamps(self, card_id: str) -> list[dict]:
        """Build comment objects with Trello timestamps preserved.

        Args:
            card_id: Trello card ID

        Returns:
            List of comment dicts with {author, text, created_at} for JSONL
        """
        comments = self.card_comments.get(card_id, [])
        if not comments:
            return []

        comment_objects = []

        # Regex pattern for Trello card URLs
        trello_url_pattern = re.compile(r"(?:https?://)?trello\.com/c/([a-zA-Z0-9]+)(?:/[^\s\)]*)?")

        # Build comments in chronological order (Trello API returns newest first, so reverse)
        for comment in reversed(comments):
            author = comment.get("memberCreator", {}).get("fullName", "Unknown")
            created_at = comment.get("date")  # ISO 8601 timestamp from Trello
            text = comment["data"]["text"]

            # Resolve Trello URLs in comment text
            resolved_text = text
            matches = trello_url_pattern.finditer(text)
            for match in matches:
                full_url = match.group(0)
                short_link = match.group(1)
                target_beads_id = self.card_url_map.get(short_link)

                if target_beads_id:
                    beads_ref = f"See {target_beads_id}"
                    resolved_text = resolved_text.replace(full_url, beads_ref)

            comment_objects.append(
                {
                    "author": author,
                    "text": resolved_text,
                    "created_at": created_at,  # Preserve original Trello timestamp
                }
            )

        return comment_objects

    def _resolve_card_references(
        self,
        cards: list[dict],
        comments_by_card: dict[str, list[dict]],
        broken_references: list[str],
    ) -> tuple[int, int, int]:
        """
        Second pass: Find Trello card URLs in descriptions/attachments
        and replace with beads issue references.
        Creates "related" type dependencies for cross-references.

        Note: Comments are now embedded in JSONL during import (with timestamps).

        Args:
            cards: List of Trello cards
            comments_by_card: Map of card IDs to comments
            broken_references: List to append broken reference URLs to

        Returns:
            tuple: (resolved_count, dependencies_created, dependencies_failed)
        """
        import re

        resolved_count = 0
        dependencies_created = 0
        dependencies_failed = 0
        circular_dependencies_skipped = 0  # Track cycles separately

        # Regex patterns for Trello card URLs
        # Matches: https://trello.com/c/abc123 or trello.com/c/abc123/card-name
        trello_url_pattern = re.compile(r"(?:https?://)?trello\.com/c/([a-zA-Z0-9]+)(?:/[^\s\)]*)?")

        for card in cards:
            beads_id = self.trello_to_beads.get(card["id"])
            if not beads_id:
                continue

            # Track referenced cards for creating dependencies
            referenced_beads_ids: set[str] = set()

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

                if target_beads_id and target_beads_id != beads_id:
                    # Replace Trello URL with beads reference
                    beads_ref = f"See {target_beads_id}"
                    updated_desc = updated_desc.replace(full_url, beads_ref)
                    replacements_made = True
                    referenced_beads_ids.add(target_beads_id)
                    logger.info(f"  ✓ Resolved {short_link} → {target_beads_id} in description")
                elif not target_beads_id:
                    # Track broken reference
                    broken_references.append(full_url)
                    logger.warning(
                        "Broken reference in %s: %s (card not in conversion)", beads_id, full_url
                    )

            # Comments already embedded in JSONL with timestamps preserved!
            # Check comments for card references (for dependency tracking)
            card_comments = comments_by_card.get(card["id"], [])
            for comment in card_comments:
                comment_text = comment.get("data", {}).get("text", "")
                comment_matches = trello_url_pattern.finditer(comment_text)
                for match in comment_matches:
                    full_url = match.group(0)
                    short_link = match.group(1)
                    target_beads_id = self.card_url_map.get(short_link)
                    if target_beads_id and target_beads_id != beads_id:
                        referenced_beads_ids.add(target_beads_id)
                    elif not target_beads_id:
                        broken_references.append(full_url)

            # Also check attachments for Trello card links
            attachment_refs = []
            if card.get("attachments"):
                for att in card["attachments"]:
                    att_url = att.get("url", "")
                    att_match: re.Match[str] | None = trello_url_pattern.search(att_url)

                    if att_match:
                        full_url = att_match.group(0)
                        short_link = att_match.group(1)
                        target_beads_id = self.card_url_map.get(short_link)

                        if target_beads_id and target_beads_id != beads_id:
                            attachment_refs.append(
                                {"name": att["name"], "beads_id": target_beads_id}
                            )
                            replacements_made = True
                            referenced_beads_ids.add(target_beads_id)
                            logger.info(f"  ✓ Attachment '{att['name']}' → {target_beads_id}")
                        elif not target_beads_id:
                            broken_references.append(full_url)

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

                full_description = "\n".join(desc_parts)

                # Update the beads issue description
                self._update_description(beads_id, full_description)
                resolved_count += 1

            # Create "related" type dependencies for all referenced cards
            if referenced_beads_ids:
                for target_id in referenced_beads_ids:
                    try:
                        self.beads.add_dependency(beads_id, target_id, "related")
                        dependencies_created += 1
                        logger.debug("Created related dependency: %s → %s", beads_id, target_id)
                    except Exception as e:
                        error_str = str(e).lower()

                        # Detect circular dependency errors
                        if "cycle" in error_str or "circular" in error_str:
                            circular_dependencies_skipped += 1
                            logger.debug(
                                "Skipped circular dependency: %s → %s (would create cycle)",
                                beads_id,
                                target_id,
                            )
                        else:
                            dependencies_failed += 1
                            logger.warning(
                                "Failed to create dependency %s → %s: %s",
                                beads_id,
                                target_id,
                                e,
                            )

                logger.info(
                    f"  ✓ Created {len(referenced_beads_ids)} related dependency/dependencies for {beads_id}"
                )

        return (
            resolved_count,
            dependencies_created,
            dependencies_failed + circular_dependencies_skipped,  # Total dep failures
        )

    def _update_description(self, issue_id: str, new_description: str) -> None:
        """Update beads issue description"""
        cmd = ["bd"]

        if self.beads.db_path:
            cmd.extend(["--db", self.beads.db_path])

        cmd.extend(["update", issue_id, "--description", new_description])

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.warning(
                f"    ⚠️  Warning: Failed to update description for {issue_id}: {result.stderr}"
            )

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
        self.card_comments: dict[str, list[dict]] = {}  # Trello card ID -> list of comment dicts

        # Use custom keywords or fall back to class defaults
        self.status_keywords = (
            status_keywords if status_keywords is not None else self.STATUS_KEYWORDS
        )

    def convert(
        self, dry_run: bool = False, snapshot_path: str | None = None, max_workers: int = 1
    ) -> None:
        """Perform the conversion

        Args:
            dry_run: Preview changes without creating issues
            snapshot_path: Path to Trello snapshot file (load if exists, save if not)
            max_workers: Number of parallel workers for issue creation (default: 1 for serial)
                        Use 5-10 for faster conversion on large boards (experimental)
        """
        logger.info("🔄 Starting Trello → Beads conversion...")
        logger.info("")

        # Track validation warnings and statistics
        validation_warnings: list[str] = []
        failed_issues: list[dict] = []
        failed_dependencies: int = 0
        pending_closures: list[str] = []  # Track issues that should be closed after import
        broken_references: list[str] = []
        epic_count = 0
        child_task_count = 0

        # PASS 0: Fetch from Trello and save snapshot (or load existing)
        if snapshot_path and Path(snapshot_path).exists():
            logger.info(f"📂 Loading existing snapshot: {snapshot_path}")
            with open(snapshot_path) as f:
                snapshot = json.load(f)
            board = snapshot["board"]
            lists = snapshot["lists"]
            cards = snapshot["cards"]
            comments_by_card = snapshot.get("comments", {})
            logger.info(f"✅ Loaded {len(cards)} cards from snapshot")
        else:
            logger.info("🌐 Fetching from Trello API...")
            board = self.trello.get_board()
            lists = self.trello.get_lists()
            cards = self.trello.get_cards()

            # Fetch comments for cards that have them
            logger.info("💬 Fetching comments...")
            comments_by_card = {}
            cards_with_comments = [c for c in cards if c.get("badges", {}).get("comments", 0) > 0]

            for i, card in enumerate(cards_with_comments, 1):
                card_id = card["id"]
                comments = self.trello.get_card_comments(card_id)
                if comments:
                    comments_by_card[card_id] = comments
                    logger.info(
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
                logger.info(f"💾 Saved snapshot: {snapshot_path}")

        logger.info(f"\n📋 Board: {board['name']}")
        logger.info(f"   URL: {board['url']}")
        logger.info(f"📝 Lists: {len(lists)}")
        logger.info(f"🎴 Cards: {len(cards)}")
        logger.info("")

        # Build list map
        for lst in lists:
            self.list_map[lst["id"]] = lst["name"]

        # Log list-to-status mapping
        logger.info("📋 List → Status Mapping:")
        for lst in lists:
            status = self.list_to_status(lst["name"])
            logger.info(f"   '{lst['name']}' → {status}")
        logger.info("")

        # Sort cards by position
        cards_sorted = sorted(cards, key=lambda c: (c["idList"], c.get("pos", 0)))

        # Group cards by list for position-based priority calculation
        cards_by_list: dict[str, list[dict]] = {}
        for card in cards_sorted:
            list_id = card["idList"]
            if list_id not in cards_by_list:
                cards_by_list[list_id] = []
            cards_by_list[list_id].append(card)

        # FIRST PASS: Create all issues and build mapping
        logger.info("🔄 Pass 1: Creating beads issues...")

        # Phase 1a: Collect all parent issue requests
        issue_requests = []
        card_metadata = []  # Store card info for post-processing

        for card in cards_sorted:
            # Validate card has a title
            if not card.get("name") or not card["name"].strip():
                validation_warnings.append(f"Card {card['id']} has no title - skipping")
                logger.warning("Skipping card %s: no title", card["id"])
                continue

            list_name = self.list_map.get(card["idList"], "Unknown")
            status = self.list_to_status(list_name)

            # External reference for debugging (Trello short link)
            external_ref = f"trello:{card['shortLink']}"

            # WORKAROUND: bd import --rename-on-import skips closed issues
            # Import as "open" and track for post-import closure
            if status == "closed":
                status = "open"  # Temporary status for import
                pending_closures.append(external_ref)  # Track for post-import closure
                logger.debug(f"Tracking {external_ref} for post-import closure")

            # Create labels: preserve list name for querying
            labels = [f"list:{list_name}"]

            # Add original Trello labels if present
            if card.get("labels"):
                for label in card["labels"]:
                    if label.get("name"):
                        labels.append(f"trello-label:{label['name']}")

            # Build description
            desc_parts = []

            if card.get("desc"):
                desc_parts.append(card["desc"])

            # Determine if card has checklists (will become epic with children)
            has_checklists = bool(card.get("checklists"))

            # Add attachments
            if card.get("attachments"):
                desc_parts.append("\n## Attachments\n")
                for att in card["attachments"]:
                    desc_parts.append(
                        f"- [{att['name']}]({att['url']}) ({att.get('bytes', 0)} bytes)"
                    )
                desc_parts.append("")

            # Store comments for second pass (will be added as real beads comments after URL resolution)
            card_comments = comments_by_card.get(card["id"], [])
            if card_comments:
                self.card_comments[card["id"]] = card_comments

            description = "\n".join(desc_parts)

            # Determine issue type based on checklists
            issue_type = "epic" if has_checklists else "task"

            # Calculate priority based on position and recency
            cards_in_list = cards_by_list.get(card["idList"], [])
            priority = self.calculate_priority_from_position(card, cards_in_list)

            if dry_run:
                logger.info("[DRY RUN] Would create:")
                logger.info(f"  Title: {card['name']}")
                logger.info(f"  Type: {issue_type}")
                logger.info(f"  Status: {status}")
                logger.info(f"  List: {list_name}")
                logger.info(f"  Labels: {', '.join(labels)}")
                if has_checklists:
                    total_items = sum(len(cl.get("checkItems", [])) for cl in card["checklists"])
                    logger.info(f"  Children: {total_items} checklist items")
                logger.info("")
            else:
                # Build comments with timestamps (will be embedded in JSONL)
                comments_for_issue = self._build_comments_with_timestamps(card["id"])

                # Collect issue for JSONL creation
                issue_requests.append(
                    {
                        "title": card["name"],
                        "description": description,
                        "status": status,
                        "priority": priority,
                        "issue_type": issue_type,
                        "labels": labels,
                        "external_ref": external_ref,
                        "comments": comments_for_issue if comments_for_issue else None,
                    }
                )
                card_metadata.append(
                    {
                        "card": card,
                        "has_checklists": has_checklists,
                        "list_name": list_name,
                        "priority": priority,
                    }
                )

        # Phase 1b: Create parent issues (JSONL import or batch create)
        parent_issues_created = 0  # Track parent issues (cards)
        child_issues_created = 0  # Track child issues (checklist items)
        child_issues_data = []  # Collect child issue data for batch creation
        child_parent_map = []  # Track (child_external_ref, parent_issue_id) for dependencies
        if not dry_run and issue_requests:
            # Use JSONL import in production (preserves comment timestamps)
            # Use batch_create in dry-run/test mode (for test compatibility)
            if self.beads.dry_run:
                # Test/dry-run mode: use batch_create (tests mock this method)
                logger.info(f"Creating {len(issue_requests)} parent issues (dry-run/test mode)...")
                # Remove comments from issue_requests for batch_create (it doesn't support them)
                batch_requests = []
                for issue in issue_requests:
                    issue_copy = issue.copy()
                    issue_copy.pop("comments", None)  # Remove comments field
                    batch_requests.append(issue_copy)

                issue_ids = self.beads.batch_create_issues(batch_requests, max_workers=max_workers)

                # Add comments separately in dry-run mode (for test compatibility)
                for issue_id, issue_request in zip(issue_ids, issue_requests, strict=True):
                    # Type narrowing for mypy
                    if not isinstance(issue_id, str):
                        continue

                    comments_data = issue_request.get("comments")
                    if not comments_data or not isinstance(comments_data, list):
                        continue

                    for comment in comments_data:
                        # Format comment text with timestamp prefix for beads
                        text = comment["text"]
                        created_at = comment.get("created_at")
                        if created_at:
                            # Format timestamp as [YYYY-MM-DD]
                            timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                            date_str = timestamp.strftime("%Y-%m-%d")
                            text = f"[{date_str}] {text}"

                        self.beads.add_comment(
                            issue_id,
                            text,
                            author=comment.get("author"),
                        )
            else:
                # Production mode: use JSONL import (preserves comment timestamps)
                logger.info(f"Creating {len(issue_requests)} parent issues via JSONL import...")

                # Generate valid beads IDs with placeholder prefix
                # --rename-on-import will fix prefix to match database
                import tempfile

                # Store mapping: generated_id -> external_ref (for query-back later)
                generated_id_to_external_ref: dict[str, str] = {}

                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".jsonl", delete=False
                ) as jsonl_file:
                    jsonl_path = jsonl_file.name
                    for i, issue in enumerate(issue_requests):
                        # Generate valid beads ID (Base36, 4-char suffix)
                        # Use "import" as placeholder prefix (--rename-on-import will fix it)
                        issue_id = self.beads.generate_issue_id("import", i)
                        issue["id"] = issue_id

                        # Store mapping for later (to match renamed IDs)
                        external_ref = issue.get("external_ref")
                        if external_ref:
                            generated_id_to_external_ref[issue_id] = external_ref

                        # Remove None comments field (beads doesn't like null)
                        if issue.get("comments") is None:
                            del issue["comments"]

                        # Write JSONL line
                        jsonl_file.write(json.dumps(issue) + "\n")

                # Import JSONL (preserves comment timestamps!)
                # beads will rename: import-a3f8 → accel-a3f8 (or whatever DB prefix is)
                try:
                    external_ref_to_id = self.beads.import_from_jsonl(
                        jsonl_path, generated_id_to_external_ref
                    )
                    logger.info(f"✅ Imported {len(external_ref_to_id)} parent issues")

                    # Build issue_ids list by looking up each request's external_ref
                    # This gets the RENAMED IDs after --rename-on-import
                    # (maintains same order as issue_requests for zip with card_metadata)
                    issue_ids = []
                    for issue in issue_requests:
                        external_ref = issue.get("external_ref")
                        issue_id = external_ref_to_id.get(external_ref) if external_ref else None
                        issue_ids.append(issue_id)

                finally:
                    # Clean up temp file
                    Path(jsonl_path).unlink(missing_ok=True)

            # Phase 1b: Update parent issues that should be closed
            # WORKAROUND: bd import skips closed issues, so we imported them as "open"
            # Now update them to "closed" after successful import
            # Note: Only handle parent cards here; children handled separately after child import
            parent_closures = [ref for ref in pending_closures if ":item-" not in ref]
            if parent_closures:
                logger.info(f"🔄 Updating {len(parent_closures)} parent issues to closed status...")
                closures_succeeded = 0
                closures_failed = 0

                for external_ref in parent_closures:
                    issue_id = external_ref_to_id.get(external_ref)
                    if not issue_id:
                        logger.warning(f"⚠️  Cannot close {external_ref}: issue not found in mapping")
                        closures_failed += 1
                        continue

                    try:
                        self.beads.update_status(issue_id, "closed")
                        closures_succeeded += 1
                        logger.debug(f"✅ Closed {issue_id} ({external_ref})")
                    except Exception as e:
                        logger.warning(f"⚠️  Failed to close {issue_id} ({external_ref}): {e}")
                        closures_failed += 1

                logger.info(
                    f"✅ Updated {closures_succeeded} parent issues to closed "
                    f"({closures_failed} failed)"
                )

            # Phase 1c: Post-process - build mappings and handle checklists
            for issue_id, meta in zip(issue_ids, card_metadata, strict=True):
                card = meta["card"]
                has_checklists = meta["has_checklists"]
                list_name = meta["list_name"]
                priority = meta["priority"]
                external_ref = f"trello:{card['shortLink']}"

                if issue_id is None:
                    # Track failure
                    failed_issues.append(
                        {
                            "title": card["name"],
                            "type": "epic" if has_checklists else "task",
                            "error": "Batch creation returned None",
                        }
                    )
                    logger.error(f"❌ Failed to create '{card['name']}'")
                    continue

                # Build mapping for second pass
                self.trello_to_beads[card["id"]] = issue_id
                self.card_url_map[card["shortUrl"]] = issue_id
                self.card_url_map[card["shortLink"]] = issue_id

                if has_checklists:
                    logger.info(f"✅ Created {issue_id}: {card['name']} (epic, list:{list_name})")
                    epic_count += 1
                else:
                    logger.info(f"✅ Created {issue_id}: {card['name']} (list:{list_name})")

                # Both epic and regular cards are parent cards
                parent_issues_created += 1

                # Collect child issue data for batch creation
                if has_checklists:
                    for checklist in card["checklists"]:
                        checklist_name = checklist.get("name", "Checklist")
                        for item_idx, item in enumerate(checklist.get("checkItems", [])):
                            # Get item ID (fallback to index for test data without IDs)
                            item_id = item.get("id", f"test-item-{item_idx}")
                            item_name = item["name"]
                            item_state = item.get("state", "incomplete")

                            # External reference for child (before status workaround)
                            child_external_ref = f"{external_ref}:item-{item_id}"

                            # Determine child status based on completion
                            # WORKAROUND: bd import skips closed issues (same as parent cards)
                            child_status = "closed" if item_state == "complete" else "open"
                            if child_status == "closed":
                                child_status = "open"  # Temporary - will update after import
                                pending_closures.append(child_external_ref)  # Track for closure

                            # Detect URL-only checklist items and generate proper title
                            is_url_only = item_name.strip().startswith(("http://", "https://"))
                            url_in_description = ""

                            if is_url_only:
                                # URL-only item: generate meaningful title from checklist name + position
                                # e.g., "Absorb Artifacts - 1" instead of "https://docs.google.com/..."
                                position = item_idx + 1  # 1-indexed for humans
                                child_title = f"{checklist_name} - {position}"
                                url_in_description = f"\n\nURL: {item_name.strip()}"
                            else:
                                # Normal item: use item name as title
                                child_title = f"{item_name}"
                                if len(card["checklists"]) > 1:
                                    # Multiple checklists - add checklist name for clarity
                                    child_title = f"[{checklist_name}] {item_name}"

                            # Child description references parent epic
                            child_desc = (
                                f"Part of epic: {card['name']}\nChecklist: {checklist_name}{url_in_description}"
                            )

                            # Collect child issue data for batch creation
                            child_issue = {
                                "title": child_title,
                                "description": child_desc,
                                "status": child_status,
                                "priority": priority,
                                "type": "task",
                                "labels": [f"epic:{issue_id}", f"list:{list_name}"],
                                "external_ref": child_external_ref,
                            }
                            child_issues_data.append(child_issue)
                            child_parent_map.append((child_external_ref, issue_id, child_title, item_state))

                            status_icon = "✓" if item_state == "complete" else "☐"
                            logger.info(f"  └─ {status_icon} Queued child: {child_title}")

            # Phase 1d: Batch create all child issues via JSONL import
            if child_issues_data and not dry_run:
                logger.info("")
                logger.info(f"📦 Creating {len(child_issues_data)} child issues via JSONL import...")

                # Create JSONL file with all children (using same pattern as parent import)
                import tempfile
                child_id_mapping = {}  # external_ref -> child_id

                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".jsonl", delete=False
                ) as child_jsonl_file:
                    child_jsonl_path = child_jsonl_file.name

                    # Store mapping for suffix matching
                    child_generated_id_to_external_ref = {}

                    for idx, child_issue in enumerate(child_issues_data):
                        # Generate valid beads ID (offset index to avoid collision with parents)
                        # Parents use indices 0-(n-1) for n total cards, children use indices n-(n+m-1)
                        # CRITICAL: Use len(issue_requests) NOT parent_issues_created to avoid collisions
                        # (Some parents may have failed import, but their indices are still consumed)
                        child_idx = len(issue_requests) + idx
                        child_id = self.beads.generate_issue_id("import", child_idx)
                        child_issue["id"] = child_id

                        # Store mapping
                        external_ref = child_issue.get("external_ref")
                        if external_ref:
                            child_generated_id_to_external_ref[child_id] = external_ref

                        # Write JSONL line
                        child_jsonl_file.write(json.dumps(child_issue) + "\n")

                try:
                    # Import children
                    child_external_ref_to_id = self.beads.import_from_jsonl(
                        child_jsonl_path, child_generated_id_to_external_ref
                    )
                    logger.info(f"✅ Imported {len(child_external_ref_to_id)} child issues")

                    # Create parent-child dependencies
                    logger.info("🔗 Creating parent-child dependencies...")
                    deps_created = 0
                    for child_external_ref, parent_id, child_title, item_state in child_parent_map:
                        child_id = child_external_ref_to_id.get(child_external_ref)
                        if child_id:
                            try:
                                self.beads.add_dependency(child_id, parent_id, "parent-child")
                                status_icon = "✓" if item_state == "complete" else "☐"
                                logger.info(f"  └─ {status_icon} Created {child_id}: {child_title}")
                                deps_created += 1
                                child_issues_created += 1
                                child_task_count += 1
                            except Exception as e:
                                logger.warning(f"Failed to add dependency {child_id} → {parent_id}: {e}")
                        else:
                            logger.warning(f"Child issue not found for {child_external_ref}")

                    logger.info(f"✅ Created {deps_created} parent-child dependencies")

                    # Update child issues that should be closed
                    # Count how many children are tracked for closure
                    child_closures = [ref for ref in pending_closures if ":item-" in ref]
                    if child_closures:
                        logger.info(f"🔄 Updating {len(child_closures)} child issues to closed status...")
                        child_closures_succeeded = 0
                        child_closures_failed = 0

                        for child_external_ref in child_closures:
                            child_id = child_external_ref_to_id.get(child_external_ref)
                            if not child_id:
                                logger.warning(f"⚠️  Cannot close {child_external_ref}: not found in mapping")
                                child_closures_failed += 1
                                continue

                            try:
                                self.beads.update_status(child_id, "closed")
                                child_closures_succeeded += 1
                                logger.debug(f"✅ Closed {child_id} ({child_external_ref})")
                            except Exception as e:
                                logger.warning(f"⚠️  Failed to close {child_id}: {e}")
                                child_closures_failed += 1

                        logger.info(
                            f"✅ Updated {child_closures_succeeded} child issues to closed "
                            f"({child_closures_failed} failed)"
                        )

                finally:
                    # Clean up temp file
                    Path(child_jsonl_path).unlink(missing_ok=True)

        # SECOND PASS: Resolve Trello card references (if not dry run)
        # Note: Comments already embedded in JSONL during import with timestamps!
        related_dependencies_created = 0
        if not dry_run and self.trello_to_beads:
            logger.info("")
            logger.info("🔄 Pass 2: Resolving Trello card references...")
            (
                resolved_count,
                related_dependencies_created,
                failed_dependencies_pass2,
            ) = self._resolve_card_references(cards_sorted, comments_by_card, broken_references)

            # Update totals
            failed_dependencies += failed_dependencies_pass2

            logger.info(f"✅ Resolved {resolved_count} Trello card references")
            logger.info(f"✅ Created {related_dependencies_created} related dependencies")
            if failed_dependencies > 0:
                logger.warning(
                    f"⚠️  Failed to create {failed_dependencies} dependencies "
                    "(includes circular dependencies - Trello allows cycles, beads doesn't)"
                )

        # Summary report
        logger.info("")
        logger.info("=" * 60)
        logger.info("📊 CONVERSION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Board: {board['name']}")
        logger.info(f"Lists: {len(lists)}")
        logger.info(f"Total Cards: {len(cards)}")

        total_issues_created = parent_issues_created + child_issues_created

        if dry_run:
            logger.info(f"\n🎯 Dry run complete. Would create {len(cards)} parent issues")
        else:
            logger.info(f"Parent Issues Created: {parent_issues_created}/{len(cards)} cards")
            if child_issues_created > 0:
                logger.info(f"Child Issues Created: {child_issues_created} (from checklists)")
            logger.info(f"Total Issues Created: {total_issues_created}")

            # Count preserved features
            checklists_count = sum(1 for c in cards if c.get("checklists"))
            attachments_count = sum(1 for c in cards if c.get("attachments"))
            labels_count = sum(1 for c in cards if c.get("labels"))
            comments_count = len(comments_by_card)

            logger.info("\nPreserved Features:")
            logger.info(f"  Checklists: {checklists_count} cards")
            logger.info(f"  Attachments: {attachments_count} cards")
            logger.info(f"  Labels: {labels_count} cards")
            logger.info(
                f"  Comments: {comments_count} cards with comments "
                "(embedded in issues with original Trello timestamps)"
            )
            logger.info(
                f"  Dependencies: {related_dependencies_created} related dependencies created"
            )

            # Issue type breakdown
            logger.info("\nIssue Types:")
            logger.info(f"  Epics: {epic_count} (cards with checklists)")
            logger.info(f"  Child Tasks: {child_task_count} (from checklist items)")
            logger.info(f"  Regular Tasks: {parent_issues_created - epic_count}")

            # Validation Report
            total_failures = len(failed_issues) + failed_dependencies
            has_issues = (
                total_failures > 0 or len(validation_warnings) > 0 or len(broken_references) > 0
            )

            if has_issues:
                logger.warning("\n⚠️  VALIDATION REPORT:")

                # Calculate success rate (for parent cards only)
                total_attempted = len(cards)
                total_succeeded = parent_issues_created
                success_rate = (
                    (total_succeeded / total_attempted * 100) if total_attempted > 0 else 0
                )
                logger.info(
                    f"  Card Success Rate: {success_rate:.1f}% ({total_succeeded}/{total_attempted})"
                )

                # Validation warnings
                if validation_warnings:
                    logger.info(f"\n  Validation Warnings ({len(validation_warnings)}):")
                    for warning in validation_warnings[:5]:  # Show first 5
                        logger.info(f"    - {warning}")
                    if len(validation_warnings) > 5:
                        logger.info(f"    ... and {len(validation_warnings) - 5} more")

                # Failed issues
                if failed_issues:
                    logger.info(f"\n  Failed Issue Creation ({len(failed_issues)}):")
                    for failure in failed_issues[:5]:  # Show first 5
                        logger.info(
                            f"    - [{failure['type']}] {failure['title']}: {failure['error']}"
                        )
                    if len(failed_issues) > 5:
                        logger.info(f"    ... and {len(failed_issues) - 5} more")

                # Failed dependencies
                if failed_dependencies > 0:
                    logger.info(f"\n  Failed Dependencies: {failed_dependencies}")

                # Broken references
                if broken_references:
                    unique_broken = list(set(broken_references))
                    logger.info(f"\n  Broken Trello References ({len(unique_broken)}):")
                    logger.info("    (URLs to cards not included in this conversion)")
                    for ref in unique_broken[:5]:  # Show first 5
                        logger.info(f"    - {ref}")
                    if len(unique_broken) > 5:
                        logger.info(f"    ... and {len(unique_broken) - 5} more")
            else:
                logger.info("\n✅ Validation: No issues detected")

            logger.info("\nStatus Distribution:")
            status_counts: dict[str, int] = {}
            for card in cards_sorted:
                list_name = self.list_map.get(card["idList"], "Unknown")
                status = self.list_to_status(list_name)
                status_counts[status] = status_counts.get(status, 0) + 1

            for status, count in sorted(status_counts.items()):
                logger.info(f"  {status}: {count}")

            logger.info("\n✅ Conversion complete!")
            logger.info("\nView issues: bd list")
            logger.info("Query by list: bd list --labels 'list:To Do'")
            logger.info("Show issue: bd show <issue-id>")
        logger.info("=" * 60)


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
