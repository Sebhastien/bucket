from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import HORIZONS, Item, Note, STATUSES


def render_items(items: list[Item], console: Console) -> None:
    table = Table(title="Bucket List")
    table.add_column("ID", justify="right")
    table.add_column("Title")
    table.add_column("Horizon")
    table.add_column("Status")
    table.add_column("Priority")
    table.add_column("Rank")
    table.add_column("Blocked by")
    table.add_column("Tags")
    for item in items:
        tags = ", ".join(item.tags) if item.tags else ""
        blocked_by = f"#{item.blocked_by}" if item.blocked_by else ""
        table.add_row(
            str(item.id),
            item.title,
            item.horizon,
            item.status,
            str(item.priority or ""),
            str(item.rank or ""),
            blocked_by,
            tags,
        )
    console.print(table)


def _render_notes(notes: list[Note]) -> str:
    if not notes:
        return "[dim]No notes[/dim]"
    lines = ["[bold]Notes[/bold]"]
    for note in notes:
        lines.append(f"  [{note.created_at}] {note.body}")
    return "\n".join(lines)


def render_stats(data: dict, console: Console) -> None:
    # Summary panel
    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="bold")
    summary.add_column()
    summary.add_row("Total items:", str(data["total_items"]))
    summary.add_row("Actionable items:", str(data["actionable_items"]))
    summary.add_row("Completion rate:", f"{data['completion_rate']:.1%}")
    summary.add_row("Ranked actionable:", str(data["ranked_actionable"]))
    summary.add_row("Unranked actionable:", str(data["unranked_actionable"]))
    summary.add_row("Waiting:", str(data["waiting_items"]))
    summary.add_row("Blocked by dependency:", str(data["blocked"]))
    console.print(Panel(summary, title="Bucket Stats"))

    # Status breakdown
    status_table = Table(title="By Status")
    status_table.add_column("Status")
    status_table.add_column("Count", justify="right")
    for status in STATUSES:
        status_table.add_row(status, str(data["by_status"].get(status, 0)))
    console.print(status_table)

    # Horizon breakdown
    horizon_table = Table(title="By Horizon")
    horizon_table.add_column("Horizon")
    horizon_table.add_column("Count", justify="right")
    for horizon in HORIZONS:
        horizon_table.add_row(horizon, str(data["by_horizon"].get(horizon, 0)))
    console.print(horizon_table)

    # Tag breakdown
    if data["by_tag"]:
        tag_table = Table(title="By Tag")
        tag_table.add_column("Tag")
        tag_table.add_column("Items", justify="right")
        for tag in data["by_tag"]:
            tag_table.add_row(tag["name"], str(tag["count"]))
        console.print(tag_table)


def render_item(item: Item, console: Console, notes: list[Note] | None = None) -> None:
    tags = ", ".join(item.tags) if item.tags else "[dim]none[/dim]"
    blocked = f"#{item.blocked_by}" if item.blocked_by else "[dim]-[/dim]"
    parts = [
        f"[bold]{item.title}[/bold]",
        f"Status: {item.status}",
        f"Horizon: {item.horizon}",
        f"Priority: {item.priority or '-'}",
        f"Target date: {item.target_date or '-'}",
        f"Rank: {item.rank or '-'}",
        f"Ranking quiz appearances: {item.rank_quiz_count}",
        f"Blocked by: {blocked}",
        f"Tags: {tags}",
        "",
        item.description or "[dim]No description[/dim]",
    ]
    if notes is not None:
        parts.extend(["", _render_notes(notes)])
    body = "\n".join(parts)
    console.print(Panel(body, title=f"Item #{item.id}"))
