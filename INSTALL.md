# Installation Quick Start

**For impatient users who just want it working NOW.**

## Your Situation: Corporate Mac with Old Python

If you have:
- Corporate MacBook
- System Python 3.9 (or older)
- Can't easily install new Python versions
- Just want the tool to work

**Do this:**

```bash
# 1. Install pipx (works with your old Python)
brew install pipx
pipx ensurepath

# Restart your shell or run:
source ~/.zshrc  # or ~/.bashrc

# 2. Navigate to the repo
cd /path/to/trello2beads/repo

# 3. Install trello2beads
pipx install -e .

# 4. Install beads
pipx install beads-project

# 5. Verify it works
trello2beads --help
bd --version

# Done! The commands work globally from any directory.
```

## What Just Happened?

- `pipx` created isolated Python environments for both tools
- Used Python 3.12 automatically (it downloads it if needed)
- Commands are now in your PATH globally
- No venv activation, no version conflicts, no headaches

## Next Steps

1. Set up Trello credentials (see [README.md](README.md#setup-credentials))
2. Run your first migration: `trello2beads --help`

## Troubleshooting

**"pipx: command not found"**
```bash
# Make sure Homebrew is updated
brew update
brew install pipx
```

**"command not found: trello2beads" after install**
```bash
# Add pipx bin directory to PATH
pipx ensurepath
# Then restart your shell
```

**Need to reinstall after code changes? (Development/Testing)**
```bash
# Force reinstall from local repo (useful after git pull)
cd /path/to/trello2beads/repo
pipx reinstall --force trello2beads

# Or if installed with editable mode (-e):
pipx uninstall trello2beads
pipx install -e .
```

**Still having issues?**
- Check that `~/.local/bin` is in your PATH: `echo $PATH`
- Try: `python3 -m pipx install -e .` instead
- Verify version: `trello2beads --help` (check for expected features)

---

For detailed docs, see [README.md](README.md)
