"""Centralized logging configuration for trello2beads."""

from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """Configure logging for trello2beads.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR). Default: INFO.
        log_file: Optional path to log file. If provided, logs will be written to both
                  console and file.

    Example:
        >>> setup_logging("DEBUG")  # Verbose output to console
        >>> setup_logging("INFO", "conversion.log")  # Standard output + file logging
        >>> setup_logging("ERROR")  # Errors only
    """
    # Map level names to constants
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }

    # Get or create the trello2beads logger
    logger = logging.getLogger("trello2beads")
    logger.setLevel(level_map.get(level.upper(), logging.INFO))

    # Remove any existing handlers to avoid duplicates
    logger.handlers.clear()

    # Console handler (outputs to stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(console_handler)

    # File handler (optional, with timestamps)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False
