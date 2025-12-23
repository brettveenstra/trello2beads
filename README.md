# trello2beads

**High-fidelity Trello board migration to beads issue tracking**

Migrate your Trello boards to [beads](https://github.com/steveyegge/beads) - a local, command-line-friendly, dependency-aware issue tracking system. Preserve all your cards, checklists, comments, and references without losing information.

## Features

- **High Fidelity**: Preserves cards, descriptions, checklists, attachments, comments, and labels
- **Smart Status Mapping**: Automatically maps Trello lists to beads status (open/in_progress/closed)
- **URL Resolution**: Converts Trello card references to beads issue references
- **Read-Only**: Safe, non-destructive Trello access (never modifies your Trello board)
- **Offline Support**: Snapshot caching for faster re-runs and offline testing
- **Dry-Run Mode**: Preview conversion before creating issues

## Quick Start

### Prerequisites

1. **Python 3.8+**
2. **beads CLI** - Install from [github.com/steveyegge/beads](https://github.com/steveyegge/beads)
3. **Trello API credentials** - Get from [trello.com/power-ups/admin](https://trello.com/power-ups/admin)

### Installation

```bash
# Clone or download this repository
git clone https://github.com/brettveenstra/trello2beads.git
cd trello2beads

# Install Python dependencies
pip install -r requirements.txt
```

### Setup Credentials

Get your Trello API credentials:

1. Go to https://trello.com/power-ups/admin
2. Create a new Power-Up (or use existing one)
3. Get your **API Key**
4. Generate a **Token** (click "Token" link, authorize access)

Find your board ID:
- Open your Trello board in a browser
- Look at the URL: `https://trello.com/b/ABC123/board-name`
- The board ID is `ABC123`

Set environment variables:

```bash
export TRELLO_API_KEY="your-api-key-here"
export TRELLO_TOKEN="your-token-here"
export TRELLO_BOARD_ID="your-board-id-here"
```

Or create a `.env` file:

```bash
cat > .env <<'EOF'
TRELLO_API_KEY=your-api-key-here
TRELLO_TOKEN=your-token-here
TRELLO_BOARD_ID=your-board-id-here
EOF
```

### Run Conversion

```bash
# Initialize a beads database
mkdir my-project && cd my-project
bd init --prefix myproject

# Preview what will be converted (dry-run)
python3 ../trello2beads.py --dry-run

# Run the actual conversion
python3 ../trello2beads.py

# View your converted issues
bd list
bd show myproject-abc
```

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

# Run conversion
python3 /path/to/trello2beads.py
```

### Dry Run (Preview Only)

Preview the conversion without creating any issues:

```bash
python3 trello2beads.py --dry-run
```

This shows:
- Total cards that will be converted
- Status distribution (open/in_progress/closed)
- Features that will be preserved (checklists, attachments, comments)
- No actual issues created

### Custom Paths

Override default paths using environment variables:

```bash
# Use different beads database
export BEADS_DB_PATH=/path/to/.beads/beads.db

# Save snapshot to custom location
export SNAPSHOT_PATH=/path/to/snapshot.json

# Use different .env file
export TRELLO_ENV_FILE=/path/to/credentials.env

python3 trello2beads.py
```

### Snapshot Caching

The first run fetches data from Trello API and saves it to `trello_snapshot.json`. Subsequent runs use the cached snapshot for instant conversion.

To force a fresh fetch:

```bash
rm trello_snapshot.json
python3 trello2beads.py
```

## How It Works

### Conversion Process

The converter runs in two passes:

**Pass 1: Create Issues**
1. Fetches all cards from Trello (or loads from snapshot)
2. Creates beads issues with mapped status
3. Builds URL mapping (Trello card ID → beads issue ID)

**Pass 2: Resolve References**
1. Finds Trello card URLs in descriptions, comments, and attachments
2. Replaces them with beads issue references
3. Updates issue descriptions

### Mapping Strategy

#### Lists → Status

Trello list names are mapped to beads status using keyword matching:

| List Name Examples | Beads Status |
|-------------------|--------------|
| "To Do", "Backlog" | `open` |
| "Doing", "In Progress", "WIP" | `in_progress` |
| "Done", "Completed", "Archived" | `closed` |
| Anything else | `open` (safe default) |

Keywords matched (case-insensitive):
- **closed**: done, completed, closed, archived, finished
- **in_progress**: doing, in progress, wip, active, current, working

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

⏳ **Planned for V2/V3**:
- Card assignees (members)
- Due dates
- Priority mapping (from labels or card attributes)
- Type mapping (bug/feature/task)

❌ **Not Supported**:
- Card cover images
- Custom fields
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
$ python3 trello2beads.py --dry-run

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
$ python3 trello2beads.py

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

Check your list names - the mapping uses keywords:
- Lists with "done", "complete" → `closed`
- Lists with "doing", "wip" → `in_progress`
- Everything else → `open`

You can manually update status after conversion:
```bash
bd update <issue-id> --status closed
```

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
A: Not in V1. The mapping logic is hard-coded. V2 will support configurable mappings.

**Q: Where are my comments?**
A: Comments are added to the issue description in a `## Comments` section, preserving author, date, and text.

**Q: How do I find a specific card after conversion?**
A: Each issue has the Trello short link in its `external_ref` field (e.g., `trello:abc123`). Use beads queries or search the `.beads/issues.jsonl` file.

## Development

This is V1 - a working, production-ready tool with a simple mapping strategy.

**Roadmap**:
- V1 (current): Hard-coded mapping, high-fidelity content preservation
- V2 (planned): Configurable mappings (YAML config file)
- V3 (planned): Assignee support, due dates, priority mapping

See the main repository for development docs and contribution guidelines.

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
