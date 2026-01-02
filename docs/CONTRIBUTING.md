# Contributing to trello2beads

Thank you for your interest in contributing! This guide will help you get set up for development.

## Development Setup

### Prerequisites

1. **Python 3.10+**
2. **beads CLI** - `pipx install beads-project`
3. **Git**

### Recommended Setup: uv (Modern, Fast)

The fastest and easiest way to get started:

```bash
# 1. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh
# Or: brew install uv (macOS)

# 2. Clone repository
git clone https://github.com/brettveenstra/trello2beads.git
cd trello2beads

# 3. Install in editable mode with dev dependencies
uv pip install -e ".[dev]"

# 4. Verify setup
trello2beads --help
pytest --version
ruff --version
mypy --version
```

**What `uv` does for you:**
- Automatically manages Python versions (no pyenv needed)
- Automatically creates/manages virtual environments
- 10-100x faster than pip
- Better dependency resolution

---

### Alternative Setup: Traditional Tools

If you prefer the traditional Python toolchain:

```bash
# 1. Install pyenv (Python version manager)
brew install pyenv  # macOS
# or: curl https://pyenv.run | bash  # Linux

# Add to shell config (~/.zshrc, ~/.bashrc):
# export PYENV_ROOT="$HOME/.pyenv"
# export PATH="$PYENV_ROOT/bin:$PATH"
# eval "$(pyenv init -)"

# 2. Install Python 3.12
pyenv install 3.12
pyenv local 3.12

# 3. Clone and install
git clone https://github.com/brettveenstra/trello2beads.git
cd trello2beads
pip install -e ".[dev]"
```

---

### What Gets Installed

Running `pip install -e ".[dev]"` or `uv pip install -e ".[dev]"` installs:

**Runtime Dependencies:**
- `requests` - Trello API client
- `urllib3<2` - macOS LibreSSL compatibility

**Development Tools (`[dev]` extra):**
- `pytest`, `pytest-cov`, `pytest-mock`, `responses` - Testing framework
- `mypy`, `types-requests` - Static type checking
- `ruff` - Fast linting and formatting (replaces flake8, black, isort)
- `bandit` - Security vulnerability scanner
- `pip-audit` - Dependency security auditing
- `coverage` - Code coverage reporting

**Configuration:**
- All tool configuration lives in `pyproject.toml` (single source of truth)
- No separate config files (`requirements.txt`, `pytest.ini`, `mypy.ini`, etc.)

---

## Daily Development Workflow

### Testing Code Changes (In Virtual Environment)

```bash
# Make changes to code in trello2beads/

# Run tests (quick)
pytest

# Run full test suite with coverage
./run_tests.sh

# Type check
mypy trello2beads

# Lint and format
ruff check .           # Check for issues
ruff check --fix .     # Auto-fix issues
ruff format .          # Format code

# Security scan
bandit -r trello2beads
pip-audit
```

### Testing the CLI Tool (Globally Installed via pipx)

When you need to test the actual `trello2beads` command as users will run it:

```bash
# After making code changes and committing/pulling
cd /path/to/trello2beads/repo

# Reinstall from local repo (picks up latest changes)
pipx reinstall --force trello2beads

# Or if installed with editable mode:
pipx uninstall trello2beads
pipx install -e .

# Verify the tool works with your changes
trello2beads --help
trello2beads --test-connection
```

**When to use this:**
- After `git pull` to pick up remote changes
- Testing user-facing CLI behavior
- Troubleshooting installation issues
- Verifying fixes work in production-like environment

### Continuous Integration Script

The `./run_tests.sh` script runs everything CI runs:
- Unit tests with coverage
- Linting (ruff)
- Type checking (mypy)

```bash
./run_tests.sh           # Full quality checks
./run_tests.sh --quick   # Tests only (skip linting/types)
```

---

## Testing

### Unit Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_converter.py

# Run with verbose output
pytest -v

# Run tests matching pattern
pytest -k "test_url_resolution"
```

### Integration Tests

Integration tests require a real Trello board and API credentials:

```bash
# Set up credentials
export TRELLO_API_KEY="your-key"
export TRELLO_TOKEN="your-token"

# Run integration tests
pytest tests/integration/ -v
```

### Coverage

```bash
# Generate coverage report
pytest --cov=trello2beads --cov-report=html

# Open HTML report
open htmlcov/index.html  # macOS
# or: xdg-open htmlcov/index.html  # Linux
```

---

## Code Style

We follow standard Python conventions with a few specifics:

### Style Guidelines

- **PEP 8** compliance (enforced by ruff)
- **Type hints** on all public functions
- **Docstrings** for public APIs (Google style)
- **Line length**: 100 characters
- **Descriptive naming**: Avoid abbreviations except common ones (API, CLI, ID)

### Example

```python
def read_board(board_id: str, include_closed: bool = False) -> dict[str, Any]:
    """Read Trello board with all lists, cards, and labels.

    Args:
        board_id: Trello board ID (8 characters)
        include_closed: Include archived/closed cards

    Returns:
        Board data with lists, cards, labels, and members

    Raises:
        TrelloAPIError: If API request fails
        ValidationError: If board_id is invalid
    """
    # Implementation
```

### Auto-formatting

We use `ruff` for both linting and formatting:

```bash
# Format code (safe, idempotent)
ruff format .

# Fix linting issues automatically
ruff check --fix .
```

---

## Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write tests for new functionality
   - Update documentation as needed
   - Follow code style guidelines

3. **Run quality checks**
   ```bash
   ./run_tests.sh  # Must pass before PR
   ```

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat: add feature description"
   ```

   We follow [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` - New feature
   - `fix:` - Bug fix
   - `docs:` - Documentation changes
   - `test:` - Test additions/changes
   - `refactor:` - Code refactoring
   - `chore:` - Maintenance tasks

5. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```
   Then open a pull request on GitHub.

---

## Project Structure

```
trello2beads/
├── trello2beads/           # Main package
│   ├── __init__.py
│   ├── cli.py             # CLI entry point
│   ├── trello_client.py   # Trello API client
│   ├── beads_client.py    # Beads integration
│   ├── converter.py       # Trello → Beads conversion logic
│   ├── exceptions.py      # Custom exceptions
│   ├── rate_limiter.py    # API rate limiting
│   └── logging_config.py  # Logging setup
├── tests/
│   ├── unit/              # Unit tests
│   └── integration/       # Integration tests
├── docs/
│   └── CONTRIBUTING.md    # This file
├── pyproject.toml         # Package configuration
├── README.md              # User documentation
├── INSTALL.md             # Quick installation guide
└── run_tests.sh           # Test runner script
```

---

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/brettveenstra/trello2beads/issues)
- **Discussions**: [GitHub Discussions](https://github.com/brettveenstra/trello2beads/discussions)
- **Email**: brettveenstra@gmail.com

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
