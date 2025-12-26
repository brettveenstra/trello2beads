"""CLI entry point for trello2beads converter."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from trello2beads.beads_client import BeadsWriter
from trello2beads.converter import TrelloToBeadsConverter, load_status_mapping
from trello2beads.trello_client import TrelloReader

# Module docstring for --help
__doc__ = """
trello2beads - High-fidelity Trello board migration to beads issue tracking

Usage:
    export TRELLO_API_KEY="your-key"
    export TRELLO_TOKEN="your-token"
    export TRELLO_BOARD_ID="your-board-id"

    # Initialize beads database
    mkdir my-project && cd my-project
    bd init --prefix myproject

    # Run conversion
    python3 -m trello2beads

    # Or dry-run to preview
    python3 -m trello2beads --dry-run

    # Use custom status mapping
    python3 -m trello2beads --status-mapping custom_mapping.json

For full documentation, see README.md
"""


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
