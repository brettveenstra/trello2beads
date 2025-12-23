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

For full documentation, see README.md
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import requests


class TrelloReader:
    """Read data from Trello API"""

    def __init__(self, api_key: str, token: str, board_id: str):
        self.api_key = api_key
        self.token = token
        self.board_id = board_id
        self.base_url = "https://api.trello.com/1"

    def _request(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        """Make authenticated request to Trello API"""
        url = f"{self.base_url}/{endpoint}"
        auth_params = {"key": self.api_key, "token": self.token}
        if params:
            auth_params.update(params)

        response = requests.get(url, params=auth_params, timeout=30)
        response.raise_for_status()
        return cast(Any, response.json())

    def get_board(self) -> Dict:
        """Get board info"""
        return cast(Dict, self._request(f"boards/{self.board_id}", {"fields": "name,desc,url"}))

    def get_lists(self) -> List[Dict]:
        """Get all lists on the board"""
        return cast(
            List[Dict], self._request(f"boards/{self.board_id}/lists", {"fields": "name,id,pos"})
        )

    def get_cards(self) -> List[Dict]:
        """Get all cards with full details"""
        cards = self._request(
            f"boards/{self.board_id}/cards",
            {"attachments": "true", "checklists": "all", "fields": "all"},
        )
        return cast(List[Dict], cards)

    def get_card_comments(self, card_id: str) -> List[Dict]:
        """Get all comments for a card"""
        comments = self._request(f"cards/{card_id}/actions", {"filter": "commentCard"})
        return cast(List[Dict], comments)


class BeadsWriter:
    """Write issues to beads via bd CLI"""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize with optional custom database path"""
        self.db_path = db_path

    def create_issue(
        self,
        title: str,
        description: str = "",
        status: str = "open",
        priority: int = 2,
        issue_type: str = "task",
        labels: Optional[List[str]] = None,
        external_ref: Optional[str] = None,
    ) -> str:
        """Create a beads issue and return its ID"""
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

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"Failed to create issue: {result.stderr}")

        # Parse issue ID from output (format: "✓ Created issue: trello2beads-xyz")
        issue_id = None
        for line in result.stdout.split("\n"):
            if "Created issue:" in line:
                issue_id = line.split("Created issue:")[1].strip()
                break

        if not issue_id:
            raise RuntimeError(f"Could not parse issue ID from output: {result.stdout}")

        # Update status if not 'open' (bd create defaults to open)
        if status != "open":
            self.update_status(issue_id, status)

        return issue_id

    def update_status(self, issue_id: str, status: str) -> None:
        """Update issue status"""
        cmd = ["bd"]

        if self.db_path:
            cmd.extend(["--db", self.db_path])

        cmd.extend(["update", issue_id, "--status", status])

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"Failed to update status: {result.stderr}")


class TrelloToBeadsConverter:
    """Convert Trello board to beads issues"""

    # Smart status mapping (conservative - only obvious cases)
    STATUS_KEYWORDS = {
        "closed": ["done", "completed", "closed", "archived", "finished"],
        "in_progress": ["doing", "in progress", "wip", "active", "current", "working"],
    }

    @staticmethod
    def list_to_status(list_name: str) -> str:
        """Map list name to beads status (conservative)"""
        list_lower = list_name.lower()

        # Check for closed keywords
        if any(
            keyword in list_lower for keyword in TrelloToBeadsConverter.STATUS_KEYWORDS["closed"]
        ):
            return "closed"

        # Check for in_progress keywords
        if any(
            keyword in list_lower
            for keyword in TrelloToBeadsConverter.STATUS_KEYWORDS["in_progress"]
        ):
            return "in_progress"

        # Default to open (safe)
        return "open"

    def _resolve_card_references(
        self, cards: List[Dict], comments_by_card: Dict[str, List[Dict]]
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
                    att_match: Optional[re.Match[str]] = trello_url_pattern.search(att_url)

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

    def __init__(self, trello: TrelloReader, beads: BeadsWriter):
        self.trello = trello
        self.beads = beads
        self.list_map: Dict[str, str] = {}  # Trello list ID -> name
        self.trello_to_beads: Dict[str, str] = {}  # Trello card ID -> beads issue ID
        self.card_url_map: Dict[str, str] = {}  # Trello short URL -> beads issue ID

    def convert(self, dry_run: bool = False, snapshot_path: Optional[str] = None) -> None:
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
            status_counts: Dict[str, int] = {}
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

    if not all([api_key, token, board_id]):
        print("❌ Error: Missing required Trello credentials")
        print("\nRequired environment variables:")
        print("  TRELLO_API_KEY     - Your Trello API key")
        print("  TRELLO_TOKEN       - Your Trello API token")
        print("  TRELLO_BOARD_ID    - The board ID to convert")
        print("\nSet them in your environment or create a .env file:")
        print('  export TRELLO_API_KEY="..."')
        print('  export TRELLO_TOKEN="..."')
        print('  export TRELLO_BOARD_ID="..."')
        print("\nFor setup instructions, see README.md")
        sys.exit(1)

    # Type narrowing for mypy
    assert api_key is not None
    assert token is not None
    assert board_id is not None

    # Check for flags
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv
    use_snapshot = "--use-snapshot" in sys.argv

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
    trello = TrelloReader(api_key, token, board_id)
    beads = BeadsWriter(db_path=beads_db_path)
    converter = TrelloToBeadsConverter(trello, beads)

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
