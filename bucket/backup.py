from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from tempfile import NamedTemporaryFile

ITEM_COLUMNS = (
    "id",
    "title",
    "description",
    "status",
    "horizon",
    "blocked_by",
    "category",
    "priority",
    "target_date",
    "completed_at",
    "created_at",
    "updated_at",
    "rank",
    "rank_quiz_count",
    "ranked_at",
)
TAG_COLUMNS = ("id", "name")
ITEM_TAG_COLUMNS = ("item_id", "tag_id")
NOTE_COLUMNS = ("id", "item_id", "body", "created_at")


def dump_database(conn: sqlite3.Connection) -> dict:
    version = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()["version"]
    return {
        "schema_version": version,
        "items": [dict(row) for row in conn.execute("SELECT * FROM items ORDER BY id").fetchall()],
        "tags": [dict(row) for row in conn.execute("SELECT * FROM tags ORDER BY id").fetchall()],
        "item_tags": [
            dict(row)
            for row in conn.execute("SELECT item_id, tag_id FROM item_tags ORDER BY item_id, tag_id").fetchall()
        ],
        "notes": [dict(row) for row in conn.execute("SELECT * FROM notes ORDER BY id").fetchall()],
    }


def write_backup_file(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        json.dump(payload, tmp, indent=2)
        tmp.write("\n")
        temp_path = Path(tmp.name)
    temp_path.replace(path)


def load_backup_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def current_schema_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()["version"])


def has_existing_data(conn: sqlite3.Connection) -> bool:
    tables = ("items", "tags", "item_tags", "notes")
    return any(conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is not None for table in tables)


def validate_backup_schema(conn: sqlite3.Connection, payload: dict) -> None:
    backup_version = int(payload.get("schema_version", 0))
    current_version = current_schema_version(conn)
    if backup_version > current_version:
        raise ValueError(
            f"backup uses newer schema version {backup_version}; current database is version {current_version}"
        )


def restore_database(conn: sqlite3.Connection, payload: dict) -> dict:
    items = payload.get("items", [])
    tags = payload.get("tags", [])
    item_tags = payload.get("item_tags", [])
    notes = payload.get("notes", [])
    has_notes_in_backup = "notes" in payload
    with conn:
        conn.execute("DELETE FROM item_tags")
        if has_notes_in_backup:
            conn.execute("DELETE FROM notes")
        conn.execute("DELETE FROM tags")
        conn.execute("DELETE FROM items")
        seq_tables = ["items", "tags"]
        if has_notes_in_backup:
            seq_tables.append("notes")
        conn.execute(f"DELETE FROM sqlite_sequence WHERE name IN ({', '.join(repr(t) for t in seq_tables)})")
        for item in items:
            values = [item.get(column) for column in ITEM_COLUMNS]
            placeholders = ", ".join("?" for _ in ITEM_COLUMNS)
            conn.execute(
                f"INSERT INTO items ({', '.join(ITEM_COLUMNS)}) VALUES ({placeholders})",
                values,
            )
        for tag in tags:
            conn.execute("INSERT INTO tags (id, name) VALUES (?, ?)", [tag.get(column) for column in TAG_COLUMNS])
        for item_tag in item_tags:
            conn.execute(
                "INSERT INTO item_tags (item_id, tag_id) VALUES (?, ?)",
                [item_tag.get(column) for column in ITEM_TAG_COLUMNS],
            )
        for note in notes:
            conn.execute(
                f"INSERT INTO notes ({', '.join(NOTE_COLUMNS)}) VALUES ({', '.join('?' for _ in NOTE_COLUMNS)})",
                [note.get(column) for column in NOTE_COLUMNS],
            )
    return {"items": len(items), "tags": len(tags), "item_tags": len(item_tags), "notes": len(notes)}
