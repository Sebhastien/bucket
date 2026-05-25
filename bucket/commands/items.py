from __future__ import annotations

import typer

from bucket import queries
from bucket.display import render_item, render_items
from bucket.main import EXIT_NOT_FOUND, EXIT_USER_ERROR, emit, fail, get_conn


def register(app: typer.Typer) -> None:
    @app.command()
    def add(
        ctx: typer.Context,
        title: str,
        horizon: str = typer.Option("now", "--horizon"),
        desc: str | None = typer.Option(None, "--desc"),
        priority: int | None = typer.Option(None, "--priority"),
        date: str | None = typer.Option(None, "--date"),
        tag: list[str] = typer.Option([], "--tag"),
    ) -> None:
        """Add a bucket list item."""
        try:
            with get_conn(ctx) as conn:
                item = queries.create_item(
                    conn,
                    title=title,
                    description=desc,
                    horizon=horizon,
                    priority=priority,
                    target_date=date,
                )
                for t in tag:
                    queries.add_tag_to_item(conn, item.id, t)
                item = queries.get_item(conn, item.id)
                assert item is not None
        except ValueError as exc:
            fail(str(exc))
        emit(ctx, item.to_dict(), lambda console: render_item(item, console))

    @app.command("list")
    def list_command(
        ctx: typer.Context,
        horizon: str | None = typer.Option(None, "--horizon"),
        status: str | None = typer.Option(None, "--status"),
        tag: str | None = typer.Option(None, "--tag"),
        all_items: bool = typer.Option(False, "--all"),
        ranked: bool = typer.Option(False, "--ranked", help="Sort by global rank."),
    ) -> None:
        """List items. Defaults to horizon=now unless --all is used."""
        try:
            with get_conn(ctx) as conn:
                items = queries.list_items(
                    conn, horizon=horizon, status=status, tag=tag, all_items=all_items, ranked=ranked
                )
        except ValueError as exc:
            fail(str(exc))
        emit(ctx, [item.to_dict() for item in items], lambda console: render_items(items, console))

    @app.command()
    def show(ctx: typer.Context, item_id: int) -> None:
        """Show one item."""
        with get_conn(ctx) as conn:
            item = queries.get_item(conn, item_id)
        if item is None:
            fail(f"item not found: {item_id}", EXIT_NOT_FOUND)
        emit(ctx, item.to_dict(), lambda console: render_item(item, console))

    @app.command()
    def edit(
        ctx: typer.Context,
        item_id: int,
        title: str | None = typer.Option(None, "--title"),
        horizon: str | None = typer.Option(None, "--horizon"),
        desc: str | None = typer.Option(None, "--desc"),
        priority: int | None = typer.Option(None, "--priority"),
        date: str | None = typer.Option(None, "--date"),
    ) -> None:
        """Edit item fields."""
        try:
            with get_conn(ctx) as conn:
                item = queries.update_item(
                    conn,
                    item_id,
                    title=title,
                    horizon=horizon,
                    description=desc,
                    priority=priority,
                    target_date=date,
                )
        except ValueError as exc:
            fail(str(exc))
        if item is None:
            fail(f"item not found: {item_id}", EXIT_NOT_FOUND)
        emit(ctx, item.to_dict(), lambda console: render_item(item, console))

    @app.command()
    def start(ctx: typer.Context, item_id: int) -> None:
        """Mark an item in progress."""
        with get_conn(ctx) as conn:
            item = queries.set_status(conn, item_id, "in_progress")
        if item is None:
            fail(f"item not found: {item_id}", EXIT_NOT_FOUND)
        emit(ctx, item.to_dict(), lambda console: render_item(item, console))

    @app.command()
    def done(
        ctx: typer.Context,
        item_id: int,
        force: bool = typer.Option(False, "--force", help="Override if item is blocked."),
    ) -> None:
        """Mark an item completed."""
        with get_conn(ctx) as conn:
            item = queries.get_item(conn, item_id)
            if item is None:
                fail(f"item not found: {item_id}", EXIT_NOT_FOUND)
            if item.blocked_by is not None and not force:
                fail(f"item is blocked by #{item.blocked_by}; use --force to override", EXIT_USER_ERROR)
            item = queries.set_status(conn, item_id, "completed")
        emit(ctx, item.to_dict(), lambda console: render_item(item, console))

    @app.command()
    def abandon(ctx: typer.Context, item_id: int) -> None:
        """Mark an item abandoned."""
        with get_conn(ctx) as conn:
            item = queries.set_status(conn, item_id, "abandoned")
        if item is None:
            fail(f"item not found: {item_id}", EXIT_NOT_FOUND)
        emit(ctx, item.to_dict(), lambda console: render_item(item, console))

    @app.command()
    def delete(
        ctx: typer.Context,
        item_id: int,
        confirm: bool = typer.Option(False, "--confirm"),
    ) -> None:
        """Delete an item."""
        with get_conn(ctx) as conn:
            item = queries.get_item(conn, item_id)
            if item is None:
                fail(f"item not found: {item_id}", EXIT_NOT_FOUND)
            if not confirm and not typer.confirm(f"Delete '{item.title}'?"):
                raise typer.Exit(1)
            deleted = queries.delete_item(conn, item_id)
        assert deleted is not None
        emit(ctx, deleted.to_dict(), lambda console: console.print(f"Deleted item #{deleted.id}: {deleted.title}"))

    @app.command()
    def search(ctx: typer.Context, query: str) -> None:
        """Search items by title or description."""
        with get_conn(ctx) as conn:
            items = queries.search_items(conn, query)
        emit(ctx, [item.to_dict() for item in items], lambda console: render_items(items, console))
