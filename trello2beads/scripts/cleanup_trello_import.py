#!/usr/bin/env python3
"""Cleanup script to remove imported Trello issues from beads database.

This script helps reset a beads database after a Trello import, allowing you to
re-run the import with fixes.

Usage:
    # List all imported issues
    python cleanup_trello_import.py --list

    # Delete all imported issues (with confirmation)
    python cleanup_trello_import.py --delete-all

    # Delete all except specified issues
    python cleanup_trello_import.py --keep beads-abc beads-def

    # Specify custom database path
    python cleanup_trello_import.py --db /path/to/.beads/beads.db --delete-all
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_bd_command(args: list[str], db_path: str | None = None) -> tuple[int, str, str]:
    """Run a bd command and return (returncode, stdout, stderr)"""
    cmd = ["bd"]
    if db_path:
        cmd.extend(["--db", db_path])
    cmd.extend(args)

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def get_all_issues_jsonl(db_path: str | None = None) -> list[dict]:
    """Get all issues from beads database via JSONL export"""
    # Try to read .beads/issues.jsonl directly
    jsonl_path = Path(".beads/issues.jsonl")
    if not jsonl_path.exists():
        print(f"Error: {jsonl_path} not found. Are you in a beads-enabled directory?")
        sys.exit(1)

    issues = []
    with open(jsonl_path) as f:
        for line in f:
            if line.strip():
                issues.append(json.loads(line))

    return issues


def find_trello_imports(issues: list[dict]) -> list[dict]:
    """Find all issues that were imported from Trello (have external_ref starting with 'trello:')"""
    trello_issues = []
    for issue in issues:
        external_ref = issue.get("external_ref")
        if external_ref and isinstance(external_ref, str) and external_ref.startswith("trello:"):
            trello_issues.append(issue)

    return trello_issues


def list_imported_issues(db_path: str | None = None):
    """List all imported Trello issues"""
    issues = get_all_issues_jsonl(db_path)
    trello_issues = find_trello_imports(issues)

    if not trello_issues:
        print("No Trello-imported issues found.")
        return

    print(f"\n📋 Found {len(trello_issues)} Trello-imported issues:\n")

    # Group by status
    by_status = {}
    for issue in trello_issues:
        status = issue.get("status", "unknown")
        if status not in by_status:
            by_status[status] = []
        by_status[status].append(issue)

    for status, issues_in_status in sorted(by_status.items()):
        print(f"\n{status.upper()} ({len(issues_in_status)}):")
        for issue in issues_in_status:
            issue_id = issue["id"]
            title = issue["title"]
            external_ref = issue.get("external_ref", "")
            print(f"  {issue_id} - {title} ({external_ref})")


def delete_issues(issue_ids: list[str], db_path: str | None = None) -> tuple[int, int]:
    """Delete specified issues. Returns (success_count, fail_count)"""
    success_count = 0
    fail_count = 0

    print(f"\n🗑️  Deleting {len(issue_ids)} issues...")

    for issue_id in issue_ids:
        # Use bd to delete the issue
        # Note: bd doesn't have a delete command, so we'll close them instead
        # User will need to manually remove from git if needed
        returncode, stdout, stderr = run_bd_command(["close", issue_id], db_path)

        if returncode == 0:
            success_count += 1
            print(f"  ✓ Closed {issue_id}")
        else:
            fail_count += 1
            print(f"  ✗ Failed to close {issue_id}: {stderr.strip()}")

    return success_count, fail_count


def main():
    parser = argparse.ArgumentParser(
        description="Cleanup imported Trello issues from beads database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--list", action="store_true", help="List all imported Trello issues")
    parser.add_argument(
        "--delete-all",
        action="store_true",
        help="Delete all imported Trello issues (prompts for confirmation)",
    )
    parser.add_argument(
        "--keep",
        nargs="+",
        metavar="ISSUE_ID",
        help="Keep specified issues, delete all other imports",
    )
    parser.add_argument("--db", help="Path to beads database (default: .beads/beads.db)")
    parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation prompts (dangerous!)"
    )

    args = parser.parse_args()

    # Validate arguments
    if not (args.list or args.delete_all or args.keep):
        parser.print_help()
        print("\nError: Must specify --list, --delete-all, or --keep")
        sys.exit(1)

    # List imported issues
    if args.list:
        list_imported_issues(args.db)
        return

    # Get all Trello imports
    issues = get_all_issues_jsonl(args.db)
    trello_issues = find_trello_imports(issues)

    if not trello_issues:
        print("No Trello-imported issues found.")
        return

    # Determine which issues to delete
    if args.delete_all:
        to_delete = [issue["id"] for issue in trello_issues]
        print(f"\n⚠️  WARNING: This will close {len(to_delete)} Trello-imported issues!")
    elif args.keep:
        keep_set = set(args.keep)
        to_delete = [issue["id"] for issue in trello_issues if issue["id"] not in keep_set]
        print(f"\n⚠️  WARNING: This will close {len(to_delete)} Trello-imported issues")
        print(f"    (keeping {len(keep_set)} specified issues)")

    # Confirmation prompt
    if not args.yes:
        print("\nThis operation will:")
        print("  1. Close all selected issues in the beads database")
        print("  2. You'll need to run 'bd sync' to commit changes")
        print("  3. You may need to manually clean up .beads/issues.jsonl in git")
        print("")
        response = input("Continue? [y/N]: ")
        if response.lower() not in ("y", "yes"):
            print("Aborted.")
            return

    # Delete issues
    success, failed = delete_issues(to_delete, args.db)

    print(f"\n✅ Summary:")
    print(f"   Closed: {success}")
    if failed:
        print(f"   Failed: {failed}")

    print(f"\n💡 Next steps:")
    print(f"   1. Run 'bd sync' to commit changes to git")
    print(f"   2. Re-run trello2beads with fixes")


if __name__ == "__main__":
    main()
