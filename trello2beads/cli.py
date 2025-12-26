"""CLI entry point for trello2beads converter."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from trello2beads.beads_client import BeadsWriter
from trello2beads.converter import TrelloToBeadsConverter, load_status_mapping
from trello2beads.logging_config import setup_logging
from trello2beads.trello_client import TrelloReader

logger = logging.getLogger("trello2beads.cli")

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

    # Parse logging flags
    log_level = "INFO"  # Default
    log_file = None

    if "--verbose" in sys.argv or "-v" in sys.argv:
        log_level = "DEBUG"
    elif "--quiet" in sys.argv or "-q" in sys.argv:
        log_level = "ERROR"
    elif "--log-level" in sys.argv:
        idx = sys.argv.index("--log-level")
        if idx + 1 < len(sys.argv):
            log_level = sys.argv[idx + 1].upper()

    if "--log-file" in sys.argv:
        idx = sys.argv.index("--log-file")
        if idx + 1 < len(sys.argv):
            log_file = sys.argv[idx + 1]

    # Setup logging
    setup_logging(log_level, log_file)

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
        logger.error("❌ Error: Missing required Trello credentials")
        logger.error("\nRequired environment variables:")
        logger.error("  TRELLO_API_KEY     - Your Trello API key")
        logger.error("  TRELLO_TOKEN       - Your Trello API token")
        logger.error("\nAnd one of:")
        logger.error("  TRELLO_BOARD_ID    - The board ID (e.g., Bm0nnz1R)")
        logger.error(
            "  TRELLO_BOARD_URL   - The full board URL (e.g., https://trello.com/b/Bm0nnz1R/my-board)"
        )
        logger.error("\nSet them in your environment or create a .env file:")
        logger.error('  export TRELLO_API_KEY="..."')
        logger.error('  export TRELLO_TOKEN="..."')
        logger.error('  export TRELLO_BOARD_ID="..." (or TRELLO_BOARD_URL="...")')
        logger.error("\nFor setup instructions, see README.md")
        sys.exit(1)

    if not board_id and not board_url:
        logger.error("❌ Error: Missing board identifier")
        logger.error("\nYou must provide either:")
        logger.error("  TRELLO_BOARD_ID    - The board ID (e.g., Bm0nnz1R)")
        logger.error(
            "  TRELLO_BOARD_URL   - The full board URL (e.g., https://trello.com/b/Bm0nnz1R/my-board)"
        )
        logger.error("\nFor setup instructions, see README.md")
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
            logger.error("❌ Error: --status-mapping requires a file path")
            logger.error("Usage: --status-mapping path/to/mapping.json")
            sys.exit(1)

        status_mapping_path = sys.argv[idx + 1]
        try:
            custom_status_keywords = load_status_mapping(status_mapping_path)
            logger.info(f"✅ Loaded custom status mapping from: {status_mapping_path}")
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"❌ Error loading status mapping: {e}")
            sys.exit(1)

    # Find beads database (current directory or override)
    beads_db_path = os.getenv("BEADS_DB_PATH") or str(Path.cwd() / ".beads/beads.db")

    if not Path(beads_db_path).exists():
        logger.error(f"❌ Error: Beads database not found: {beads_db_path}")
        logger.error("\nYou need to initialize a beads database first:")
        logger.error("  bd init --prefix myproject")
        logger.error("\nOr specify a custom path:")
        logger.error("  export BEADS_DB_PATH=/path/to/.beads/beads.db")
        sys.exit(1)

    logger.info(f"📂 Using beads database: {beads_db_path}")
    logger.info("")

    # Snapshot path for caching Trello API responses
    snapshot_path = os.getenv("SNAPSHOT_PATH") or str(Path.cwd() / "trello_snapshot.json")

    # Initialize Trello client
    trello = TrelloReader(api_key, token, board_id=board_id, board_url=board_url)

    # Pre-flight check: Validate credentials and board access
    logger.info("🔍 Validating Trello credentials and board access...")
    try:
        trello.validate_credentials()
        logger.info("✅ Credentials valid, board accessible")
        logger.info("")
    except Exception as e:
        logger.error(f"❌ Validation failed: {e}")
        sys.exit(1)

    # Initialize beads client and converter
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
        logger.error(f"❌ Conversion failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
