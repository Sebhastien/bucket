# AGENTS.md

Guidance for AI agents and maintainers working on this repository.

## Project Summary

Bucket List CLI is a local-first Python command-line application for managing a personal bucket list. It uses:

- Python 3.11+
- Typer for CLI commands
- Rich for human-readable terminal output
- SQLite via the standard-library `sqlite3` module
- `uv` for dependency and environment management

The product plan lives in `project-plan.md`. Keep that document updated when behavior or scope changes.

## Core Commands

Use `uv` for all development commands:

```bash
uv sync
uv run bucket --help
uv run pytest
```

Useful manual smoke tests:

```bash
uv run bucket --db ./test.sqlite add "Visit Japan" --horizon soon
uv run bucket --db ./test.sqlite list --all
uv run bucket --db ./test.sqlite review --ranking --until-all-ranked
uv run bucket --db ./test.sqlite list --all --ranked
```

## Architecture

```text
bucket/
  main.py          # Typer app entry point and global options
  db.py            # SQLite connection setup and migration runner
  models.py        # Dataclasses and enum constants
  queries.py       # SQL query helpers; keep business logic minimal here
  ranking.py       # Pure pairwise-ranking helper logic
  display.py       # Rich rendering helpers
  commands/        # CLI command modules
  migrations/      # Forward-only SQL migrations
tests/             # Unit and CLI integration tests
project-plan.md    # Product and implementation plan
```

## Design Decisions

### Local-first SQLite

The app is intentionally local-only for v1. Do not add cloud sync, accounts, or remote APIs unless the product plan is explicitly updated.

### Raw SQL, no ORM

Use `sqlite3` and explicit SQL. Avoid adding an ORM for the current scope.

### Migrations are forward-only

Add new SQL files under `bucket/migrations/` named like:

```text
003_description.sql
```

Do not edit existing migrations after they have shipped unless the repo is still known to be unreleased and the user explicitly approves.

### JSON is an agent contract

Global `--json` output is intended for scripting and AI-agent use. Preserve stable field names and exit codes.

Stable exit codes:

- `0`: success
- `1`: user/input error
- `2`: not found
- `3`: conflict

### Human output is separate from JSON output

Human-readable output should use Rich via `display.py` where practical. JSON output should emit clean JSON only, with no extra status text.

### Ranking model

Ranking is separate from manual `priority`.

- `priority`: manual 1–5 field
- `rank`: global ordered rank; lower is better
- `rank_quiz_count`: number of pairwise quiz appearances
- `ranked_at`: timestamp of last rank update

Pairwise ranking defaults to eligible unblocked, incomplete items:

```text
status IN ('active', 'in_progress')
horizon != 'blocked'
blocked_by IS NULL
```

`bucket review --ranking --until-all-ranked` should rank unranked eligible items and stop before re-ranking existing ranked items.

## Implementation Guidelines

- Keep changes incremental and covered by tests.
- Prefer simple functions over premature abstractions.
- Keep SQL in `queries.py` unless a command needs a tiny, local query.
- Keep pure algorithmic logic, especially ranking logic, outside CLI command files when possible.
- Do not introduce new dependencies without a clear reason and user approval.
- Do not break existing CLI flags or JSON field names without updating docs and tests.
- Update `README.md` for user-facing behavior changes.
- Update `project-plan.md` for product or architectural decisions.

## Testing Expectations

Add or update tests for behavior changes:

- `tests/test_queries.py` for database/query behavior
- `tests/test_commands.py` for Typer CLI behavior and JSON contracts
- `tests/test_ranking.py` for pure ranking algorithm behavior

Before finishing any code change, run:

```bash
uv run pytest
```

## Git Hygiene

Commit focused changes with descriptive messages. Avoid committing:

- `.venv/`
- SQLite database files
- Python caches
- build artifacts
- coverage artifacts

Check status before finishing:

```bash
git status --short
```
