# Bucket List CLI

SQLite-backed CLI for managing a personal bucket list.

## Development

```bash
uv sync
uv run bucket --help
uv run pytest
```

## Example

```bash
uv run bucket --db ./bucket.sqlite add "Hike the Grand Canyon" --horizon soon --json
uv run bucket --db ./bucket.sqlite list --all
uv run bucket --db ./bucket.sqlite review --ranking
uv run bucket --db ./bucket.sqlite review --ranking --until-all-ranked
uv run bucket --db ./bucket.sqlite list --all --ranked
```
