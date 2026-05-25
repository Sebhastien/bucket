# Bucket List CLI

A local-first command-line app for managing a personal bucket list with SQLite, rich terminal output, JSON-friendly automation, GTD-style review, and pairwise ranking review.

The project is intentionally lightweight: Python, Typer, Rich, and the standard-library `sqlite3` module. Dependency and environment management use [`uv`](https://docs.astral.sh/uv/).

## Features

- Add, list, show, edit, complete, mark no-longer-me, and delete bucket list items
- Local SQLite database with automatic migrations
- Horizon planning: `now`, `soon`, `later`, `waiting`
- Lifecycle statuses: `active`, `in_progress`, `completed`, `no_longer_me`
- Dependency blocking: mark items as blocked by other items
- Tagging for flexible categorization
- Notes on individual items
- Fuzzy search by title or description
- Rich human-readable terminal output
- `--json` output for scripting and agent workflows
- Stable database override via `--db`
- Interactive GTD-style review for keeping, moving horizons, completing, or marking items no-longer-me
- Pairwise ranking review with binary-search insertion
- `--until-all-ranked` mode to rank every unranked eligible item
- JSON backup and restore

## Requirements

- Python 3.11+
- `uv`

Install `uv` if needed:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Quick Start

Clone the repository and install dependencies:

```bash
git clone https://github.com/Sebhastien/bucket.git
cd bucket
uv sync
```

Run the CLI:

```bash
uv run bucket --help
```

Add a few items:

```bash
uv run bucket add "Visit Japan" --horizon soon
uv run bucket add "Hike the Grand Canyon" --horizon now
uv run bucket add "Learn scuba diving" --horizon later
```

List items:

```bash
uv run bucket list --all
```

Use a throwaway database while testing:

```bash
uv run bucket --db ./test.sqlite add "Visit Iceland"
uv run bucket --db ./test.sqlite list --all
```

## Commands

### Add an item

```bash
uv run bucket add "Hike the Grand Canyon" \
  --horizon soon \
  --desc "Rim-to-rim trip" \
  --priority 3 \
  --date 2027-01-01
```

### List items

By default, `list` shows actionable `now` items only (`active` or `in_progress`):

```bash
uv run bucket list
```

Show everything:

```bash
uv run bucket list --all
```

Filter by horizon or status:

```bash
uv run bucket list --horizon soon
uv run bucket list --status completed --all
```

Sort by rank:

```bash
uv run bucket list --all --ranked
```

### Show one item

```bash
uv run bucket show 1
```

### Edit an item

```bash
uv run bucket edit 1 --title "Hike Grand Canyon rim-to-rim" --horizon now
uv run bucket edit 1 --clear-desc --clear-priority --clear-date
```

### Start, complete, or mark an item no-longer-me

```bash
uv run bucket start 1
uv run bucket done 1
uv run bucket no-longer-me 2
```

### Delete an item

```bash
uv run bucket delete 1 --confirm
```

Without `--confirm`, the CLI prompts before deleting.

### Block and unblock items

Mark an item as waiting on another:

```bash
uv run bucket block 2 --by 1
```

Remove the blocking relationship:

```bash
uv run bucket unblock 2
```

### Tags

Add a tag to an item:

```bash
uv run bucket tag add 1 adventure
```

Remove a tag:

```bash
uv run bucket tag remove 1 adventure
```

List all tags with item counts:

```bash
uv run bucket tags
```

### Notes

Add a note to an item:

```bash
uv run bucket note add 1 "Saw a great deal on flights today"
```

### Search

Search titles and descriptions:

```bash
uv run bucket search "hike"
```

### Stats

Show aggregate statistics and breakdowns:

```bash
uv run bucket stats
```

Output includes total items, actionable items, completion rate, counts by status and horizon, total and actionable ranked/unranked counts, waiting items, dependency-blocked items, and tag counts.

For scripting and agent use:

```bash
uv run bucket --json stats
```

## GTD Review

Run an interactive review for active or in-progress `soon`, `later`, and `waiting` items:

```bash
uv run bucket review
```

For each item, choose whether to keep it, move it to `now`, `soon`, `later`, or `waiting`, mark it done, mark it no-longer-me, skip it, or quit. Mutations are saved after each answer, so progress is preserved if you quit mid-session.

Filter the review scope:

```bash
uv run bucket review --horizon later
uv run bucket review --all
```

GTD review is interactive and does not support global `--json`; use `rank-next` and `rank-answer` for agent-friendly ranking workflows.

## Pairwise Ranking Review

Ranking is separate from `priority`. `priority` is a manual 1–5 field; `rank` is a global ordered list where lower numbers are better.

Start a ranking session:

```bash
uv run bucket review --ranking
```

The CLI asks pairwise questions:

```text
Which would you rather do sooner?

1. Learn scuba diving
2. Visit Japan

Choose [1/2/skip/quit]:
```

Choices:

- `1`: first item ranks higher
- `2`: second item ranks higher
- `skip`: do not rank this comparison; quiz counts are unchanged
- `quit`: exit safely

Rank all currently unranked eligible items:

```bash
uv run bucket review --ranking --until-all-ranked
```

Rank only a filtered section:

```bash
uv run bucket review --ranking --until-all-ranked --horizon now
```

### How ranking works

Ranking is designed to require a small number of meaningful choices, not a long sorting chore.

When you rank a new item, the CLI uses binary search to place it into your existing ranked list. Rather than comparing the new item against every ranked item, you answer roughly `log2(n)` questions. With 16 ranked items, that is about 4 comparisons instead of 16.

By default, the CLI adds a little randomness, or “jitter,” to the comparison choice. Instead of always selecting the exact midpoint, it picks a random item near the midpoint — within about one sixth of the current search range.

That small randomness helps because:

1. **Ranking feels less repetitive.** Without jitter, the same midpoint item tends to appear first every time. With 8 ranked items, for example, strict binary search would repeatedly start around item #4.
2. **More items resurface over time.** Each item tracks `rank_quiz_count`, which records how often it has appeared in ranking prompts. Strict midpoint search overexposes the center of the list and underexposes the edges; jitter spreads those appearances more evenly.
3. **The search still stays efficient.** The jitter is bounded, so it usually adds at most one extra question. In exchange, the review feels more reflective and less mechanical.

The goal is to turn ranking into 4–5 useful judgment calls instead of a predictable sequence of identical-feeling midpoint comparisons.

Use strict midpoint binary search instead of randomized pivots:

```bash
uv run bucket review --ranking --no-randomize
```

Agent-friendly JSON ranking uses non-interactive steps:

```bash
uv run bucket --json rank-next
uv run bucket --json rank-answer --candidate 3 --pivot 1 --winner candidate
```

`rank-next` returns either `{"status":"comparison", "candidate": ..., "pivot": ...}` or `{"status":"ranked", "item": ...}` when no comparison is needed. `rank-answer` accepts `candidate`, `pivot`, or `skip` as `--winner`. Pending comparisons must be answered or skipped before starting a `rank-next` call with different filters.

By default, ranking focuses on unblocked, incomplete items:

- `status` is `active` or `in_progress`
- `horizon` is not `waiting`
- `blocked_by` is empty

Include all items manually:

```bash
uv run bucket review --ranking --all
```

View ranked output:

```bash
uv run bucket list --all --ranked
```

## Shell Completion

Generate and install shell tab completion scripts.

Print a completion script for the current or specified shell:

```bash
uv run bucket completion show
uv run bucket completion show --shell zsh
```

Install completion for the detected shell:

```bash
uv run bucket completion install
```

Install for a specific shell:

```bash
uv run bucket completion install --shell fish
```

Supported shells: `bash`, `zsh`, `fish`. After installing, restart your terminal or source your shell config file.

## Backup and Restore

Create a JSON backup:

```bash
uv run bucket backup --dest ./bucket-backup.json
```

Restore into an empty database:

```bash
uv run bucket --db ./restored.sqlite restore ./bucket-backup.json
```

Restore into a database that already has data:

```bash
uv run bucket --db ./existing.sqlite restore ./bucket-backup.json --confirm
```

`restore` replaces the target database contents, so `--confirm` is required when existing items, tags, or item-tag relationships are present.

Backups currently include items, tags, item-tag relationships, ranks, quiz counts, and timestamps. Restore rejects backups from newer schema versions to avoid silently dropping unsupported future fields.

## JSON Output

Most commands support JSON for scripting. Because `--json` is a global Typer option, place it before the subcommand:

```bash
uv run bucket --json add "Visit Japan" --horizon soon
uv run bucket --json list --all --ranked
uv run bucket --json show 1
```

This works:

```bash
uv run bucket --json list --all
```

This does not:

```bash
uv run bucket list --all --json
```

The schema can be inspected with:

```bash
uv run bucket --json schema
```

## Database Location

Default database path:

```text
~/.config/bucketlist/db.sqlite
```

Override order:

1. `--db <path>` CLI flag
2. `BUCKETLIST_DB` environment variable
3. `db_path` in `~/.config/bucketlist/config.toml`
4. Default path above

Example:

```bash
BUCKETLIST_DB=./bucket.sqlite uv run bucket list --all
```

## Development

Install dependencies:

```bash
uv sync
```

Run tests:

```bash
uv run pytest
```

Run the CLI locally:

```bash
uv run bucket --help
```

Project layout:

```text
bucket/
  main.py          # Typer app entry point
  db.py            # SQLite connection and migrations
  models.py        # Dataclasses and enums
  queries.py       # SQL query helpers
  ranking.py       # Pairwise ranking helpers
  commands/        # CLI command modules
  migrations/      # SQL migrations
tests/             # Unit and CLI integration tests
project-plan.md    # Product and implementation plan
```

## Current Status

Implemented:

- Core CRUD commands
- SQLite migrations
- JSON output and schema introspection
- Rich terminal rendering
- Tags, notes, and blocking commands
- Fuzzy search
- Stats with actionable/rankable breakdowns
- Interactive GTD review
- Pairwise ranking review
- Agent-friendly `rank-next` / `rank-answer`
- `--until-all-ranked`
- JSON backup and restore
- Automated tests

Planned next:

- CSV/Markdown export

## License

This project is licensed under the GNU General Public License v3.0. See [`LICENSE`](./LICENSE) for details.
