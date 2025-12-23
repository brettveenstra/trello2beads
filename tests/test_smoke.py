"""
Smoke test to verify test infrastructure works
"""

import pytest


def test_pytest_working():
    """Verify pytest is configured correctly"""
    assert True


def test_can_import_main_module():
    """Verify we can import the main trello2beads module"""
    # This will fail until we make trello2beads importable, but that's okay for now
    try:
        import sys
        from pathlib import Path

        # Add parent directory to path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        # Try to import (will work once trello2beads.py is a module)
        # For now, just check the file exists
        module_file = Path(__file__).parent.parent / "trello2beads.py"
        assert module_file.exists(), "trello2beads.py should exist"
    except ImportError:
        pytest.skip("Module import not yet configured")


def test_fixtures_directory_exists(fixtures_dir):
    """Verify fixtures directory is accessible"""
    assert fixtures_dir.exists()
    assert fixtures_dir.is_dir()
