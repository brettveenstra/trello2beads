#!/usr/bin/env bash
# Convenience wrapper for trello2beads Python module
# Usage: ./trello2beads.sh [OPTIONS]

# Get the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Add the repo directory to PYTHONPATH so the module can be found
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH}"

# Run the trello2beads module with all arguments passed through
exec python3 -m trello2beads "$@"
