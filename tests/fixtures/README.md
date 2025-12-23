# Test Fixtures

This directory contains test fixtures for the trello2beads test suite.

## Fixture Files

### simple_board.json
Basic Trello board with minimal data for testing core functionality.
- 3 lists: "To Do", "Doing", "Done"
- 10 cards distributed across lists
- No comments, checklists, or attachments

### board_with_comments.json
Board with cards that have comments to test comment preservation.
- Cards with single and multiple comments
- Comments with various authors and dates
- Tests comment formatting and ordering

### board_with_references.json
Board with cards that reference each other via Trello URLs.
- Cards with Trello URLs in descriptions
- Tests URL resolution and replacement logic

### board_with_checklists.json
Board with cards containing checklists.
- Checklists with completed and incomplete items
- Tests checklist preservation and formatting

### empty_board.json
Edge case: Empty board with no cards.
- Tests handling of empty board scenario
- Validates no errors on zero cards

### malformed_board.json
Board with missing/invalid fields for error handling tests.
- Missing required fields
- Invalid data types
- Tests graceful error handling

## Creating Fixtures

To create new fixtures, use actual Trello API snapshot format:

```json
{
  "board": {
    "id": "board123",
    "name": "Test Board",
    "url": "https://trello.com/b/board123"
  },
  "lists": [
    {
      "id": "list1",
      "name": "To Do",
      "pos": 0
    }
  ],
  "cards": [
    {
      "id": "card1",
      "name": "Test Card",
      "desc": "Description",
      "idList": "list1",
      "pos": 0,
      "shortLink": "abc123",
      "shortUrl": "https://trello.com/c/abc123",
      "badges": {"comments": 0}
    }
  ],
  "comments": {}
}
```

## Usage in Tests

```python
def test_something(simple_board_fixture):
    board = simple_board_fixture
    assert board["board"]["name"] == "Test Board"
```
