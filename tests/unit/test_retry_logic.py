"""
Unit tests for retry logic with exponential backoff
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

# Add parent directory to path to import trello2beads module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from trello2beads import TrelloReader


class TestRetryLogic:
    """Test retry logic and exponential backoff in TrelloReader"""

    def test_successful_request_no_retry(self):
        """Should succeed on first attempt without retrying"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "test", "name": "Test Board"}
        mock_response.raise_for_status.return_value = None

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", return_value=mock_response) as mock_get,
        ):
            result = reader._request("boards/TEST1234")

            # Should make only one request
            assert mock_get.call_count == 1
            assert result == {"id": "test", "name": "Test Board"}

    def test_retry_on_429_rate_limit(self):
        """Should retry on 429 (rate limit) with exponential backoff"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        # First two attempts return 429, third succeeds
        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.raise_for_status.side_effect = requests.HTTPError(response=response_429)

        response_success = MagicMock()
        response_success.json.return_value = {"success": True}
        response_success.raise_for_status.return_value = None

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
            patch("time.sleep") as mock_sleep,  # Mock sleep to speed up test
        ):
            mock_get.side_effect = [
                response_429,  # Attempt 1: fail
                response_429,  # Attempt 2: fail
                response_success,  # Attempt 3: success
            ]

            result = reader._request("boards/TEST1234")

            # Should have retried 3 times
            assert mock_get.call_count == 3
            assert result == {"success": True}

            # Should have slept with exponential backoff (1s, 2s)
            assert mock_sleep.call_count == 2
            assert mock_sleep.call_args_list[0][0][0] == 1.0  # 1s delay
            assert mock_sleep.call_args_list[1][0][0] == 2.0  # 2s delay

    def test_retry_on_500_server_error(self):
        """Should retry on 500 (internal server error)"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_500 = MagicMock()
        response_500.status_code = 500
        response_500.raise_for_status.side_effect = requests.HTTPError(response=response_500)

        response_success = MagicMock()
        response_success.json.return_value = {"recovered": True}
        response_success.raise_for_status.return_value = None

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
            patch("time.sleep") as mock_sleep,
        ):
            mock_get.side_effect = [response_500, response_success]

            result = reader._request("boards/TEST1234")

            assert mock_get.call_count == 2
            assert result == {"recovered": True}
            assert mock_sleep.call_count == 1  # Slept once between attempts

    def test_retry_on_503_service_unavailable(self):
        """Should retry on 503 (service unavailable)"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_503 = MagicMock()
        response_503.status_code = 503
        response_503.raise_for_status.side_effect = requests.HTTPError(response=response_503)

        response_success = MagicMock()
        response_success.json.return_value = {"recovered": True}
        response_success.raise_for_status.return_value = None

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
            patch("time.sleep"),
        ):
            mock_get.side_effect = [response_503, response_success]

            result = reader._request("boards/TEST1234")

            assert mock_get.call_count == 2
            assert result == {"recovered": True}

    def test_no_retry_on_401_unauthorized(self):
        """Should NOT retry on 401 (unauthorized) - non-transient error"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_401 = MagicMock()
        response_401.status_code = 401
        response_401.raise_for_status.side_effect = requests.HTTPError(response=response_401)

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", return_value=response_401) as mock_get,
        ):
            with pytest.raises(requests.HTTPError):
                reader._request("boards/TEST1234")

            # Should NOT retry - only one attempt
            assert mock_get.call_count == 1

    def test_no_retry_on_404_not_found(self):
        """Should NOT retry on 404 (not found) - non-transient error"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_404 = MagicMock()
        response_404.status_code = 404
        response_404.raise_for_status.side_effect = requests.HTTPError(response=response_404)

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", return_value=response_404) as mock_get,
        ):
            with pytest.raises(requests.HTTPError):
                reader._request("boards/TEST1234")

            # Should NOT retry - only one attempt
            assert mock_get.call_count == 1

    def test_exhaust_all_retries(self):
        """Should raise exception after exhausting all retries"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_503 = MagicMock()
        response_503.status_code = 503
        response_503.raise_for_status.side_effect = requests.HTTPError(response=response_503)

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", return_value=response_503) as mock_get,
            patch("time.sleep") as mock_sleep,
        ):
            with pytest.raises(requests.HTTPError):
                reader._request("boards/TEST1234")

            # Should have tried 3 times (max retries)
            assert mock_get.call_count == 3

            # Should have slept between attempts (not after last)
            assert mock_sleep.call_count == 2

    def test_exponential_backoff_delays(self):
        """Should use exponential backoff: 1s, 2s, 4s"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.raise_for_status.side_effect = requests.HTTPError(response=response_429)

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get", return_value=response_429),
            patch("time.sleep") as mock_sleep,
        ):
            with pytest.raises(requests.HTTPError):
                reader._request("boards/TEST1234")

            # Check exponential backoff delays: 1s, 2s
            assert mock_sleep.call_count == 2
            assert mock_sleep.call_args_list[0][0][0] == 1.0  # 2^0 = 1s
            assert mock_sleep.call_args_list[1][0][0] == 2.0  # 2^1 = 2s

    def test_retry_on_network_timeout(self):
        """Should retry on network timeout (RequestException)"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_success = MagicMock()
        response_success.json.return_value = {"recovered": True}
        response_success.raise_for_status.return_value = None

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
            patch("time.sleep") as mock_sleep,
        ):
            mock_get.side_effect = [
                requests.Timeout("Connection timeout"),
                response_success,
            ]

            result = reader._request("boards/TEST1234")

            assert mock_get.call_count == 2
            assert result == {"recovered": True}
            assert mock_sleep.call_count == 1

    def test_retry_on_connection_error(self):
        """Should retry on connection error"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_success = MagicMock()
        response_success.json.return_value = {"recovered": True}
        response_success.raise_for_status.return_value = None

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
            patch("time.sleep"),
        ):
            mock_get.side_effect = [
                requests.ConnectionError("Network unreachable"),
                response_success,
            ]

            result = reader._request("boards/TEST1234")

            assert mock_get.call_count == 2
            assert result == {"recovered": True}

    def test_retry_exhaustion_on_network_error(self):
        """Should raise after exhausting retries on persistent network errors"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
            patch("time.sleep"),
        ):
            mock_get.side_effect = requests.Timeout("Persistent timeout")

            with pytest.raises(requests.Timeout):
                reader._request("boards/TEST1234")

            # Should have tried 3 times
            assert mock_get.call_count == 3

    def test_retry_preserves_request_params(self):
        """Should preserve all request parameters across retries"""
        reader = TrelloReader(api_key="test_key", token="test_token", board_id="TEST1234")

        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.raise_for_status.side_effect = requests.HTTPError(response=response_429)

        response_success = MagicMock()
        response_success.json.return_value = {"success": True}
        response_success.raise_for_status.return_value = None

        with (
            patch.object(reader.rate_limiter, "acquire", return_value=True),
            patch("requests.get") as mock_get,
            patch("time.sleep"),
        ):
            mock_get.side_effect = [response_429, response_success]

            reader._request("boards/TEST1234/cards", {"fields": "all", "limit": 1000})

            # Check that all calls had the same parameters
            assert mock_get.call_count == 2
            for call in mock_get.call_args_list:
                params = call[1]["params"]
                assert params["fields"] == "all"
                assert params["limit"] == 1000
                assert params["key"] == "test_key"
                assert params["token"] == "test_token"
