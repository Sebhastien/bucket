from __future__ import annotations

import typer

from bucket import queries
from bucket.main import EXIT_NOT_FOUND, emit, fail, get_conn


def register(app: typer.Typer) -> None:
    @app.command()
    def note(
        ctx: typer.Context,
        item_id: int,
        body: list[str] = typer.Argument(..., help="Note text."),
    ) -> None:
        """Add a note to an item."""
        text = " ".join(body)
        try:
            with get_conn(ctx) as conn:
                note = queries.add_note(conn, item_id, text)
        except ValueError as exc:
            fail(str(exc))
        if note is None:
            fail(f"item not found: {item_id}", EXIT_NOT_FOUND)
        emit(ctx, note.to_dict(), lambda console: console.print(f"Note added to item #{item_id}."))
