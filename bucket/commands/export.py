from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from bucket import backup
from bucket.main import emit, fail, get_conn


def register(app: typer.Typer) -> None:
    @app.command("backup")
    def backup_command(
        ctx: typer.Context,
        dest: Path | None = typer.Option(None, "--dest", help="Backup JSON destination path."),
    ) -> None:
        """Write a JSON backup of the database."""
        path = dest or Path(f"bucket-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
        with get_conn(ctx) as conn:
            payload = backup.dump_database(conn)
        backup.write_backup_file(payload, path)
        emit(ctx, {"path": str(path), "items": len(payload["items"])}, lambda console: console.print(str(path)))

    @app.command()
    def restore(
        ctx: typer.Context,
        file: Path,
        confirm: bool = typer.Option(False, "--confirm", help="Confirm replacement of existing database contents."),
    ) -> None:
        """Restore a JSON backup into the current database."""
        payload = backup.load_backup_file(file)
        with get_conn(ctx) as conn:
            try:
                backup.validate_backup_schema(conn, payload)
            except ValueError as exc:
                fail(str(exc))
            if backup.has_existing_data(conn) and not confirm:
                fail("restore would replace existing data; rerun with --confirm to proceed")
            result = backup.restore_database(conn, payload)
        emit(ctx, result, lambda console: console.print(f"Restored {result['items']} item(s)."))
