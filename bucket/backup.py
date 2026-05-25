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


def restore_database(conn: sqlite3.Connection, payload: dict) -> dict:
    items = payload.get("items", [])
    tags = payload.get("tags", [])
    item_tags = payload.get("item_tags", [])
    with conn:
        conn.execute("DELETE FROM item_tags")
        conn.execute("DELETE FROM tags")
        conn.execute("DELETE FROM items")
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
    return {"items": len(items), "tags": len(tags), "item_tags": len(item_tags)}
