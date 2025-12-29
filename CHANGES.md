# Installation Modernization - December 2024

## What Changed

Completely modernized the Python packaging and installation workflow to eliminate friction for both users and developers.

## Problem We Solved

**Before:**
- 381-line bash script managing dependencies manually
- Hardcoded `python3` command (failed on old Python versions)
- Separate `requirements*.txt` files duplicating `pyproject.toml`
- Interactive prompts blocking automation
- Corporate Mac users with Python 3.9 couldn't install
- Fighting Python's native tooling instead of using it

**After:**
- One command: `pipx install -e .` (users) or `uv pip install -e ".[dev]"` (developers)
- Works with ANY Python version (pipx handles it)
- Single source of truth: `pyproject.toml`
- No manual venv management
- No version conflicts

## Files Changed

### Added
- `repo/.env.example` - Template for Trello credentials
- `repo/INSTALL.md` - Quick start for impatient users
- `repo/CHANGES.md` - This file

### Modified
- `repo/pyproject.toml` - Added `[dev]` optional dependencies, consolidated all tool config
- `repo/README.md` - Bifurcated: USER (pipx) first, DEVELOPER (uv) second
- `repo/.gitignore` - Fixed `.env` pattern (was `*.env`)
- `repo/run_tests.sh` - Uses `pip install -e ".[dev]"` instead of requirements files
- `docs/development-guide.md` - Modern setup with `uv` primary, traditional as fallback

### Deleted
- `repo/install.sh` - Replaced by standard Python tooling
- `repo/requirements.txt` - Consolidated into `pyproject.toml`
- `repo/requirements-dev.txt` - Consolidated into `pyproject.toml`
- `repo/pytest.ini` - Moved to `pyproject.toml`
- `repo/mypy.ini` - Moved to `pyproject.toml`
- `repo/.coveragerc` - Moved to `pyproject.toml`

## Installation Methods

### For Users (Just Want to Use the Tool)
```bash
brew install pipx && pipx ensurepath
cd repo/
pipx install -e .
trello2beads --help  # Works globally!
```

### For Developers (Working on Code)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
cd repo/
uv pip install -e ".[dev]"
pytest  # All dev tools installed
```

## Why These Tools?

**pipx** (for users):
- Manages its own Python environments
- Works with old system Python
- Commands available globally
- Perfect for corporate environments

**uv** (for developers):
- Handles Python versions automatically
- Manages venvs transparently
- 10-100x faster than pip
- Better dependency resolution

## Testing

Package is installable via:
- ✅ `pipx install -e .` (user mode)
- ✅ `uv pip install -e ".[dev]"` (dev mode)
- ✅ `pip install -e ".[dev]"` (traditional)

All configurations moved to `pyproject.toml`:
- ✅ pytest
- ✅ mypy
- ✅ ruff
- ✅ coverage

## Migration Guide

**If you previously used `install.sh`:**

1. Delete your old `.venv` directory
2. Follow new instructions in `INSTALL.md` or `README.md`
3. Use `pipx install -e .` instead

**If you're a developer:**

1. Install `uv`: `brew install uv`
2. Run: `uv pip install -e ".[dev]"`
3. All dev tools work immediately

## Documentation

- **Users**: Read `INSTALL.md` (quick) or `README.md` (detailed)
- **Developers**: Read `docs/development-guide.md`
