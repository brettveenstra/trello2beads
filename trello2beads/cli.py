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

    # Enable parallel execution for faster conversion (large boards)
    python3 -m trello2beads --max-workers 5

    # Disable SSL verification (if needed for network environment)
    python3 -m trello2beads --no-verify-ssl

    # Test connection and credentials
    python3 -m trello2beads --test-connection

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
    no_verify_ssl = "--no-verify-ssl" in sys.argv
    test_connection = "--test-connection" in sys.argv

    # Disable SSL warnings if --no-verify-ssl is used
    if no_verify_ssl:
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        logger.info("🔓 SSL verification disabled")

    # Parse --max-workers flag (default: 1 for serial execution)
    max_workers = 1  # Serial execution by default (safe, backward compatible)
    if "--max-workers" in sys.argv:
        idx = sys.argv.index("--max-workers")
        if idx + 1 >= len(sys.argv):
            logger.error("❌ Error: --max-workers requires a number")
            logger.error("Usage: --max-workers N (e.g., --max-workers 5)")
            sys.exit(1)

        try:
            max_workers = int(sys.argv[idx + 1])
            if max_workers < 1:
                logger.error("❌ Error: --max-workers must be at least 1")
                sys.exit(1)
            if max_workers > 1:
                logger.info(
                    f"⚡ Parallel mode enabled: {max_workers} workers "
                    "(experimental - may cause issues on some systems)"
                )
        except ValueError:
            logger.error(f"❌ Error: --max-workers must be a number, got: {sys.argv[idx + 1]}")
            sys.exit(1)

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
    trello = TrelloReader(
        api_key, token, board_id=board_id, board_url=board_url, verify_ssl=not no_verify_ssl
    )

    # Test connection mode - detailed diagnostics
    if test_connection:
        logger.info("🔍 Testing connection to Trello API...")
        logger.info(f"   API Key: {api_key[:8]}...{api_key[-4:]} (length: {len(api_key)})")
        logger.info(f"   Token: {token[:8]}...{token[-4:]} (length: {len(token)})")
        logger.info(f"   SSL Verification: {'Enabled' if not no_verify_ssl else 'Disabled'}")

        # Check for common issues
        warnings = []
        if api_key != api_key.strip():
            warnings.append("⚠️  API Key has leading/trailing whitespace")
        if token != token.strip():
            warnings.append("⚠️  Token has leading/trailing whitespace")
        if len(api_key) != 32:
            warnings.append(f"⚠️  API Key should be 32 characters, got {len(api_key)}")
        if len(token) != 64:
            warnings.append(f"⚠️  Token should be 64 characters, got {len(token)}")
        if '"' in api_key or "'" in api_key:
            warnings.append("⚠️  API Key contains quotes (remove them)")
        if '"' in token or "'" in token:
            warnings.append("⚠️  Token contains quotes (remove them)")

        if warnings:
            logger.warning("")
            for warning in warnings:
                logger.warning(f"   {warning}")
        logger.info("")

        # Test 1: Basic connectivity
        logger.info("📡 Test 1: Basic connectivity to api.trello.com...")
        try:
            import socket

            socket.create_connection(("api.trello.com", 443), timeout=5)
            logger.info("   ✅ Can reach api.trello.com:443")
        except Exception as e:
            logger.error(f"   ❌ Cannot reach api.trello.com: {e}")
            logger.error("   Check your network connection, proxy settings, or firewall")
            sys.exit(1)

        # Test 2: HTTPS request
        logger.info("📡 Test 2: HTTPS GET request...")
        try:
            import requests
            from urllib.parse import urlencode

            params = {"key": api_key.strip(), "token": token.strip(), "fields": "id,username"}
            test_url = "https://api.trello.com/1/members/me"

            # Show the URL format (without actual credentials)
            logger.info(f"   URL: {test_url}?key=<hidden>&token=<hidden>&fields=id,username")

            response = requests.get(
                test_url,
                params=params,
                timeout=10,
                verify=not no_verify_ssl,
            )
            logger.info(f"   Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                logger.info(f"   ✅ Authenticated as: {data.get('username', 'unknown')}")
            elif response.status_code == 401:
                logger.error(f"   ❌ HTTP 401: Authentication failed")
                logger.error(f"   Response: {response.text[:300]}")
                logger.error("")
                logger.error("   Troubleshooting steps:")
                logger.error("   1. Verify API Key at: https://trello.com/power-ups/admin")
                logger.error("   2. Generate a NEW token (tokens can expire or be revoked)")
                logger.error("   3. Check for extra quotes or whitespace in your credentials")
                logger.error("   4. Make sure you're using:")
                logger.error("      export TRELLO_API_KEY='your-key-here'  (no extra quotes inside)")
                logger.error("      export TRELLO_TOKEN='your-token-here'")
                sys.exit(1)
            else:
                logger.error(f"   ❌ HTTP {response.status_code}: {response.text[:200]}")
                sys.exit(1)
        except requests.exceptions.SSLError as e:
            logger.error(f"   ❌ SSL Error: {e}")
            logger.error("   Try using --no-verify-ssl flag")
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            logger.error(f"   ❌ Request failed: {e}")
            sys.exit(1)

        # Test 3: List boards
        logger.info("📡 Test 3: Fetching your boards...")
        try:
            boards = trello.list_boards(filter_status="open")
            logger.info(f"   ✅ Found {len(boards)} open boards")
            if boards:
                logger.info("   First 5 boards:")
                for board in boards[:5]:
                    logger.info(f"      - {board['name']} ({board['id']})")
        except Exception as e:
            logger.error(f"   ❌ Failed to list boards: {e}")
            sys.exit(1)

        # Test 4: Board access (if board_id provided)
        if board_id or board_url:
            logger.info(f"📡 Test 4: Checking board access (ID: {trello.board_id})...")
            try:
                board = trello.get_board()
                logger.info(f"   ✅ Board accessible: {board.get('name', 'unknown')}")
            except Exception as e:
                logger.error(f"   ❌ Cannot access board: {e}")
                sys.exit(1)

        logger.info("")
        logger.info("✅ All connection tests passed!")
        logger.info("   Your credentials and network setup are working correctly.")
        sys.exit(0)

    # Pre-flight check: Validate credentials and board access
    logger.info("🔍 Validating Trello credentials and board access...")
    try:
        trello.validate_credentials()
        logger.info("✅ Credentials valid, board accessible")
        logger.info("")
    except Exception as e:
        logger.error(f"❌ Validation failed: {e}")
        logger.error("\nFor detailed diagnostics, run: trello2beads --test-connection")
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
            max_workers=max_workers,
        )
    except Exception as e:
        logger.error(f"❌ Conversion failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
