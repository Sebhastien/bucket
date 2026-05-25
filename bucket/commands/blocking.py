from __future__ import annotations

import typer

from bucket import queries
from bucket.display import render_item
from bucket.main import EXIT_CONFLICT, EXIT_NOT_FOUND, emit, fail, get_conn


def register(app: typer.Typer) -> None:
    @app.command()
    def block(
        ctx: typer.Context,
        item_id: int,
        by: int = typer.Option(..., "--by", help="ID of the item that blocks this one."),
    ) -> None:
        """Mark an item as blocked by another item."""
        try:
            with get_conn(ctx) as conn:
                item = queries.block_item(conn, item_id, by)
        except queries.BlockerNotFoundError as exc:
            fail(str(exc), EXIT_NOT_FOUND)
        except ValueError as exc:
            fail(str(exc), EXIT_CONFLICT)
        if item is None:
            fail(f"item not found: {item_id}", EXIT_NOT_FOUND)
        emit(ctx, item.to_dict(), lambda console: render_item(item, console))

    @app.command()
    def unblock(ctx: typer.Context, item_id: int) -> None:
        """Remove the blocked-by relationship from an item."""
        with get_conn(ctx) as conn:
            item = queries.unblock_item(conn, item_id)
        if item is None:
            fail(f"item not found: {item_id}", EXIT_NOT_FOUND)
        emit(ctx, item.to_dict(), lambda console: render_item(item, console))
