"""High-fidelity Trello board migration to beads issue tracking."""

from __future__ import annotations

# Import beads client from extracted module
from trello2beads.beads_client import BeadsWriter

# Import CLI from extracted module
from trello2beads.cli import main

# Import converter from extracted module
from trello2beads.converter import TrelloToBeadsConverter, load_status_mapping

# Import exceptions from extracted module
from trello2beads.exceptions import (
    BeadsCommandError,
    BeadsIssueCreationError,
    BeadsUpdateError,
    BeadsWriterError,
    TrelloAPIError,
    TrelloAuthenticationError,
    TrelloNotFoundError,
    TrelloRateLimitError,
    TrelloServerError,
)

# Import logging configuration
from trello2beads.logging_config import setup_logging

# Import rate limiter from extracted module
from trello2beads.rate_limiter import RateLimiter

# Import Trello client from extracted module
from trello2beads.trello_client import TrelloReader

__version__ = "0.1.0"

__all__ = [
    # Core classes
    "TrelloToBeadsConverter",
    "TrelloReader",
    "BeadsWriter",
    "RateLimiter",
    "load_status_mapping",
    "setup_logging",
    # Exceptions
    "TrelloAPIError",
    "TrelloAuthenticationError",
    "TrelloNotFoundError",
    "TrelloRateLimitError",
    "TrelloServerError",
    "BeadsWriterError",
    "BeadsCommandError",
    "BeadsIssueCreationError",
    "BeadsUpdateError",
    # CLI
    "main",
]
