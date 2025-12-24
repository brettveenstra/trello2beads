"""
Unit tests for comprehensive error handling with custom exceptions
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directory to path to import trello2beads module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
import requests

from trello2beads import (
    TrelloAPIError,
    TrelloAuthenticationError,
    TrelloNotFoundError,
    TrelloRateLimitError,
    TrelloReader,
    TrelloServerError,
)


class TestCustomExceptions:
    """Test custom exception classes"""

    def test_trello_api_error_base_exception(self):
        """Should create base TrelloAPIError with metadata"""
        error = TrelloAPIError("Test error", status_code=400, response_text="Bad request")

        assert str(error) == "Test error"
        assert error.status_code == 400
        assert error.response_text == "Bad request"

    def test_trello_authentication_error(self):
        """Should create authentication error with helpful message"""
        error = TrelloAuthenticationError(
            "Invalid credentials", status_code=401, response_text="Unauthorized"
        )

        assert isinstance(error, TrelloAPIError)
        assert error.status_code == 401
        assert "Invalid credentials" in str(error)

    def test_trello_not_found_error(self):
        """Should create not found error"""
        error = TrelloNotFoundError("Board not found", status_code=404)

        assert isinstance(error, TrelloAPIError)
        assert error.status_code == 404

    def test_trello_rate_limit_error(self):
        """Should create rate limit error"""
        error = TrelloRateLimitError("Rate limit exceeded", status_code=429)

        assert isinstance(error, TrelloAPIError)
        assert error.status_code == 429

    def test_trello_server_error(self):
        """Should create server error"""
        error = TrelloServerError("Server error", status_code=500)

        assert isinstance(error, TrelloAPIError)
        assert error.status_code == 500


class TestAuthenticationErrorHandling:
    """Test 401/403 authentication error handling"""

    def test_401_raises_authentication_error_with_helpful_message(self):
        """Should raise TrelloAuthenticationError with credential guidance for 401"""
        reader = TrelloReader(api_key="bad_key", token="bad_token", board_id="TEST1234")

        response_401 = MagicMock()
        response_401.status_code = 401
        response_401.text = "Unauthorized"
        http_error = requests.HTTPError(response=response_401)
        response_401.raise_for_status.side_effect = http_error

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", return_value=response_401),
        ):
            with pytest.raises(TrelloAuthenticationError) as exc_info:
                reader._request("boards/TEST1234")

            error = exc_info.value
            assert error.status_code == 401
            assert "Invalid API credentials" in str(error)
            assert "TRELLO_API_KEY" in str(error)
            assert "TRELLO_TOKEN" in str(error)
            assert "https://trello.com/power-ups/admin" in str(error)

    def test_403_raises_authentication_error_with_permission_message(self):
        """Should raise TrelloAuthenticationError with permission guidance for 403"""
        reader = TrelloReader(api_key="key", token="token", board_id="TEST1234")

        response_403 = MagicMock()
        response_403.status_code = 403
        response_403.text = "Forbidden"
        http_error = requests.HTTPError(response=response_403)
        response_403.raise_for_status.side_effect = http_error

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", return_value=response_403),
        ):
            with pytest.raises(TrelloAuthenticationError) as exc_info:
                reader._request("boards/PRIVATE123/cards")

            error = exc_info.value
            assert error.status_code == 403
            assert "Access forbidden" in str(error)
            assert "permission" in str(error).lower()
            assert "boards/PRIVATE123/cards" in str(error)


class TestNotFoundErrorHandling:
    """Test 404 not found error handling"""

    def test_404_raises_not_found_error_with_board_guidance(self):
        """Should raise TrelloNotFoundError with board ID guidance"""
        reader = TrelloReader(api_key="key", token="token", board_id="INVALID99")

        response_404 = MagicMock()
        response_404.status_code = 404
        response_404.text = "Not Found"
        http_error = requests.HTTPError(response=response_404)
        response_404.raise_for_status.side_effect = http_error

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", return_value=response_404),
        ):
            with pytest.raises(TrelloNotFoundError) as exc_info:
                reader._request("boards/INVALID99")

            error = exc_info.value
            assert error.status_code == 404
            assert "Resource not found" in str(error)
            assert "board ID is correct" in str(error)
            assert "boards/INVALID99" in str(error)


class TestRateLimitErrorHandling:
    """Test 429 rate limit error handling after retries"""

    def test_429_exhausted_retries_raises_rate_limit_error(self):
        """Should raise TrelloRateLimitError after exhausting retries"""
        reader = TrelloReader(api_key="key", token="token", board_id="TEST1234")

        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.text = "Too Many Requests"
        http_error = requests.HTTPError(response=response_429)
        response_429.raise_for_status.side_effect = http_error

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", return_value=response_429),
            patch("time.sleep"),  # Speed up test
        ):
            with pytest.raises(TrelloRateLimitError) as exc_info:
                reader._request("boards/TEST1234/cards")

            error = exc_info.value
            assert error.status_code == 429
            assert "Rate limit exceeded" in str(error)
            assert "retry attempts" in str(error)
            assert "100 requests per 10 seconds" in str(error)
            assert "Wait a few minutes" in str(error)


class TestServerErrorHandling:
    """Test 500/502/503/504 server error handling after retries"""

    def test_500_exhausted_retries_raises_server_error(self):
        """Should raise TrelloServerError after exhausting retries for 500"""
        reader = TrelloReader(api_key="key", token="token", board_id="TEST1234")

        response_500 = MagicMock()
        response_500.status_code = 500
        response_500.text = "Internal Server Error"
        http_error = requests.HTTPError(response=response_500)
        response_500.raise_for_status.side_effect = http_error

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", return_value=response_500),
            patch("time.sleep"),
        ):
            with pytest.raises(TrelloServerError) as exc_info:
                reader._request("boards/TEST1234")

            error = exc_info.value
            assert error.status_code == 500
            assert "Trello server error" in str(error)
            assert "HTTP 500" in str(error)
            assert "retries" in str(error)
            assert "Try again later" in str(error)

    def test_503_exhausted_retries_raises_server_error(self):
        """Should raise TrelloServerError after exhausting retries for 503"""
        reader = TrelloReader(api_key="key", token="token", board_id="TEST1234")

        response_503 = MagicMock()
        response_503.status_code = 503
        response_503.text = "Service Unavailable"
        http_error = requests.HTTPError(response=response_503)
        response_503.raise_for_status.side_effect = http_error

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", return_value=response_503),
            patch("time.sleep"),
        ):
            with pytest.raises(TrelloServerError) as exc_info:
                reader._request("boards/TEST1234")

            error = exc_info.value
            assert error.status_code == 503
            assert "HTTP 503" in str(error)


class TestNetworkErrorHandling:
    """Test network error handling (timeouts, connection errors)"""

    def test_timeout_exhausted_retries_raises_api_error(self):
        """Should raise TrelloAPIError with network guidance after timeout retries"""
        reader = TrelloReader(api_key="key", token="token", board_id="TEST1234")

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", side_effect=requests.Timeout("Connection timeout")),
            patch("time.sleep"),
        ):
            with pytest.raises(TrelloAPIError) as exc_info:
                reader._request("boards/TEST1234")

            error = exc_info.value
            assert error.status_code is None
            assert "Network error" in str(error)
            assert "3 attempts" in str(error)
            assert "internet connection" in str(error).lower()

    def test_connection_error_exhausted_retries_raises_api_error(self):
        """Should raise TrelloAPIError for connection errors after retries"""
        reader = TrelloReader(api_key="key", token="token", board_id="TEST1234")

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", side_effect=requests.ConnectionError("Network unreachable")),
            patch("time.sleep"),
        ):
            with pytest.raises(TrelloAPIError) as exc_info:
                reader._request("boards/TEST1234")

            error = exc_info.value
            assert "Network error" in str(error)
            assert "Check your internet connection" in str(error)


class TestOtherHTTPErrorHandling:
    """Test handling of other HTTP errors (not 401/403/404/429/500/503)"""

    def test_400_bad_request_raises_api_error(self):
        """Should raise TrelloAPIError for 400 Bad Request"""
        reader = TrelloReader(api_key="key", token="token", board_id="TEST1234")

        response_400 = MagicMock()
        response_400.status_code = 400
        response_400.text = "Invalid request parameters"
        http_error = requests.HTTPError(response=response_400)
        response_400.raise_for_status.side_effect = http_error

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", return_value=response_400),
        ):
            with pytest.raises(TrelloAPIError) as exc_info:
                reader._request("boards/TEST1234")

            error = exc_info.value
            assert error.status_code == 400
            assert "HTTP 400" in str(error)
            assert "Invalid request parameters" in str(error)
