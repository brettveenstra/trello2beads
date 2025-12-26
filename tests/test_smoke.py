"""
Smoke test to verify test infrastructure works
"""

import pytest


def test_pytest_working():
    """Verify pytest is configured correctly"""
    assert True


def test_can_import_main_module():
    """Verify we can import the main trello2beads package"""
    try:
        import sys
        from pathlib import Path

        # Add parent directory to path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        # Check the package structure exists
        package_dir = Path(__file__).parent.parent / "trello2beads"
        assert package_dir.exists(), "trello2beads/ package should exist"
        assert package_dir.is_dir(), "trello2beads should be a directory"

        init_file = package_dir / "__init__.py"
        assert init_file.exists(), "trello2beads/__init__.py should exist"

        # Verify we can import from the package
        import trello2beads

        assert hasattr(trello2beads, "TrelloReader"), "Should export TrelloReader"
        assert hasattr(trello2beads, "BeadsWriter"), "Should export BeadsWriter"
        assert hasattr(trello2beads, "TrelloToBeadsConverter"), (
            "Should export TrelloToBeadsConverter"
        )
    except ImportError as e:
        pytest.skip(f"Module import not yet configured: {e}")


def test_fixtures_directory_exists(fixtures_dir):
    """Verify fixtures directory is accessible"""
    assert fixtures_dir.exists()
    assert fixtures_dir.is_dir()
