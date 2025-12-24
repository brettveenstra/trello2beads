"""
Unit tests for RateLimiter
"""

import sys
import time
from pathlib import Path

# Add parent directory to path to import trello2beads module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from trello2beads import RateLimiter


class TestRateLimiter:
    """Test the RateLimiter token bucket implementation"""

    def test_initial_tokens(self):
        """Rate limiter should start with full burst allowance"""
        limiter = RateLimiter(requests_per_second=10.0, burst_allowance=5)
        status = limiter.get_status()

        assert status["available_tokens"] == 5.0
        assert status["max_tokens"] == 5
        assert status["rate_per_second"] == 10.0

    def test_acquire_single_token(self):
        """Should successfully acquire a single token"""
        limiter = RateLimiter(requests_per_second=10.0, burst_allowance=5)

        result = limiter.acquire(timeout=1.0)

        assert result is True
        status = limiter.get_status()
        assert status["available_tokens"] == 4.0  # 5 - 1

    def test_acquire_multiple_tokens_burst(self):
        """Should allow burst consumption up to burst_allowance"""
        limiter = RateLimiter(requests_per_second=10.0, burst_allowance=5)

        # Consume all 5 burst tokens
        for i in range(5):
            result = limiter.acquire(timeout=0.1)
            assert result is True, f"Failed to acquire token {i + 1}"

        status = limiter.get_status()
        assert status["available_tokens"] < 1.0  # All consumed

    def test_acquire_blocks_when_depleted(self):
        """Should block when no tokens available"""
        limiter = RateLimiter(requests_per_second=10.0, burst_allowance=2)

        # Consume all tokens
        limiter.acquire(timeout=0.1)
        limiter.acquire(timeout=0.1)

        # Next acquire should block for a short time
        start_time = time.time()
        limiter.acquire(timeout=0.2)
        elapsed = time.time() - start_time

        # Should have blocked for some time (token replenishment)
        assert elapsed > 0.05  # At least some delay

    def test_acquire_timeout(self):
        """Should timeout if no tokens available and rate is zero"""
        # Create limiter with 0 rate (no replenishment)
        limiter = RateLimiter(requests_per_second=0.0, burst_allowance=1)

        # Consume the one available token
        limiter.acquire(timeout=0.1)

        # Next acquire should timeout (no replenishment)
        start_time = time.time()
        result = limiter.acquire(timeout=0.1)
        elapsed = time.time() - start_time

        assert result is False  # Timeout
        assert 0.09 <= elapsed <= 0.15  # Should wait ~0.1s

    def test_token_replenishment(self):
        """Tokens should replenish over time at specified rate"""
        limiter = RateLimiter(requests_per_second=10.0, burst_allowance=5)

        # Consume all tokens
        for _ in range(5):
            limiter.acquire(timeout=0.1)

        # Wait for 0.5 seconds (should replenish ~5 tokens at 10 req/sec)
        time.sleep(0.5)

        # Try to acquire - should succeed immediately if tokens replenished
        result = limiter.acquire(timeout=0.1)
        assert result is True  # Should have replenished enough tokens

        status = limiter.get_status()
        # Should still have tokens available (replenished ~5, consumed 1)
        assert status["available_tokens"] >= 3.0

    def test_token_cap_at_burst_allowance(self):
        """Tokens should not exceed burst_allowance even after long wait"""
        limiter = RateLimiter(requests_per_second=100.0, burst_allowance=3)

        # Consume one token
        limiter.acquire(timeout=0.1)

        # Wait long enough to replenish many tokens
        time.sleep(0.1)  # Would allow 10 tokens, but capped at 3

        # Try to acquire burst_allowance tokens - should succeed
        for i in range(3):
            result = limiter.acquire(timeout=0.1)
            assert result is True, f"Token {i + 1} should be available"

        # Should now be depleted
        status = limiter.get_status()
        assert status["available_tokens"] < 1.0

    def test_thread_safety(self):
        """Rate limiter should be thread-safe"""
        import threading

        limiter = RateLimiter(requests_per_second=100.0, burst_allowance=20)
        successes = []

        def acquire_token():
            result = limiter.acquire(timeout=2.0)
            successes.append(result)

        # Spawn 20 threads to acquire tokens simultaneously
        threads = [threading.Thread(target=acquire_token) for _ in range(20)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # All should succeed (we have 20 burst tokens)
        assert len(successes) == 20
        assert all(successes)

    def test_realistic_trello_rate(self):
        """Test with realistic Trello API rate limits"""
        # Trello: 100 requests per 10 seconds = 10 req/sec
        limiter = RateLimiter(requests_per_second=10.0, burst_allowance=10)

        # Should be able to make 10 requests immediately (burst)
        for i in range(10):
            result = limiter.acquire(timeout=0.1)
            assert result is True, f"Failed burst request {i + 1}"

        # 11th request should block briefly (wait for replenishment)
        start_time = time.time()
        result = limiter.acquire(timeout=1.0)
        elapsed = time.time() - start_time

        assert result is True
        # Should have waited at least a little bit
        assert elapsed > 0.05

    def test_get_status(self):
        """get_status should return accurate statistics"""
        limiter = RateLimiter(requests_per_second=5.0, burst_allowance=10)

        status = limiter.get_status()

        assert "available_tokens" in status
        assert "max_tokens" in status
        assert "rate_per_second" in status
        assert "utilization_percent" in status

        assert status["max_tokens"] == 10
        assert status["rate_per_second"] == 5.0
        assert status["utilization_percent"] == 0.0  # No tokens consumed yet

        # Consume some tokens
        limiter.acquire()
        limiter.acquire()

        status = limiter.get_status()
        # Use approximate comparison due to floating point and timing
        assert 7.9 <= status["available_tokens"] <= 8.1
        assert 19.0 <= status["utilization_percent"] <= 21.0  # ~20%
