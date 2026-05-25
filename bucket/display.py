from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import Item


def render_items(items: list[Item], console: Console) -> None:
    table = Table(title="Bucket List")
    table.add_column("ID", justify="right")
    table.add_column("Title")
    table.add_column("Horizon")
    table.add_column("Status")
    table.add_column("Priority")
    table.add_column("Rank")
    table.add_column("Tags")
    for item in items:
        tags = ", ".join(item.tags) if item.tags else ""
        table.add_row(
            str(item.id),
            item.title,
            item.horizon,
            item.status,
            str(item.priority or ""),
            str(item.rank or ""),
            tags,
        )
    console.print(table)


def render_item(item: Item, console: Console) -> None:
    tags = ", ".join(item.tags) if item.tags else "[dim]none[/dim]"
    body = "\n".join(
        [
            f"[bold]{item.title}[/bold]",
            f"Status: {item.status}",
            f"Horizon: {item.horizon}",
            f"Priority: {item.priority or '-'}",
            f"Target date: {item.target_date or '-'}",
            f"Rank: {item.rank or '-'}",
            f"Ranking quiz appearances: {item.rank_quiz_count}",
            f"Tags: {tags}",
            "",
            item.description or "[dim]No description[/dim]",
        ]
    )
    console.print(Panel(body, title=f"Item #{item.id}"))
