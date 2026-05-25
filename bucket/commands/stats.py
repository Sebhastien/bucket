from __future__ import annotations

import typer

from bucket import queries
from bucket.display import render_stats
from bucket.main import emit, get_conn


def register(app: typer.Typer) -> None:
    @app.command()
    def stats(ctx: typer.Context) -> None:
        """Show bucket list statistics."""
        with get_conn(ctx) as conn:
            data = queries.get_stats(conn)
        emit(ctx, data, lambda console: render_stats(data, console))
