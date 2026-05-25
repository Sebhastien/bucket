from __future__ import annotations

import typer

from bucket import queries
from bucket.display import render_item
from bucket.main import EXIT_NOT_FOUND, emit, fail, get_conn


def register(app: typer.Typer) -> None:
    tag_app = typer.Typer()

    @tag_app.command("add")
    def tag_add(
        ctx: typer.Context,
        item_id: int,
        tag_name: str,
    ) -> None:
        """Add a tag to an item."""
        try:
            with get_conn(ctx) as conn:
                item = queries.add_tag_to_item(conn, item_id, tag_name)
        except ValueError as exc:
            fail(str(exc))
        if item is None:
            fail(f"item not found: {item_id}", EXIT_NOT_FOUND)
        emit(ctx, item.to_dict(), lambda console: render_item(item, console))

    @tag_app.command("remove")
    def tag_remove(
        ctx: typer.Context,
        item_id: int,
        tag_name: str,
    ) -> None:
        """Remove a tag from an item."""
        with get_conn(ctx) as conn:
            item = queries.remove_tag_from_item(conn, item_id, tag_name)
        if item is None:
            fail(f"item not found: {item_id}", EXIT_NOT_FOUND)
        emit(ctx, item.to_dict(), lambda console: render_item(item, console))

    app.add_typer(tag_app, name="tag")

    @app.command("tags")
    def tags_list(ctx: typer.Context) -> None:
        """List all tags with item counts."""
        with get_conn(ctx) as conn:
            tags = queries.list_tags(conn)

        def render(console) -> None:
            from rich.table import Table

            table = Table(title="Tags")
            table.add_column("Tag")
            table.add_column("Items", justify="right")
            for tag in tags:
                table.add_row(tag.name, str(tag.item_count))
            console.print(table)

        emit(ctx, [tag.to_dict() for tag in tags], render)
