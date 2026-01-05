#!/usr/bin/env python3
"""DANGEROUS: Directly delete imported Trello issues from beads SQLite database.

⚠️  WARNING: This script directly modifies the SQLite database!
   Always backup your .beads/ directory before running this.

This is needed because 'bd' may not have a delete command, only close.
For a full reset to re-import, we need to actually remove the rows.

Usage:
    # Backup first!
    cp -r .beads .beads.backup

    # List what will be deleted
    python reset_trello_import.py --dry-run

    # Delete all Trello imports
    python reset_trello_import.py --delete-all

    # Keep specific issues
    python reset_trello_import.py --keep trello2beads-abc trello2beads-def
"""

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def backup_beads_dir(beads_dir: Path) -> Path:
    """Create a timestamped backup of .beads directory"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = Path(f".beads.backup_{timestamp}")

    print(f"📦 Creating backup: {backup_path}")
    shutil.copytree(beads_dir, backup_path)
    print(f"✅ Backup created")

    return backup_path


def get_trello_issue_ids(db_path: Path) -> list[str]:
    """Get all issue IDs that have external_ref starting with 'trello:'"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Query issues with external_ref like 'trello:%'
    cursor.execute("""
        SELECT id FROM issues
        WHERE external_ref LIKE 'trello:%'
        ORDER BY id
    """)

    issue_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

    return issue_ids


def delete_issues_from_db(db_path: Path, issue_ids: list[str], dry_run: bool = False):
    """Delete issues from SQLite database"""
    if dry_run:
        print(f"\n🔍 DRY RUN: Would delete {len(issue_ids)} issues:")
        for issue_id in issue_ids:
            print(f"  - {issue_id}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    deleted_count = 0
    failed_count = 0

    print(f"\n🗑️  Deleting {len(issue_ids)} issues from database...")

    for issue_id in issue_ids:
        try:
            # Delete from issues table
            cursor.execute("DELETE FROM issues WHERE id = ?", (issue_id,))

            # Delete related data (comments, dependencies, etc.)
            cursor.execute("DELETE FROM comments WHERE issue_id = ?", (issue_id,))
            cursor.execute(
                "DELETE FROM dependencies WHERE issue_id = ? OR depends_on = ?",
                (issue_id, issue_id),
            )

            deleted_count += 1
            print(f"  ✓ Deleted {issue_id}")

        except sqlite3.Error as e:
            failed_count += 1
            print(f"  ✗ Failed to delete {issue_id}: {e}")

    # Commit changes
    if deleted_count > 0:
        conn.commit()
        print(f"\n✅ Deleted {deleted_count} issues from database")
        if failed_count > 0:
            print(f"⚠️  {failed_count} issues failed to delete")

    conn.close()


def regenerate_jsonl(db_path: Path, jsonl_path: Path):
    """Regenerate issues.jsonl from SQLite database"""
    print(f"\n📝 Regenerating {jsonl_path}...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all issues
    cursor.execute("""
        SELECT id, title, description, status, priority, issue_type,
               created_at, updated_at, external_ref, labels
        FROM issues
        ORDER BY id
    """)

    issues = []
    for row in cursor.fetchall():
        issue = {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "status": row[3],
            "priority": row[4],
            "issue_type": row[5],
            "created_at": row[6],
            "updated_at": row[7],
            "external_ref": row[8],
            "labels": json.loads(row[9]) if row[9] else [],
        }
        issues.append(issue)

    conn.close()

    # Write JSONL
    with open(jsonl_path, "w") as f:
        for issue in issues:
            f.write(json.dumps(issue) + "\n")

    print(f"✅ Wrote {len(issues)} issues to {jsonl_path}")


def main():
    parser = argparse.ArgumentParser(
        description="⚠️  DANGEROUS: Delete Trello imports from beads database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be deleted without deleting"
    )
    parser.add_argument(
        "--delete-all", action="store_true", help="Delete all Trello-imported issues"
    )
    parser.add_argument(
        "--keep", nargs="+", metavar="ISSUE_ID", help="Keep specified issues, delete others"
    )
    parser.add_argument("--no-backup", action="store_true", help="Skip automatic backup (risky!)")
    parser.add_argument(
        "--beads-dir", type=Path, default=Path(".beads"), help="Path to .beads directory"
    )

    args = parser.parse_args()

    # Validate
    if not (args.dry_run or args.delete_all or args.keep):
        parser.print_help()
        print("\nError: Must specify --dry-run, --delete-all, or --keep")
        sys.exit(1)

    beads_dir = args.beads_dir
    db_path = beads_dir / "beads.db"
    jsonl_path = beads_dir / "issues.jsonl"

    if not db_path.exists():
        print(f"Error: {db_path} not found")
        sys.exit(1)

    # Get all Trello imports
    trello_issue_ids = get_trello_issue_ids(db_path)

    if not trello_issue_ids:
        print("No Trello-imported issues found.")
        return

    print(f"📊 Found {len(trello_issue_ids)} Trello-imported issues")

    # Determine what to delete
    if args.delete_all:
        to_delete = trello_issue_ids
    elif args.keep:
        keep_set = set(args.keep)
        to_delete = [issue_id for issue_id in trello_issue_ids if issue_id not in keep_set]

    # Dry run mode
    if args.dry_run:
        delete_issues_from_db(db_path, to_delete, dry_run=True)
        return

    # Create backup
    if not args.no_backup:
        backup_path = backup_beads_dir(beads_dir)
        print(f"💾 Backup saved to: {backup_path}")
    else:
        print("⚠️  Skipping backup (--no-backup specified)")

    # Confirmation
    print(f"\n⚠️  WARNING: This will PERMANENTLY DELETE {len(to_delete)} issues from:")
    print(f"    {db_path}")
    print(f"\nThis operation:")
    print(f"  1. Deletes rows from SQLite database")
    print(f"  2. Regenerates .beads/issues.jsonl")
    print(f"  3. You'll need to 'git add' and 'bd sync' after")
    print(f"")
    response = input("Type 'DELETE' to confirm: ")

    if response != "DELETE":
        print("Aborted.")
        return

    # Delete from database
    delete_issues_from_db(db_path, to_delete)

    # Regenerate JSONL
    regenerate_jsonl(db_path, jsonl_path)

    print(f"\n✅ Reset complete!")
    print(f"\n💡 Next steps:")
    print(f"   1. git add .beads/issues.jsonl")
    print(f"   2. bd sync")
    print(f"   3. Re-run trello2beads with fixes")


if __name__ == "__main__":
    main()
