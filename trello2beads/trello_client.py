"""Trello API client with rate limiting and retry logic."""

from __future__ import annotations

import re
import time
from typing import Any, cast

import requests

from trello2beads.exceptions import (
    TrelloAPIError,
    TrelloAuthenticationError,
    TrelloNotFoundError,
    TrelloRateLimitError,
    TrelloServerError,
)
from trello2beads.rate_limiter import RateLimiter


class TrelloReader:
    """Read data from Trello API with rate limiting

    Trello API rate limits (per token):
    - 100 requests per 10 seconds = 10 req/sec sustained
    - 300 requests per 10 seconds per API key = 30 req/sec

    We use 10 req/sec with burst allowance of 10 for conservative usage.
    """

    def __init__(
        self, api_key: str, token: str, board_id: str | None = None, board_url: str | None = None
    ):
        self.api_key = api_key
        self.token = token
        self.base_url = "https://api.trello.com/1"

        # Rate limiter: 10 requests/sec, burst up to 10
        # Conservative limit to respect Trello's 100 req/10sec token limit
        self.rate_limiter = RateLimiter(requests_per_second=10.0, burst_allowance=10)

        # Board ID can be provided directly or extracted from URL
        # Note: board_id is optional - only required for board-specific operations
        self.board_id: str | None
        if board_url:
            self.board_id = self.parse_board_url(board_url)
        elif board_id:
            self.board_id = board_id
        else:
            self.board_id = None  # Will be required for board-specific methods

    @staticmethod
    def parse_board_url(url: str) -> str:
        """Extract board ID from Trello URL

        Supports formats:
        - https://trello.com/b/Bm0nnz1R/board-name
        - https://trello.com/b/Bm0nnz1R
        - trello.com/b/Bm0nnz1R/board-name

        Args:
            url: Trello board URL

        Returns:
            Board ID (8-character alphanumeric string)

        Raises:
            ValueError: If URL format is invalid or board ID cannot be extracted
        """
        if not url:
            raise ValueError("URL cannot be empty")

        # Match Trello board URL patterns
        # Captures the board ID (e.g., Bm0nnz1R) from various URL formats
        patterns = [
            r"trello\.com/b/([a-zA-Z0-9]+)",  # Matches with or without https://
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        raise ValueError(f"Could not extract board ID from URL: {url}")

    def _request(self, endpoint: str, params: dict | None = None) -> Any:
        """Make authenticated request to Trello API with rate limiting and retry logic"""
        # Acquire rate limiter token before making request
        if not self.rate_limiter.acquire(timeout=30.0):
            raise RuntimeError("Rate limiter timeout - too many requests queued")

        url = f"{self.base_url}/{endpoint}"
        auth_params = {"key": self.api_key, "token": self.token}
        if params:
            auth_params.update(params)

        # Retry logic with exponential backoff for transient failures
        max_retries = 3
        base_delay = 1.0
        retry_statuses = {429, 500, 502, 503, 504}  # Transient errors

        last_exception: requests.RequestException | None = None
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=auth_params, timeout=30)
                response.raise_for_status()
                return cast(Any, response.json())

            except requests.HTTPError as e:
                last_exception = e
                status_code = e.response.status_code if e.response else 0
                response_text = e.response.text if e.response else ""

                # Handle non-retryable errors with helpful messages
                if status_code not in retry_statuses:
                    if status_code == 401:
                        raise TrelloAuthenticationError(
                            "Invalid API credentials. Check your TRELLO_API_KEY and TRELLO_TOKEN.\n"
                            "Get credentials at: https://trello.com/power-ups/admin",
                            status_code=status_code,
                            response_text=response_text,
                        ) from e
                    elif status_code == 403:
                        raise TrelloAuthenticationError(
                            f"Access forbidden to resource: {endpoint}\n"
                            "Your API token may not have permission to access this board.",
                            status_code=status_code,
                            response_text=response_text,
                        ) from e
                    elif status_code == 404:
                        raise TrelloNotFoundError(
                            f"Resource not found: {endpoint}\n"
                            "Check that your board ID is correct and the board exists.",
                            status_code=status_code,
                            response_text=response_text,
                        ) from e
                    else:
                        # Other non-retryable HTTP errors
                        raise TrelloAPIError(
                            f"HTTP {status_code} error for {endpoint}: {response_text[:200]}",
                            status_code=status_code,
                            response_text=response_text,
                        ) from e

                # Don't delay after last attempt
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)  # Exponential backoff: 1s, 2s, 4s
                    time.sleep(delay)

            except requests.RequestException as e:
                # Network errors, timeouts, etc.
                last_exception = e
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    time.sleep(delay)
                else:
                    # Network error after all retries
                    raise TrelloAPIError(
                        f"Network error after {max_retries} attempts: {str(e)}\n"
                        "Check your internet connection and try again.",
                        status_code=None,
                        response_text=None,
                    ) from e

        # All retries exhausted for transient HTTP errors
        if last_exception and isinstance(last_exception, requests.HTTPError):
            status_code = last_exception.response.status_code if last_exception.response else 0
            response_text = last_exception.response.text if last_exception.response else ""

            if status_code == 429:
                raise TrelloRateLimitError(
                    f"Rate limit exceeded after {max_retries} retry attempts.\n"
                    "Trello's API rate limit: 100 requests per 10 seconds.\n"
                    "Wait a few minutes and try again.",
                    status_code=status_code,
                    response_text=response_text,
                ) from last_exception
            elif status_code in {500, 502, 503, 504}:
                raise TrelloServerError(
                    f"Trello server error (HTTP {status_code}) persisted after {max_retries} retries.\n"
                    "Trello's servers may be experiencing issues. Try again later.",
                    status_code=status_code,
                    response_text=response_text,
                ) from last_exception

        # Fallback for unexpected cases
        if last_exception:
            raise TrelloAPIError(
                f"Request failed after {max_retries} retries: {str(last_exception)}",
                status_code=None,
                response_text=None,
            ) from last_exception

        raise RuntimeError("Request failed after retries")

    def _paginated_request(self, endpoint: str, params: dict | None = None) -> list[dict]:
        """Make paginated requests to handle Trello's 1000-item limit

        Trello API limits responses to 1000 items. This method automatically
        paginates using the 'before' parameter to fetch all results.

        Args:
            endpoint: API endpoint to request
            params: Query parameters (will add limit=1000 and before as needed)

        Returns:
            Complete list of all items across all pages
        """
        all_items: list[dict] = []
        request_params = params.copy() if params else {}
        request_params["limit"] = 1000  # Maximum allowed by Trello

        while True:
            # Fetch one page
            page_items = self._request(endpoint, request_params)

            if not isinstance(page_items, list):
                # Not a list response, return as-is
                return cast(list[dict], page_items)

            if not page_items:
                # Empty page means we're done
                break

            all_items.extend(page_items)

            # If we got less than 1000 items, we've reached the end
            if len(page_items) < 1000:
                break

            # Use the ID of the last item as the 'before' parameter for next page
            # Trello accepts IDs directly (converts to timestamp internally)
            last_item_id = page_items[-1].get("id")
            if not last_item_id:
                # No ID field, can't paginate further
                break

            request_params["before"] = last_item_id

        return all_items

    def validate_credentials(self) -> None:
        """Verify credentials work and board is accessible.

        Tests API credentials by attempting to fetch the authenticated user's boards.
        If board_id is set, also verifies that the board exists and is accessible.

        Raises:
            TrelloAuthenticationError: If API credentials are invalid
            TrelloNotFoundError: If board_id is set but board doesn't exist or isn't accessible
            TrelloAPIError: If other API errors occur

        Example:
            >>> reader = TrelloReader(api_key="...", token="...", board_id="Bm0nnz1R")
            >>> reader.validate_credentials()  # Raises exception if invalid
        """
        # Quick test: Fetch user's boards (validates credentials)
        try:
            self._request(
                "members/me/boards", params={"filter": "open", "fields": "id,name", "limit": "1"}
            )
        except TrelloAuthenticationError:
            # Re-raise with our existing good error message
            raise
        except TrelloAPIError:
            # Re-raise other API errors
            raise

        # If board_id is set, verify we can access it
        if self.board_id:
            try:
                self._request(f"boards/{self.board_id}", params={"fields": "id,name,url"})
                # Success - board is accessible
            except TrelloNotFoundError as e:
                raise TrelloNotFoundError(
                    f"Board '{self.board_id}' not found or you don't have access to it.\n"
                    f"Possible causes:\n"
                    f"  1. Board ID is incorrect\n"
                    f"  2. Board is private and your token doesn't have access\n"
                    f"  3. Board has been deleted or archived\n"
                    f"Check your board URL and privacy settings.",
                    status_code=404,
                    response_text=f"Board {self.board_id} not found",
                ) from e

    def get_board(self) -> dict:
        """Get board info"""
        if not self.board_id:
            raise ValueError(
                "board_id is required for this operation. "
                "Initialize TrelloReader with board_id or board_url parameter."
            )
        return cast(dict, self._request(f"boards/{self.board_id}", {"fields": "name,desc,url"}))

    def list_boards(self, filter_status: str = "open") -> list[dict]:
        """List all boards accessible to the authenticated user

        Useful for discovering board IDs and URLs when you're not sure which
        board to migrate.

        Args:
            filter_status: Filter boards by status. Options:
                - "open" (default): Only open (active) boards
                - "closed": Only closed (archived) boards
                - "all": Both open and closed boards

        Returns:
            List of board dictionaries with id, name, url, and closed status

        Example:
            >>> reader = TrelloReader(api_key="...", token="...")
            >>> boards = reader.list_boards()
            >>> for board in boards:
            ...     print(f"{board['name']}: {board['url']}")
        """
        valid_filters = {"open", "closed", "all"}
        if filter_status not in valid_filters:
            raise ValueError(
                f"Invalid filter_status: '{filter_status}'. Must be one of: {valid_filters}"
            )

        boards = self._request(
            "members/me/boards",
            {"fields": "name,url,closed,dateLastActivity", "filter": filter_status},
        )
        return cast(list[dict], boards)

    def get_lists(self) -> list[dict]:
        """Get all lists on the board"""
        if not self.board_id:
            raise ValueError(
                "board_id is required for this operation. "
                "Initialize TrelloReader with board_id or board_url parameter."
            )
        return cast(
            list[dict], self._request(f"boards/{self.board_id}/lists", {"fields": "name,id,pos"})
        )

    def get_cards(self) -> list[dict]:
        """Get all cards with full relationships (supports pagination for >1000 cards)

        Fetches cards with complete relationship data in a single request:
        - Attachments (files, links)
        - Checklists (with completion status)
        - Members (assigned users)
        - Custom field items (custom field values)
        - Stickers (visual decorations)
        """
        if not self.board_id:
            raise ValueError(
                "board_id is required for this operation. "
                "Initialize TrelloReader with board_id or board_url parameter."
            )
        cards = self._paginated_request(
            f"boards/{self.board_id}/cards",
            {
                "attachments": "true",
                "checklists": "all",
                "members": "true",
                "customFieldItems": "true",
                "stickers": "true",
                "fields": "all",
            },
        )
        return cards

    def get_card_comments(self, card_id: str) -> list[dict]:
        """Get all comments for a card (supports pagination for >1000 comments)"""
        comments = self._paginated_request(f"cards/{card_id}/actions", {"filter": "commentCard"})
        return comments
