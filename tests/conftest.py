"""
Shared pytest fixtures for trello2beads tests
"""
import pytest
import json
from pathlib import Path


@pytest.fixture
def fixtures_dir():
    """Return path to test fixtures directory"""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def simple_board_fixture(fixtures_dir):
    """Load simple board test fixture"""
    fixture_file = fixtures_dir / "simple_board.json"
    if fixture_file.exists():
        with open(fixture_file) as f:
            return json.load(f)
    return None


@pytest.fixture
def board_with_comments_fixture(fixtures_dir):
    """Load board with comments test fixture"""
    fixture_file = fixtures_dir / "board_with_comments.json"
    if fixture_file.exists():
        with open(fixture_file) as f:
            return json.load(f)
    return None


@pytest.fixture
def board_with_references_fixture(fixtures_dir):
    """Load board with card references test fixture"""
    fixture_file = fixtures_dir / "board_with_references.json"
    if fixture_file.exists():
        with open(fixture_file) as f:
            return json.load(f)
    return None


@pytest.fixture
def empty_board_fixture(fixtures_dir):
    """Load empty board test fixture"""
    fixture_file = fixtures_dir / "empty_board.json"
    if fixture_file.exists():
        with open(fixture_file) as f:
            return json.load(f)
    return None
