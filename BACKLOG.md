# Backlog

Known issues, technical debt, and planned features for the Bucket List CLI.

## Technical Debt

### `Item.from_row()` has a dual contract for the `tags` field
When `from_row` is called on a row that includes the `GROUP_CONCAT(...)` column aliased as `tags`, it parses and sorts the comma-separated string. When called on a plain `SELECT * FROM items` row (e.g., ranking queries), `tags` is absent and defaults to `()`. This works but means `tags` has a different data contract than all other fields.

### Ranking queries don't populate tags
`get_ranked_items` and `choose_ranking_candidate` use `SELECT * FROM items` without joining tags, so returned items always have empty `tags` tuples. Not a bug today since ranking sessions only use titles, but a gap if we ever want to display tag info during ranking.

### Tighten GTD review output assertion
`test_review_gtd_mutations_persist` currently checks `"Reviewed 2 item(s)" in result.output`. That could pass if the string appears elsewhere. Prefer `assert result.output.count("Reviewed 2 item(s)") == 1` for a slightly more precise assertion.

## Pending Features

### Stats (`bucket stats`)
Completion rate, breakdown by horizon/status/tag. High agent value with `--json`.

### Shell tab completion
`bucket completion install` via Typer's built-in completion support.

### README with full command reference
Document the agent contract (`--json`, exit codes) and human command surface.
