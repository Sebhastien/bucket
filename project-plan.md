# Bucket List CLI Tool — Project Plan

## Overview

A command-line tool for managing a personal bucket list backed by a local SQLite database. Supports full CRUD operations, horizon-based prioritization, item dependencies (blocked-by relationships), tagging, and rich terminal output. Designed for daily personal use with a clean, composable command surface.

---

## Goals & Scope

### In Scope

- Create, read, update, delete bucket list items via CLI
- Horizon system: `now`, `soon`, `later`, `waiting`
- Dependency tracking: items can be blocked by other items (self-referencing FK)
- Tagging for flexible categorization
- Rich terminal output (colored tables, item detail views)
- SQLite local database with migration support
- Shell tab completion
- Export to CSV and Markdown
- Backup command

### Out of Scope (v1)

- Cloud sync or remote database
- Recurring items
- GUI or TUI (terminal UI with mouse support)
- Multi-user support

---

## Data Model

### `items` Table

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `title` | TEXT NOT NULL | Short name of the item |
| `description` | TEXT | Optional longer description |
| `status` | TEXT | `active`, `in_progress`, `completed`, `no_longer_me` |
| `horizon` | TEXT | `now`, `soon`, `later`, `waiting` |
| `blocked_by` | INTEGER FK | Self-reference to `items.id`, nullable |
| `category` | TEXT | Optional free-text category |
| `priority` | INTEGER | 1–5 scale, nullable |
| `target_date` | TEXT | ISO date string, nullable |
| `completed_at` | TEXT | ISO datetime, set on completion |
| `created_at` | TEXT | ISO datetime, auto-set on insert |
| `updated_at` | TEXT | ISO datetime, auto-updated |

### `tags` Table

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `name` | TEXT UNIQUE NOT NULL | Lowercase, slug-friendly |

### `item_tags` Table (Join)

| Column | Type | Notes |
|--------|------|-------|
| `item_id` | INTEGER FK | References `items.id` |
| `tag_id` | INTEGER FK | References `tags.id` |

### `notes` Table

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `item_id` | INTEGER FK | References `items.id` |
| `body` | TEXT NOT NULL | Free-text note content |
| `created_at` | TEXT | ISO datetime |

### `schema_version` Table

Single-row table storing the current schema version integer. Used by the migration system to determine which migrations to apply on startup.

---

## Schema Design Decisions

### Horizon vs. Status — Two Orthogonal Axes

These are intentionally separate columns, not a single combined field.

- **Horizon** answers "when do I intend to act on this?" (`now`, `soon`, `later`, `waiting`)
- **Status** answers "what is the lifecycle state?" (`active`, `in_progress`, `completed`, `no_longer_me`)

This allows meaningful combinations like: `horizon=now, status=in_progress` (actively working on it now) or `horizon=later, status=active` (want to do it, no immediate timeline).

### Blocked-By as Self-Referencing FK

`blocked_by` stores the `id` of the item that must be completed first. This enables dependency chains. Key decisions:

- `horizon` should be auto-set to `waiting` when `blocked_by` is populated, but dependency blocking remains separate from the user-facing waiting horizon.
- On delete of a blocking item: **nullify** the `blocked_by` field on dependent items (not cascade delete). This is the safest default — the item still exists, it just becomes unblocked.
- Circular dependency detection must be enforced at the application layer (SQLite does not enforce this natively).

---

## Command Surface

```
bucket add "<title>" [--horizon now|soon|later|waiting] [--desc "..."] [--tag adventure] [--priority 3] [--date 2027-01-01]
bucket list [--horizon now|soon|later|waiting] [--tag <name>] [--status active|completed|no_longer_me] [--all]
bucket show <id>
bucket edit <id> [--title "..."] [--horizon ...] [--desc "..."] [--priority ...] [--date ...] [--clear-desc] [--clear-priority] [--clear-date]
bucket start <id>
bucket done <id>
bucket no-longer-me <id>
bucket delete <id> [--confirm]
bucket block <id> --by <blocking-id>
bucket unblock <id>
bucket note <id> "<note text>"
bucket tag add <id> <tag>
bucket tag remove <id> <tag>
bucket tags                          # list all tags and item counts
bucket search "<query>"              # fuzzy title/description search
bucket review                        # interactive GTD-style review of soon/later/waiting items
bucket rank-next                     # JSON-friendly next ranking comparison
bucket rank-answer --candidate <id> --pivot <id> --winner candidate|pivot|skip
bucket stats                         # completion rate, breakdown by horizon/tag
bucket export [--format csv|markdown]
bucket backup [--dest <path>]
bucket completion install            # install shell tab completion
```

### Flags Available Globally

- `--db <path>` — override the database file location
- `--no-color` — disable rich terminal color output
- `--json` — output results as JSON (useful for scripting)

---

## Technical Stack

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Language | Python 3.11+ | Existing expertise, rich ecosystem |
| CLI framework | Typer | Clean subcommand API, auto `--help`, built-in tab completion |
| Terminal output | `rich` | Tables, panels, color, progress bars |
| Database layer | `sqlite3` (stdlib) + raw SQL | Simple, no ORM overhead for this scope |
| Migrations | Custom version table + migration files | Lightweight, no Alembic dependency |
| Config | `tomllib` (stdlib 3.11+) | Read `~/.config/bucketlist/config.toml` |
| Packaging | `pyproject.toml` with `[project.scripts]` | Installs `bucket` as a global command via `pip install -e .` |

### Dependency Summary

```toml
[project]
dependencies = [
  "typer>=0.12",
  "rich>=13",
]
```

No ORM, no heavy dependencies. The `sqlite3` module handles all DB work.

---

## Project Structure

```
bucketlist-cli/
├── pyproject.toml
├── README.md
├── bucket/
│   ├── __init__.py
│   ├── main.py          # Typer app entry point, subcommand registration
│   ├── db.py            # Connection management, PRAGMA setup, migration runner
│   ├── models.py        # Dataclasses for Item, Tag, Note
│   ├── queries.py       # All SQL query functions (no business logic)
│   ├── commands/
│   │   ├── items.py     # add, list, show, edit, done, no-longer-me, delete
│   │   ├── blocking.py  # block, unblock
│   │   ├── tags.py      # tag add/remove, tags list
│   │   ├── notes.py     # note
│   │   ├── review.py    # interactive review session
│   │   ├── stats.py     # stats
│   │   └── export.py    # export, backup
│   ├── display.py       # rich-based rendering (tables, item detail panels)
│   └── migrations/
│       ├── 001_initial_schema.sql
│       └── 002_add_notes_table.sql
└── tests/
    ├── test_queries.py
    └── test_commands.py
```

---

## SQLite Configuration

Applied on every connection open via `db.py`:

```python
conn.execute("PRAGMA journal_mode=WAL;")      # better concurrent access
conn.execute("PRAGMA foreign_keys=ON;")        # enforce FK constraints
conn.execute("PRAGMA synchronous=NORMAL;")     # safe + faster than FULL
```

### Database Location

Default: `~/.config/bucketlist/db.sqlite`

Overridable via:
1. `--db <path>` CLI flag (highest priority)
2. `BUCKETLIST_DB` environment variable
3. `db_path` key in `~/.config/bucketlist/config.toml`
4. Default path (lowest priority)

---

## Migration System

On every startup, `db.py` runs the migration runner:

1. Create `schema_version` table if it doesn't exist (version = 0)
2. Read current version from the table
3. Scan `migrations/` for `.sql` files named `NNN_description.sql`
4. Apply any files with `NNN > current_version` in order
5. Update `schema_version` after each successful migration

This is intentionally simple — no down-migrations, no branching. Only additive changes.

---

## Edge Cases & Decisions

| Scenario | Decision |
|----------|----------|
| Delete an item that blocks others | Nullify `blocked_by` on dependents; do not cascade delete |
| Re-open a completed item | Allowed — set `status=active`, clear `completed_at`, preserve `horizon` |
| `block` without `--by` | Rejected with a clear error — dependency blocking requires a blocker item |
| Circular dependency (A blocks B blocks A) | Detected at application layer before write; rejected with error |
| `done` on an item with `blocked_by` | Warn user that item is waiting on another; require `--force` to override |
| Missing `--confirm` on delete | Interactive prompt: "Delete 'Hike the Grand Canyon'? [y/N]" |
| `bucket list` with no filters | Show actionable `horizon=now` items (`active`, `in_progress`) by default; use `--all` for everything |
| Pairwise ranking default pool | Focus on unblocked, incomplete items: `status IN ('active', 'in_progress')`, `horizon != 'waiting'`, and `blocked_by IS NULL` |
| Ranking scope | Ranking is global, but review sessions can filter to a horizon section |
| Skipped ranking comparison | Do not increment quiz counters and do not change rank |

---

## Pairwise Ranking Review

The CLI supports a pairwise ranking mode through:

```bash
bucket review --ranking
bucket review --ranking --horizon now
bucket review --ranking --limit 5
bucket review --ranking --until-all-ranked
bucket review --ranking --no-randomize
```

Ranking is a separate global ordering from the manual `priority` field. Lower `rank` values are better: rank `1` is the item the user cares about most / would rather do sooner. Sessions can be filtered by horizon so the user can rank within a section without constantly comparing `now` items against `later` items.

### Ranking Data

The `items` table includes:

| Column | Type | Notes |
|--------|------|-------|
| `rank` | INTEGER | Nullable global rank; lower is higher-ranked |
| `rank_quiz_count` | INTEGER | Number of pairwise quiz prompts this item appeared in |
| `ranked_at` | TEXT | ISO datetime when rank was last updated |

### Ranking Algorithm

1. Prefer eligible unranked items: `rank IS NULL` ordered by `rank_quiz_count ASC, RANDOM()`.
2. If no eligible unranked items exist, choose an eligible ranked item with the lowest `rank_quiz_count`, temporarily remove it from the ranked list, and reinsert it.
3. Insert candidates using binary-search-style pairwise comparisons against the current ranked list.
4. By default, choose a pivot near the midpoint with mild randomization; `--no-randomize` uses the strict midpoint.
5. Continue until the insertion point is known, then shift affected ranks and save the candidate rank.

Prompt format:

```text
Which would you rather do sooner?

1. Candidate item
2. Existing ranked item

Choose [1/2/skip/quit]:
```

A valid `1` or `2` answer increments `rank_quiz_count` for both displayed items. `skip` leaves counts and ranks unchanged for that comparison and moves on to another candidate in the current session. `quit` exits safely without inserting the current candidate.

`--until-all-ranked` keeps selecting unranked eligible items until none remain, then stops before re-ranking existing items. It can be combined with filters such as `--horizon now`.

---

## Build Phases

Agent use is the primary concern, so the agent-facing surface (`--json`, stable exit codes, JSON backup/restore) is built into the foundation rather than bolted on later. Human-facing polish (rich tables, interactive review, tab completion) comes after the agent contract is solid.

### Phase 1 — Agent-Ready Core CRUD (Week 1)

- [ ] `pyproject.toml` and project skeleton
- [ ] `db.py`: connection, PRAGMAs, migration runner
- [ ] `001_initial_schema.sql`: items + tags + item_tags tables
- [ ] `queries.py`: insert, select, update, delete for items
- [ ] `commands/items.py`: `add`, `list`, `show`, `edit`, `delete`, `start`, `done`, `no-longer-me`
- [ ] **`--json` global flag wired from day one** — every read command emits JSON; every mutation returns the resulting object as JSON
- [ ] **Stable exit codes**: 0 success, 1 user error, 2 not found, 3 conflict (e.g. circular dep)
- [ ] **`bucket schema --json`**: dumps data model + enum values (`horizon`, `status`) so agents can introspect
- [ ] `display.py`: basic rich table and item detail panel (human mode only)
- [ ] Integration tests via Typer `CliRunner` covering the JSON contract

### Phase 2 — Backup, Restore & Agent Workflows (Week 2)

- [ ] `commands/export.py`: **`backup`** — JSON by default, round-trips tags/notes/blocked_by/timestamps, includes `schema_version`
- [ ] Cron-friendly defaults: dated filenames, atomic write (tmp + rename), silent on success, non-zero exit on failure, `--keep N` rotation
- [ ] **`bucket restore <file>`** — inverse of backup; the backup is worthless without this
- [ ] `commands/export.py`: CSV and Markdown export (lossy, human-facing)
- [ ] Round-trip test: `backup` → fresh DB → `restore` → diff equals original
- [ ] Document cron recipe in README

### Phase 3 — Blocking, Tags & Notes (Week 3)

- [ ] `queries.py`: blocking queries, tag queries
- [ ] `commands/blocking.py`: `block`, `unblock` with circular dependency detection (exit code 3)
- [ ] `commands/tags.py`: `tag`, `untag`, `tags` (flat verbs to match `block`/`unblock`)
- [ ] `--tag`, `--horizon waiting`, and `--status no_longer_me` filters on `bucket list`
- [ ] `002_add_notes_table.sql` migration
- [ ] `commands/notes.py`: `note`
- [ ] `commands/items.py`: `search` with `LIKE` query
- [ ] Extend backup/restore to cover notes and tag relationships

### Phase 3.5 — Pairwise Ranking Review

- [ ] `002_add_ranking_fields.sql`: add `rank`, `rank_quiz_count`, `ranked_at`
- [ ] `queries.py`: ranking candidate selection, quiz count increments, rank insertion/reordering
- [ ] `ranking.py`: pure binary-search pivot and bounds helpers, including randomized midpoint selection
- [ ] `commands/review.py`: `bucket review --ranking` interactive pairwise quiz, including `--until-all-ranked`
- [ ] `bucket list --ranked`: show/sort by global rank while preserving JSON fields
- [ ] Tests for unranked-first selection, skipped comparisons, least-quizzed fallback, rank shifting, and CLI flow

### Phase 4 — Human Polish (Week 4)

- [x] `commands/review.py`: interactive GTD review loop
- [ ] `commands/stats.py`: completion rate, breakdown tables (`--json` supported)
- [x] Shell tab completion (`bucket completion install`)
- [ ] `--no-color` flag wired to rich console
- [ ] README with full command reference and agent-usage section

---

## Testing Strategy

- **Unit tests** (`tests/test_queries.py`): test all SQL query functions against an in-memory SQLite database (`":memory:"`)
- **Integration tests** (`tests/test_commands.py`): use Typer's `CliRunner` to invoke commands end-to-end against a temp file database
- **Edge case coverage**: circular dependency detection, nullify-on-delete behavior, re-open completed items, waiting/dependency item `done` with and without `--force`

---

## Future Enhancements (Post-v1)

- `bucket sync` — sync database file to a configured path (Dropbox, iCloud Drive, network share)
- Recurring items with a `recurrence` field and auto-reset on completion
- `bucket review --weekly` — structured weekly review mode with prompt-driven horizon updates
- TUI mode using `textual` for an interactive list browser
- `bucket import` — import from a CSV or Markdown checklist file
