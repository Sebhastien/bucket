# Backlog

Known issues, technical debt, and planned features for the Bucket List CLI.

## Technical Debt

### Error routing in `blocking.py` uses substring matching
`blocking.py` dispatches error messages to exit codes by checking substrings (`"circular" in msg`, `"blocker" in msg`, `"itself" in msg`). This is pragmatic for the current scope but brittle if error messages change. If more error variants are added, switch to typed exceptions (e.g., `class CircularDependencyError(ValueError)`).

### `Item.from_row()` has a dual contract for the `tags` field
When `from_row` is called on a row that includes the `GROUP_CONCAT(...)` column aliased as `tags`, it parses and sorts the comma-separated string. When called on a plain `SELECT * FROM items` row (e.g., ranking queries), `tags` is absent and defaults to `()`. This works but means `tags` has a different data contract than all other fields.

### Ranking queries don't populate tags
`get_ranked_items` and `choose_ranking_candidate` use `SELECT * FROM items` without joining tags, so returned items always have empty `tags` tuples. Not a bug today since ranking sessions only use titles, but a gap if we ever want to display tag info during ranking.

## Pending Features

### Stats (`bucket stats`)
Completion rate, breakdown by horizon/status/tag. High agent value with `--json`.

### Interactive GTD review (non-ranking)
Phase 4: a structured loop for reviewing `someday` items with prompt-driven horizon updates.

### Shell tab completion
`bucket completion install` via Typer's built-in completion support.

### README with full command reference
Document the agent contract (`--json`, exit codes) and human command surface.
