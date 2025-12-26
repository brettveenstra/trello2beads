"""Token bucket rate limiter for API requests."""

from __future__ import annotations

import threading
import time
from typing import Any


class RateLimiter:
    """Token bucket rate limiter for API requests

    Implements a token bucket algorithm to ensure API requests respect rate limits.
    Tokens are replenished at a constant rate and consumed for each request.
    """

    def __init__(self, requests_per_second: float, burst_allowance: int = 5):
        """
        Initialize rate limiter

        Args:
            requests_per_second: Sustained rate limit (tokens added per second)
            burst_allowance: Maximum tokens in bucket (allows short bursts)
        """
        self.rate = requests_per_second
        self.burst_allowance = burst_allowance
        self.tokens = float(burst_allowance)
        self.last_update = time.time()
        self._lock = threading.Lock()

    def acquire(self, timeout: float = 5.0) -> bool:
        """
        Acquire permission to make a request

        Blocks until a token is available or timeout is reached.

        Args:
            timeout: Maximum time to wait for permission (seconds)

        Returns:
            True if permission granted, False if timeout
        """
        deadline = time.time() + timeout

        while time.time() < deadline:
            with self._lock:
                now = time.time()
                # Add tokens based on time elapsed
                time_passed = now - self.last_update
                self.tokens = min(self.burst_allowance, self.tokens + time_passed * self.rate)
                self.last_update = now

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return True

            # Wait a short time before trying again
            time.sleep(0.01)

        return False  # Timeout

    def get_status(self) -> dict[str, Any]:
        """Get current rate limiter status for debugging"""
        with self._lock:
            return {
                "available_tokens": self.tokens,
                "max_tokens": self.burst_allowance,
                "rate_per_second": self.rate,
                "utilization_percent": (1 - self.tokens / self.burst_allowance) * 100,
            }
