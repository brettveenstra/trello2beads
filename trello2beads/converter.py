"""Trello to beads conversion orchestration with two-pass algorithm."""

from __future__ import annotations

import json
import logging
import re
import subprocess
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

    def _add_resolved_comments(self, card_id: str, beads_id: str) -> tuple[int, int]:
        """Add Trello comments to beads issue with URL resolution.

        Args:
            card_id: Trello card ID
            beads_id: Beads issue ID to add comments to

        Returns:
            Tuple of (comments_added, comments_failed)
        """
        comments = self.card_comments.get(card_id, [])
        if not comments:
            return 0, 0

        added_count = 0
        failed_count = 0

        # Regex pattern for Trello card URLs
        trello_url_pattern = re.compile(r"(?:https?://)?trello\.com/c/([a-zA-Z0-9]+)(?:/[^\s\)]*)?")

        # Add comments in chronological order (Trello API returns newest first, so reverse)
        for comment in reversed(comments):
            author = comment.get("memberCreator", {}).get("fullName", "Unknown")
            date = comment.get("date", "")[:10]  # YYYY-MM-DD
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

            # Format comment with timestamp
            comment_text = f"[{date}] {resolved_text}"

            try:
                self.beads.add_comment(beads_id, comment_text, author=author)
                added_count += 1
            except Exception as e:
                failed_count += 1
                logger.warning("Failed to add comment to %s: %s", beads_id, e)

        return added_count, failed_count

    def _resolve_card_references(
        self,
        cards: list[dict],
        comments_by_card: dict[str, list[dict]],
        broken_references: list[str],
    ) -> tuple[int, int, int, int, int]:
        """
        Second pass: Find Trello card URLs in descriptions/attachments
        and replace with beads issue references. Also add comments as beads comments.
        Creates "related" type dependencies for cross-references.

        Args:
            cards: List of Trello cards
            comments_by_card: Map of card IDs to comments
            broken_references: List to append broken reference URLs to

        Returns:
            tuple: (resolved_count, comments_added, comments_failed, dependencies_created, dependencies_failed)
        """
        import re

        resolved_count = 0
        total_comments_added = 0
        total_comments_failed = 0
        dependencies_created = 0
        dependencies_failed = 0

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

            # Add comments as actual beads comments (with URL resolution)
            comments_added, comments_failed = self._add_resolved_comments(card["id"], beads_id)
            if comments_added > 0:
                total_comments_added += comments_added
                logger.info(f"  ✓ Added {comments_added} comment(s) to {beads_id}")
            if comments_failed > 0:
                total_comments_failed += comments_failed

            # Also check comments for card references (for dependency tracking)
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
            total_comments_added,
            total_comments_failed,
            dependencies_created,
            dependencies_failed,
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

    def convert(self, dry_run: bool = False, snapshot_path: str | None = None) -> None:
        """Perform the conversion"""
        logger.info("🔄 Starting Trello → Beads conversion...")
        logger.info("")

        # Track validation warnings and statistics
        validation_warnings: list[str] = []
        failed_issues: list[dict] = []
        failed_comments: int = 0
        failed_dependencies: int = 0
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
        created_count = 0
        for card in cards_sorted:
            # Validate card has a title
            if not card.get("name") or not card["name"].strip():
                validation_warnings.append(f"Card {card['id']} has no title - skipping")
                logger.warning("Skipping card %s: no title", card["id"])
                continue

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
                try:
                    # Calculate priority based on position and recency
                    cards_in_list = cards_by_list.get(card["idList"], [])
                    priority = self.calculate_priority_from_position(card, cards_in_list)

                    # Create parent issue (epic if has checklists, task otherwise)
                    issue_id = self.beads.create_issue(
                        title=card["name"],
                        description=description,
                        status=status,
                        priority=priority,
                        issue_type=issue_type,
                        labels=labels,
                        external_ref=external_ref,
                    )

                    # Build mapping for second pass
                    self.trello_to_beads[card["id"]] = issue_id
                    self.card_url_map[card["shortUrl"]] = issue_id
                    self.card_url_map[card["shortLink"]] = issue_id

                    if has_checklists:
                        logger.info(
                            f"✅ Created {issue_id}: {card['name']} (epic, list:{list_name})"
                        )
                        epic_count += 1
                    else:
                        logger.info(f"✅ Created {issue_id}: {card['name']} (list:{list_name})")
                    created_count += 1

                    # Create child issues for checklist items
                    if has_checklists:
                        for checklist in card["checklists"]:
                            checklist_name = checklist.get("name", "Checklist")
                            for item in checklist.get("checkItems", []):
                                item_name = item["name"]
                                item_state = item.get("state", "incomplete")

                                # Determine child status based on completion
                                child_status = "closed" if item_state == "complete" else "open"

                                # Create child issue title with checklist context
                                child_title = f"{item_name}"
                                if len(card["checklists"]) > 1:
                                    # Multiple checklists - add checklist name for clarity
                                    child_title = f"[{checklist_name}] {item_name}"

                                # Child description references parent epic
                                child_desc = (
                                    f"Part of epic: {card['name']}\nChecklist: {checklist_name}"
                                )

                                try:
                                    child_id = self.beads.create_issue(
                                        title=child_title,
                                        description=child_desc,
                                        status=child_status,
                                        priority=priority,  # Inherit parent card's priority
                                        issue_type="task",
                                        labels=[f"epic:{issue_id}", f"list:{list_name}"],
                                        external_ref=f"{external_ref}:checklist-item",
                                    )

                                    # Add parent-child dependency
                                    self.beads.add_dependency(child_id, issue_id, "parent-child")

                                    status_icon = "✓" if item_state == "complete" else "☐"
                                    logger.info(
                                        f"  └─ {status_icon} Created {child_id}: {item_name}"
                                    )
                                    created_count += 1
                                    child_task_count += 1

                                except Exception as e:
                                    failed_issues.append(
                                        {
                                            "title": child_title,
                                            "type": "child_task",
                                            "error": str(e),
                                        }
                                    )
                                    logger.warning(
                                        "Failed to create child issue for checklist item '%s': %s",
                                        item_name,
                                        e,
                                    )

                except Exception as e:
                    failed_issues.append(
                        {
                            "title": card["name"],
                            "type": issue_type,
                            "error": str(e),
                        }
                    )
                    logger.error(f"❌ Failed to create '{card['name']}': {e}")

        # SECOND PASS: Resolve Trello card references and add comments (if not dry run)
        comments_added = 0
        related_dependencies_created = 0
        if not dry_run and self.trello_to_beads:
            logger.info("")
            logger.info("🔄 Pass 2: Resolving Trello card references and adding comments...")
            (
                resolved_count,
                comments_added,
                failed_comments_pass2,
                related_dependencies_created,
                failed_dependencies_pass2,
            ) = self._resolve_card_references(cards_sorted, comments_by_card, broken_references)

            # Update totals
            failed_comments += failed_comments_pass2
            failed_dependencies += failed_dependencies_pass2

            logger.info(f"✅ Resolved {resolved_count} Trello card references")
            logger.info(f"✅ Added {comments_added} comments to beads issues")
            if failed_comments > 0:
                logger.warning(f"⚠️  Failed to add {failed_comments} comments")
            logger.info(f"✅ Created {related_dependencies_created} related dependencies")
            if failed_dependencies > 0:
                logger.warning(f"⚠️  Failed to create {failed_dependencies} dependencies")

        # Summary report
        logger.info("")
        logger.info("=" * 60)
        logger.info("📊 CONVERSION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Board: {board['name']}")
        logger.info(f"Lists: {len(lists)}")
        logger.info(f"Total Cards: {len(cards)}")

        if dry_run:
            logger.info(f"\n🎯 Dry run complete. Would create {len(cards)} issues")
        else:
            logger.info(f"Issues Created: {created_count}/{len(cards)}")

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
                f"  Comments: {comments_added} added as beads comments (from {comments_count} cards)"
            )
            logger.info(
                f"  Dependencies: {related_dependencies_created} related dependencies created"
            )

            # Issue type breakdown
            logger.info("\nIssue Types:")
            logger.info(f"  Epics: {epic_count}")
            logger.info(f"  Child Tasks: {child_task_count}")
            logger.info(f"  Regular Tasks: {created_count - epic_count - child_task_count}")

            # Validation Report
            total_failures = len(failed_issues) + failed_comments + failed_dependencies
            has_issues = (
                total_failures > 0 or len(validation_warnings) > 0 or len(broken_references) > 0
            )

            if has_issues:
                logger.warning("\n⚠️  VALIDATION REPORT:")

                # Calculate success rate
                total_attempted = len(cards)
                total_succeeded = created_count
                success_rate = (
                    (total_succeeded / total_attempted * 100) if total_attempted > 0 else 0
                )
                logger.info(
                    f"  Success Rate: {success_rate:.1f}% ({total_succeeded}/{total_attempted} cards)"
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

                # Failed comments
                if failed_comments > 0:
                    logger.info(f"\n  Failed Comments: {failed_comments}")

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
