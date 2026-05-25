from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path.home() / ".config" / "bucketlist" / "db.sqlite"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def resolve_db_path(cli_path: str | None = None) -> Path:
    if cli_path:
        return Path(cli_path).expanduser()
    if env_path := os.environ.get("BUCKETLIST_DB"):
        return Path(env_path).expanduser()
    config_path = Path.home() / ".config" / "bucketlist" / "config.toml"
    if config_path.exists():
        import tomllib

        data = tomllib.loads(config_path.read_text())
        if db_path := data.get("db_path"):
            return Path(db_path).expanduser()
    return DEFAULT_DB_PATH


def connect(path: Path | str) -> sqlite3.Connection:
    db_path = Path(path)
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    run_migrations(conn)
    return conn


def run_migrations(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (0)")
        current_version = 0
    else:
        current_version = int(row["version"])

    migrations = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    for migration in migrations:
        version = int(migration.name.split("_", 1)[0])
        if version <= current_version:
            continue
        apply_migration(conn, migration, version)
        current_version = version


def apply_migration(conn: sqlite3.Connection, migration: Path, version: int) -> None:
    """Apply one migration and its version bump in a single SQLite transaction."""
    script = migration.read_text()
    transactional_script = f"""
BEGIN;
{script}
UPDATE schema_version SET version = {version};
COMMIT;
"""
    try:
        conn.executescript(transactional_script)
    except sqlite3.Error:
        if conn.in_transaction:
            conn.rollback()
        raise
