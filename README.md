# trello2beads

**High-fidelity Trello board migration to beads issue tracking**

Migrate your Trello boards to [beads](https://github.com/steveyegge/beads) - a local, command-line-friendly, dependency-aware issue tracking system. Preserve all your cards, checklists, comments, and references without losing information.

## Features

- **High Fidelity**: Preserves cards, descriptions, checklists, attachments, comments, and labels
- **Smart Status Mapping**: Automatically maps Trello lists to beads status (open/in_progress/closed)
- **URL Resolution**: Converts Trello card references to beads issue references
- **Read-Only**: Safe, non-destructive Trello access (never modifies your Trello board)
- **Board Discovery**: Accepts board URL or ID - just copy/paste the URL from your browser
- **Rate Limiting**: Built-in rate limiting respects Trello's API limits (10 req/sec with burst support)
- **Pagination**: Automatic pagination handles boards with >1000 cards or comments
- **Offline Support**: Snapshot caching for faster re-runs and offline testing
- **Dry-Run Mode**: Preview conversion before creating issues

## Quick Start

### Prerequisites

1. **Python 3.10+**
2. **beads CLI** - Install from [github.com/steveyegge/beads](https://github.com/steveyegge/beads)
3. **Trello API credentials** - Get from [trello.com/power-ups/admin](https://trello.com/power-ups/admin)

### Installation

Choose your path based on your needs:

---

## 🚀 For Users (Just Want to Use the Tool)

**Best option: pipx** (recommended for corporate environments, old system Python, etc.)

```bash
# 1. Install pipx (if not already installed)
# macOS
brew install pipx
pipx ensurepath

# Linux
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Windows
python -m pip install --user pipx
python -m pipx ensurepath

# 2. Install trello2beads
git clone https://github.com/brettveenstra/trello2beads.git
cd trello2beads
pipx install -e .

# 3. The command is now available globally
trello2beads --help
```

**Why pipx?**
- ✅ Works with ANY system Python version (even old ones)
- ✅ Automatically manages virtual environments (you never see them)
- ✅ Command available globally, no activation needed
- ✅ Perfect for corporate Macs with restrictive environments
- ✅ No PATH issues, no version conflicts

---

## 👩‍💻 For Developers (Working on the Code)

**Best option: uv** (handles everything automatically)

```bash
# 1. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh  # macOS/Linux
# Or: brew install uv (macOS)

# 2. Clone and install
git clone https://github.com/brettveenstra/trello2beads.git
cd trello2beads

# 3. Install in editable mode with dev dependencies
uv pip install -e ".[dev]"

# 4. Command available, changes to code take effect immediately
trello2beads --help
pytest
```

**Why uv?**
- ✅ Automatically manages Python versions (no pyenv needed)
- ✅ Automatically manages virtual environments (transparent)
- ✅ 10-100x faster than pip
- ✅ Better dependency resolution
- ✅ Works great on corporate networks

**Alternative: Traditional pip + pyenv**

If you prefer traditional tools:

```bash
# 1. Install pyenv
brew install pyenv  # macOS
# or: curl https://pyenv.run | bash  # Linux

# 2. Install Python 3.12
pyenv install 3.12
pyenv local 3.12

# 3. Clone and install
git clone https://github.com/brettveenstra/trello2beads.git
cd trello2beads
pip install -e ".[dev]"
```

---

## 🆘 Troubleshooting

**"Python version too old" error:**
- Use `pipx` (recommended) - it manages Python versions for you
- Or install newer Python: `brew install python@3.12` (macOS)

**"externally-managed-environment" error:**
- Use `pipx` instead of `pip` (recommended)
- Or use: `python3 -m pip install --user -e .`

**Corporate firewall/proxy issues:**
- `pipx install -e .` usually works better than pip
- Or ask IT to allowlist: pypi.org, files.pythonhosted.org

**"SSL: CERTIFICATE_VERIFY_FAILED" error:**
```bash
# Use the --no-verify-ssl flag if needed for your network environment
trello2beads --no-verify-ssl --dry-run
```

**Alternative solutions:**
1. Export your environment's root certificate and point Python to it:
   ```bash
   export SSL_CERT_FILE=/path/to/root-cert.pem
   ```
2. Install certificates to Python's certificate bundle (see your network administrator)

**Command not found after install:**
- Run: `pipx ensurepath` and restart your shell
- Or manually add to PATH: `~/.local/bin` (Linux/macOS)

---

## 📋 Install beads

This tool requires the [beads](https://github.com/steveyegge/beads) CLI:

```bash
pipx install beads-project
# Or: pip install beads-project

# Verify installation
bd --version
```

### Setup Credentials

Get your Trello API credentials:

1. Go to https://trello.com/power-ups/admin
2. Create a new Power-Up (or use existing one)
3. Get your **API Key**
4. Generate a **Token** (click "Token" link, authorize access)

Find your board (choose one option):

**Option 1: Discover Your Boards (if unsure)**
```python
from trello2beads import TrelloReader

# Initialize without board_id to list all your boards
reader = TrelloReader(
    api_key="your-api-key-here",
    token="your-token-here"
)

# List all your open boards
boards = reader.list_boards()
for board in boards:
    print(f"{board['name']}: {board['url']}")

# Or list closed/archived boards
archived = reader.list_boards(filter_status="closed")

# Or list all boards (open + closed)
all_boards = reader.list_boards(filter_status="all")
```

**Option 2: Use Board URL (easiest)**
- Open your Trello board in a browser
- Copy the full URL from the address bar
- Example: `https://trello.com/b/ABC123/my-board-name`

**Option 3: Use Board ID**
- Open your Trello board in a browser
- Look at the URL: `https://trello.com/b/ABC123/board-name`
- The board ID is the 8-character code: `ABC123`

Set environment variables (choose board_id OR board_url):

**macOS / Linux**:

```bash
export TRELLO_API_KEY="your-api-key-here"
export TRELLO_TOKEN="your-token-here"
export TRELLO_BOARD_URL="https://trello.com/b/ABC123/board-name"  # Option 1
# OR
export TRELLO_BOARD_ID="ABC123"  # Option 2
```

**Windows (PowerShell)**:

```powershell
$env:TRELLO_API_KEY="your-api-key-here"
$env:TRELLO_TOKEN="your-token-here"
$env:TRELLO_BOARD_URL="https://trello.com/b/ABC123/board-name"  # Option 1
# OR
$env:TRELLO_BOARD_ID="ABC123"  # Option 2
```

**Windows (Command Prompt)**:

```cmd
set TRELLO_API_KEY=your-api-key-here
set TRELLO_TOKEN=your-token-here
set TRELLO_BOARD_URL=https://trello.com/b/ABC123/board-name
```

**Or create a `.env` file** (all platforms - easiest for development):

```bash
# Copy the example file
cp .env.example .env

# Edit .env and fill in your credentials
# TRELLO_API_KEY=your-api-key-here
# TRELLO_TOKEN=your-token-here
# TRELLO_BOARD_URL=https://trello.com/b/ABC123/my-board
```

**Windows** (PowerShell):

```powershell
@"
TRELLO_API_KEY=your-api-key-here
TRELLO_TOKEN=your-token-here
TRELLO_BOARD_URL=https://trello.com/b/ABC123/my-board
"@ | Out-File -FilePath .env -Encoding UTF8
```

### Run Conversion

There are three ways to run the converter:

**Option 1: Using installed command (recommended - works from anywhere)**

After running `pip install -e .`:

```bash
# Initialize a beads database
mkdir my-project && cd my-project
bd init --prefix myproject

# Preview what will be converted (dry-run)
trello2beads --dry-run

# Run the actual conversion
trello2beads

# View your converted issues
bd list
bd show myproject-abc
```

**Option 2: Using Python module (works from repo directory)**

```bash
# Must be in the repo directory or have PYTHONPATH set
cd /path/to/trello2beads

# Preview conversion
python3 -m trello2beads --dry-run

# Run conversion
python3 -m trello2beads
```

**Option 3: Using convenience scripts (works from repo directory)**

**macOS / Linux:**
```bash
cd /path/to/trello2beads  # Navigate to the cloned repository

# Preview conversion
./trello2beads.sh --dry-run

# Run conversion
./trello2beads.sh
```

**Windows (PowerShell):**
```powershell
cd C:\path\to\trello2beads  # Navigate to the cloned repository

# Preview conversion
.\trello2beads.ps1 --dry-run

# Run conversion
.\trello2beads.ps1
```

The scripts automatically set up PYTHONPATH and call the Python module for you.

**Recommendation**: Use Option 1 (`pip install -e .`) for the best experience - it lets you run `trello2beads` from any directory.

## Usage

### Basic Conversion

```bash
# Set credentials (or use .env file)
export TRELLO_API_KEY="..."
export TRELLO_TOKEN="..."
export TRELLO_BOARD_ID="..."

# Initialize beads in target directory
mkdir my-trello-board && cd my-trello-board
bd init --prefix myboard

# Run conversion (after installing with: pip install -e .)
trello2beads

# OR use Python module if not installed
# python3 -m trello2beads
```

### Dry Run (Preview Only)

Preview the conversion without creating any issues:

```bash
trello2beads --dry-run
# OR: python3 -m trello2beads --dry-run (if not installed)
```

This shows:
- Total cards that will be converted
- Status distribution (open/in_progress/closed)
- Features that will be preserved (checklists, attachments, comments)
- No actual issues created

### Custom Status Mapping

Override the default status keyword mapping with a JSON configuration file:

```bash
# Create custom mapping file
cat > my_mapping.json <<'EOF'
{
  "closed": ["done", "completed", "closed", "archived", "finished", "shipped"],
  "blocked": ["blocked", "waiting", "waiting on", "on hold", "paused", "stuck"],
  "deferred": ["deferred", "someday", "maybe", "later", "backlog", "future"],
  "in_progress": ["doing", "in progress", "wip", "active", "current", "working"],
  "open": ["todo", "to do", "planned", "ready"]
}
EOF

# Run with custom mapping
python3 -m trello2beads --status-mapping my_mapping.json
```

**Partial overrides** are supported - unspecified statuses use defaults:

```json
{
  "blocked": ["stuck", "impediment"],
  "deferred": ["icebox", "parking lot"]
}
```

See `status_mapping.example.json` for a complete template.

### Parallel Execution (Large Boards)

For boards with 100+ cards, enable parallel execution to significantly reduce conversion time:

```bash
# Enable parallel mode with 5 workers (recommended)
python3 -m trello2beads --max-workers 5

# Aggressive parallelism with 10 workers
python3 -m trello2beads --max-workers 10

# Serial execution (default, safe)
python3 -m trello2beads --max-workers 1
# OR just omit the flag (serial is default)
python3 -m trello2beads
```

**Performance Improvement**:

| Board Size | Serial (default) | Parallel (5 workers) | Speedup |
|-----------|-----------------|---------------------|---------|
| 100 cards | 10-16 seconds | 2-3 seconds | **5-8x faster** |
| 500 cards | 50-80 seconds | 8-12 seconds | **6x faster** |

**When to use**:
- ✅ Large boards (100+ cards) - significant time savings
- ✅ Fast machines with good I/O performance
- ✅ You've tested with `--dry-run` first

**When to avoid**:
- ❌ Small boards (<50 cards) - minimal benefit, adds complexity
- ❌ Debugging issues - serial execution is easier to troubleshoot
- ❌ Older machines or slow storage - may cause SQLite contention

**Technical details**:
- Uses Python's `ThreadPoolExecutor` to parallelize subprocess calls to `bd create`
- Safe: Gracefully falls back to serial execution if parallel fails
- Safe: Individual issue failures don't break the entire batch
- Progress indicators show creation status for large batches

**Note**: This is an **experimental feature**. Default is serial execution (max_workers=1) for maximum compatibility and reliability. Enable parallel mode only if you need faster conversion on large boards.

### Custom Paths

Override default paths using environment variables:

```bash
# Use different beads database
export BEADS_DB_PATH=/path/to/.beads/beads.db

# Save snapshot to custom location
export SNAPSHOT_PATH=/path/to/snapshot.json

# Use different .env file
export TRELLO_ENV_FILE=/path/to/credentials.env

python3 -m trello2beads
```

### Snapshot Caching

The first run fetches data from Trello API and saves it to `trello_snapshot.json`. Subsequent runs use the cached snapshot for instant conversion.

To force a fresh fetch:

```bash
rm trello_snapshot.json
python3 -m trello2beads
```

## How It Works

### Conversion Process

The converter runs in two passes:

**Pass 1: Create Issues**
1. Fetches all cards from Trello (or loads from snapshot)
2. Creates beads issues with mapped status (serial or parallel mode)
3. Builds URL mapping (Trello card ID → beads issue ID)

**Pass 2: Resolve References**
1. Finds Trello card URLs in descriptions, comments, and attachments
2. Replaces them with beads issue references
3. Updates issue descriptions

**Execution Modes**:
- **Serial (default)**: Creates issues one at a time - safe, predictable, easier to debug
- **Parallel (opt-in)**: Creates multiple issues concurrently using `--max-workers N` - 5-8x faster on large boards

### Enhanced Card Reading

The tool fetches **complete card data with all relationships** in a single API request for maximum efficiency:

- **Attachments**: Files and links attached to cards (with metadata)
- **Checklists**: All checklist items with completion status
- **Members**: Users assigned to each card (with full profile data)
- **Custom Field Items**: All custom field values (text, number, checkbox, date)
- **Stickers**: Visual decorations applied to cards (with positioning)
- **All Card Fields**: Complete card metadata (name, description, labels, dates, etc.)

This comprehensive fetch strategy minimizes API calls while ensuring high-fidelity data migration. The tool automatically handles pagination when boards contain more than 1000 cards.

### Rate Limiting

The tool implements **token bucket rate limiting** to respect Trello's API limits:

- **Limit**: 10 requests per second (sustained)
- **Burst**: Up to 10 requests can be made immediately
- **Algorithm**: Token bucket - tokens replenish at 10/sec, burst allows short spikes
- **Behavior**: Requests automatically wait if limit is reached (no manual throttling needed)

**Trello's official limits**:
- 100 requests per 10 seconds per token
- 300 requests per 10 seconds per API key

The rate limiter is conservative (10 req/sec vs Trello's 30 req/sec key limit) to ensure reliability. For boards with hundreds of cards and comments, this prevents hitting API limits while keeping conversions fast.

### Pagination Support

The tool automatically handles **large boards with more than 1000 cards**:

- **Trello's Limit**: API responses are capped at 1000 items per request
- **Automatic Pagination**: The tool detects when more data exists and makes additional requests
- **Algorithm**: Uses Trello's `before` parameter with the last item ID to fetch next page
- **Transparent**: No configuration needed - works automatically for any board size
- **Applies to**: Card lists and comment threads (both can exceed 1000 items)

**How it works**:
1. Fetches first 1000 items (cards or comments)
2. If result contains exactly 1000 items, fetches the next page
3. Uses the ID of the last item as the `before` parameter
4. Continues until all items are retrieved or a page has <1000 items
5. Combines all pages into a single list

This ensures **complete data retrieval** for large boards without hitting Trello's pagination limits.

### Board Discovery

The tool supports **multiple ways to specify your board**:

- **Board URL**: Provide the full URL from your browser (easiest - just copy and paste)
  - Example: `https://trello.com/b/Bm0nnz1R/my-project-board`
  - Works with or without `https://`
  - Works with board name in URL or without

- **Board ID**: Provide just the 8-character board ID
  - Example: `Bm0nnz1R`
  - Extracted from URL if needed

**How it works**:
- Uses regex pattern matching to extract board ID from URLs
- Supports various URL formats (with/without protocol, with/without board name)
- Validates format before making API calls
- If board URL is provided, board ID is automatically extracted

This makes it easy to migrate boards - just copy the URL from your browser!

### Retry Logic & Error Handling

The tool implements **intelligent retry logic with exponential backoff** for resilient API calls:

- **Automatic Retries**: Automatically retries failed requests up to 3 times
- **Exponential Backoff**: Progressive delays between retries (1s, 2s, 4s)
- **Smart Error Detection**: Only retries transient errors, fails fast on permanent errors
- **Network Resilience**: Handles timeouts, connection errors, and temporary outages

**Retry Strategy**:

| Error Type | Status Codes | Retry? | Reason |
|-----------|-------------|--------|--------|
| Rate Limit | 429 | ✅ Yes | Temporary - server asks to slow down |
| Server Error | 500, 502, 503, 504 | ✅ Yes | Transient - server may recover |
| Auth Error | 401, 403 | ❌ No | Permanent - invalid credentials |
| Not Found | 404 | ❌ No | Permanent - resource doesn't exist |
| Network Timeout | - | ✅ Yes | Transient - network may recover |
| Connection Error | - | ✅ Yes | Transient - connection may recover |

**How it works**:
1. Makes initial API request
2. If request fails with transient error (429, 500, 503, etc.), waits 1 second and retries
3. If second attempt fails, waits 2 seconds and retries
4. If third attempt fails, waits 4 seconds and retries (last attempt)
5. If all retries exhausted, raises the original exception
6. For permanent errors (401, 404), fails immediately without retrying

This ensures **reliable data fetching** even when Trello's API experiences temporary issues or rate limiting, while avoiding wasted retries on permanent errors.

### Mapping Strategy

#### Lists → Status

Trello list names are mapped to beads status using keyword matching:

| List Name Examples | Beads Status |
|-------------------|--------------|
| "To Do" | `open` |
| "Doing", "In Progress", "WIP" | `in_progress` |
| "Blocked", "Waiting On", "On Hold" | `blocked` |
| "Backlog", "Someday", "Later" | `deferred` |
| "Done", "Completed", "Archived" | `closed` |
| Anything else | `open` (safe default) |

Default keywords matched (case-insensitive):
- **closed**: done, completed, closed, archived, finished
- **blocked**: blocked, waiting, waiting on, on hold, paused
- **deferred**: deferred, someday, maybe, later, backlog, future
- **in_progress**: doing, in progress, wip, active, current, working
- **open**: (default for anything not matching above)

Customize with `--status-mapping mapping.json` (see Custom Status Mapping section).

The original list name is preserved as a label (`list:To Do`) for filtering.

#### Cards → Issues

| Trello | Beads | Notes |
|--------|-------|-------|
| Card name | Issue title | Direct mapping |
| Card description | Issue description | Base content |
| Checklists | Markdown checklists | Preserves checked state |
| Attachments | Markdown links | With file sizes |
| Comments | Quoted text with author/date | Chronological order |
| Labels | Labels (`trello-label:name`) | Only if present on card |
| List position | Creation order | Maintained |
| Priority | P2 (medium) | Hard-coded in V1 |
| Type | task | Hard-coded in V1 |

### What's Preserved

✅ **Fully Supported**:
- Card names and descriptions
- Checklists (with completion status)
- Attachments (as links)
- Comments (with author and date)
- Trello labels
- Card references (URLs converted to beads issue IDs)
- List membership (as labels)
- **Card members** (assigned users) - fetched with full relationships
- **Custom field items** (custom field values) - all field types supported
- **Stickers** (visual decorations) - preserved with positioning

⏳ **Planned for V2/V3**:
- Due dates
- Priority mapping (from labels or card attributes)
- Type mapping (bug/feature/task)
- Custom field definitions mapping

❌ **Not Supported**:
- Card cover images
- Board backgrounds
- Power-Ups
- Real-time sync (one-time migration only)

## Examples

### Example 1: Simple Board

**Trello Board**:
- Lists: "To Do" (5 cards), "In Progress" (2 cards), "Done" (8 cards)
- No comments or attachments

**Conversion**:
```bash
$ python3 -m trello2beads --dry-run

📊 CONVERSION SUMMARY
Board: My Simple Board
Lists: 3
Total Cards: 15

Preserved Features:
  Checklists: 0 cards
  Attachments: 0 cards
  Comments: 0 cards

Status Distribution:
  open: 5
  in_progress: 2
  closed: 8

🎯 Dry run complete. Would create 15 issues
```

### Example 2: Standard Board

**Trello Board**:
- 10 cards across 3 lists (To Do, Doing, Done)
- Mix of open, in-progress, and completed tasks
- Standard software development workflow

**Conversion**:
```bash
$ python3 -m trello2beads

✅ Created myproject-001: Write README (list:To Do)
✅ Created myproject-002: Setup CI/CD (list:To Do)
✅ Created myproject-003: Add tests (list:To Do)
✅ Created myproject-004: Implement authentication (list:Doing)
✅ Created myproject-005: Update dependencies (list:Doing)
✅ Created myproject-006: Initial project setup (list:Done)
✅ Created myproject-007: Choose tech stack (list:Done)
✅ Created myproject-008: Design database schema (list:Done)
✅ Created myproject-009: Write project proposal (list:Done)
✅ Created myproject-010: Get approval (list:Done)

🔄 Pass 2: Resolving Trello card references...
✅ Resolved 0 Trello card references

📊 CONVERSION SUMMARY
Board: Example Todo Board
Lists: 3
Total Cards: 10
Issues Created: 10/10

Preserved Features:
  Checklists: 0 cards
  Attachments: 0 cards
  Comments: 0 cards (0 total comments)

Status Distribution:
  open: 3
  in_progress: 2
  closed: 5

✅ Conversion complete!

View issues: bd list
Query by list: bd list --labels 'list:To Do'
Show issue: bd show <issue-id>
```

### Example 3: Card References

**Trello Board**:
- Card A description: "Blocked by https://trello.com/c/abc123"
- Card B (short link: abc123)

**After Conversion**:
- Card A → `myproject-xyz` with description: "Blocked by See myproject-abc"
- Card B → `myproject-abc`

## Querying Converted Issues

After conversion, use beads commands to work with your issues:

```bash
# List all issues
bd list

# Filter by original list
bd list --labels 'list:To Do'
bd list --labels 'list:Done'

# Filter by status
bd list --status open
bd list --status in_progress

# Show full issue details
bd show myproject-abc

# Search issue titles
bd list | grep -i "authentication"

# Count issues by list
bd list --labels 'list:Backlog' | wc -l
```

## Troubleshooting

### Error Handling

The tool provides helpful error messages for common issues:

**Authentication Errors (401/403)**:
- `TrelloAuthenticationError`: Invalid API credentials or insufficient permissions
- **Solution**: Verify your `TRELLO_API_KEY` and `TRELLO_TOKEN` at https://trello.com/power-ups/admin
- Check that your token has permission to access the board

**Resource Not Found (404)**:
- `TrelloNotFoundError`: Board or resource doesn't exist
- **Solution**: Verify your board ID is correct and the board exists
- Ensure the board hasn't been deleted or archived

**Rate Limiting (429)**:
- `TrelloRateLimitError`: Exceeded Trello's API rate limit (100 req/10sec)
- **Solution**: Wait a few minutes and try again
- The tool automatically retries with exponential backoff (1s, 2s, 4s)

**Server Errors (500/502/503/504)**:
- `TrelloServerError`: Trello's servers are experiencing issues
- **Solution**: Wait and try again later - server errors are automatically retried
- Check Trello's status page for ongoing outages

**Network Errors**:
- `TrelloAPIError`: Timeout or connection issues
- **Solution**: Check your internet connection
- Network errors are automatically retried up to 3 times

All errors include detailed messages explaining the issue and suggesting next steps.

### "Missing required Trello credentials"

Make sure you've set all three environment variables:
```bash
export TRELLO_API_KEY="..."
export TRELLO_TOKEN="..."
export TRELLO_BOARD_ID="..."
```

Or create a `.env` file in the directory where you run the script.

### "Beads database not found"

You need to initialize a beads database first:
```bash
bd init --prefix myproject
```

Make sure you're running the script from the directory containing `.beads/`, or set `BEADS_DB_PATH`.

### "UNIQUE constraint failed: external_ref"

You've already converted this board to this beads database. Either:
- Use a fresh beads database: `bd init --prefix different-name`
- Or close/delete existing issues before re-running

### Issues Have Wrong Status

Check your list names - the mapping uses default keywords:
- Lists with "done", "complete", etc. → `closed`
- Lists with "blocked", "waiting", etc. → `blocked`
- Lists with "deferred", "backlog", etc. → `deferred`
- Lists with "doing", "wip", etc. → `in_progress`
- Everything else → `open`

**Solution 1**: Create a custom mapping file:
```bash
python3 -m trello2beads --status-mapping custom.json
```

**Solution 2**: Manually update status after conversion:
```bash
bd update <issue-id> --status closed
```

### BeadsWriter Errors

**"bd CLI not found"** (`BeadsCommandError`):
- **Cause**: beads is not installed or not in PATH
- **Fix**: Install beads from https://github.com/steveyegge/beads and ensure `bd` command works

**"Failed to create issue"** (`BeadsIssueCreationError`):
- **Cause**: Database not initialized, permission issues, or bd CLI version mismatch
- **Fix**: Run `bd init` in your project directory, check file permissions on `.beads/`
- If persists, update beads to latest version

**"Could not parse issue ID"**:
- **Cause**: bd CLI output format changed (after beads update)
- **Fix**: File an issue at https://github.com/brettveenstra/trello2beads/issues with your beads version

**Input validation errors** (`ValueError`):
- `"Title cannot be empty"` - Provide a non-empty title
- `"Invalid status: 'done'"` - Use valid status: `open`, `in_progress`, `blocked`, `deferred`, `closed`
- `"Priority must be 0-4"` - Use integer 0-4 (0=critical, 4=backlog)

All BeadsWriter exceptions include the failing command and error details to help diagnose issues.

## FAQ

**Q: Does this sync changes from Trello?**
A: No, it's a one-time migration. Trello → beads only.

**Q: Will it modify my Trello board?**
A: No, it's read-only. Your Trello board is never modified.

**Q: Can I run it multiple times?**
A: Yes, but it will fail if issues with the same `external_ref` already exist. Use a fresh beads database or clean up existing issues first.

**Q: What happens to card attachments?**
A: They're preserved as Markdown links in the issue description. Files are NOT downloaded.

**Q: Can I customize the status mapping?**
A: Yes! Use `--status-mapping path/to/mapping.json` to override default keywords. See the "Custom Status Mapping" section for details.

**Q: Where are my comments?**
A: Comments are added to the issue description in a `## Comments` section, preserving author, date, and text.

**Q: How do I find a specific card after conversion?**
A: Each issue has the Trello short link in its `external_ref` field (e.g., `trello:abc123`). Use beads queries or search the `.beads/issues.jsonl` file.

## Development

Want to contribute? See **[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)** for setup and guidelines.

This is V1 - a working, production-ready tool with a simple mapping strategy.

**Roadmap**:
- V1 (current): Hard-coded mapping, high-fidelity content preservation
- V2 (planned): Configurable mappings (YAML config file)
- V3 (planned): Assignee support, due dates, priority mapping

## Related Tools

- [beads](https://github.com/steveyegge/beads) - The issue tracker this tool targets
- [beads_viewer (bv)](https://github.com/Dicklesworthstone/beads_viewer) - Enhanced beads UI
- [Trello API Documentation](https://developer.atlassian.com/cloud/trello/)

## License

MIT License - See LICENSE file for details

## Author

Brett Veenstra ([brettveenstra@gmail.com](mailto:brettveenstra@gmail.com))

## Support

For issues, questions, or contributions:
- GitHub Issues: https://github.com/brettveenstra/trello2beads/issues
- Email: brettveenstra@gmail.com
