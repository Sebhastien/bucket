from __future__ import annotations

import json
from typing import Any

import typer
from rich.console import Console

from . import db
from .models import HORIZONS, STATUSES

app = typer.Typer(no_args_is_help=True)

EXIT_USER_ERROR = 1
EXIT_NOT_FOUND = 2
EXIT_CONFLICT = 3


@app.callback()
def main(
    ctx: typer.Context,
    db_path: str | None = typer.Option(None, "--db", help="Override database file location."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable color output."),
) -> None:
    ctx.obj = {
        "db_path": db.resolve_db_path(db_path),
        "json": json_output,
        "console": Console(no_color=no_color),
    }


def get_conn(ctx: typer.Context):
    return db.connect(ctx.obj["db_path"])


def emit(ctx: typer.Context, payload: Any, human_renderer=None) -> None:
    if ctx.obj["json"]:
        typer.echo(json.dumps(payload, default=str))
    elif human_renderer:
        human_renderer(ctx.obj["console"])
    else:
        ctx.obj["console"].print(payload)


def fail(message: str, code: int = EXIT_USER_ERROR) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(code)


@app.command()
def schema(ctx: typer.Context) -> None:
    """Dump the agent-readable data model and enum values."""
    emit(
        ctx,
        {
            "tables": {
                "items": {
                    "id": "integer primary key",
                    "title": "text required",
                    "description": "text nullable",
                    "status": list(STATUSES),
                    "horizon": list(HORIZONS),
                    "blocked_by": "integer nullable self-reference",
                    "category": "text nullable",
                    "priority": "integer nullable 1..5",
                    "target_date": "ISO date string nullable",
                    "completed_at": "ISO datetime nullable",
                    "created_at": "ISO datetime",
                    "updated_at": "ISO datetime",
                    "rank": "integer nullable global rank; lower is higher",
                    "rank_quiz_count": "integer count of pairwise quiz appearances",
                    "ranked_at": "ISO datetime nullable",
                },
                "tags": {"id": "integer primary key", "name": "unique text"},
                "item_tags": {"item_id": "integer", "tag_id": "integer"},
            },
            "exit_codes": {"success": 0, "user_error": 1, "not_found": 2, "conflict": 3},
        },
    )


from .commands import export, items, review, tags  # noqa: E402

items.register(app)
review.register(app)
export.register(app)
tags.register(app)
