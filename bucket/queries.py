from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .models import HORIZONS, STATUSES, Item, Note, Tag


class BlockerNotFoundError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_horizon(horizon: str) -> None:
    if horizon not in HORIZONS:
        raise ValueError(f"horizon must be one of: {', '.join(HORIZONS)}")


def validate_status(status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"status must be one of: {', '.join(STATUSES)}")


def validate_priority(priority: int | None) -> None:
    if priority is not None and not 1 <= priority <= 5:
        raise ValueError("priority must be between 1 and 5")


def row_to_item(row) -> Item | None:
    return Item.from_row(row) if row else None


def create_item(
    conn: sqlite3.Connection,
    *,
    title: str,
    description: str | None = None,
    horizon: str = "now",
    priority: int | None = None,
    target_date: str | None = None,
) -> Item:
    if not title.strip():
        raise ValueError("title is required")
    validate_horizon(horizon)
    validate_priority(priority)
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO items (title, description, horizon, priority, target_date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title.strip(), description, horizon, priority, target_date),
        )
    item = get_item(conn, cursor.lastrowid)
    assert item is not None
    return item


def get_item(conn: sqlite3.Connection, item_id: int) -> Item | None:
    row = conn.execute(
        """
        SELECT i.*, GROUP_CONCAT(t.name) as tags
        FROM items i
        LEFT JOIN item_tags it ON it.item_id = i.id
        LEFT JOIN tags t ON t.id = it.tag_id
        WHERE i.id = ?
        GROUP BY i.id
        """,
        (item_id,),
    ).fetchone()
    return row_to_item(row)


def list_items(
    conn: sqlite3.Connection,
    *,
    horizon: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    all_items: bool = False,
    ranked: bool = False,
) -> list[Item]:
    clauses: list[str] = []
    params: list[object] = []
    if horizon:
        validate_horizon(horizon)
        clauses.append("i.horizon = ?")
        params.append(horizon)
    elif not all_items:
        clauses.append("i.horizon = ?")
        params.append("now")
    if status:
        validate_status(status)
        clauses.append("i.status = ?")
        params.append(status)
    elif not all_items:
        clauses.append("i.status IN ('active', 'in_progress')")
    if tag:
        clauses.append(
            "EXISTS (SELECT 1 FROM item_tags it2 JOIN tags t2 ON t2.id = it2.tag_id WHERE it2.item_id = i.id AND t2.name = ?)"
        )
        params.append(tag.strip().lower())
    where = " AND ".join(clauses) if clauses else "1"
    order = (
        "rank IS NULL, rank ASC, COALESCE(priority, 99), created_at DESC, i.id DESC"
        if ranked
        else "COALESCE(priority, 99), created_at DESC, i.id DESC"
    )
    sql = f"""
        SELECT i.*, GROUP_CONCAT(t.name) as tags
        FROM items i
        LEFT JOIN item_tags it ON it.item_id = i.id
        LEFT JOIN tags t ON t.id = it.tag_id
        WHERE {where}
        GROUP BY i.id
        ORDER BY {order}
    """
    return [Item.from_row(row) for row in conn.execute(sql, params).fetchall()]


def get_review_items(
    conn: sqlite3.Connection,
    *,
    horizon: str | None = None,
    include_all: bool = False,
) -> list[Item]:
    """Return items eligible for GTD review.

    Defaults to active/in_progress items with horizon soon, later, or waiting.
    If horizon is provided, filter to that horizon only.
    """
    if horizon:
        validate_horizon(horizon)
        horizons = [horizon]
    else:
        horizons = ["soon", "later", "waiting"]

    placeholders = ", ".join("?" for _ in horizons)
    clauses: list[str] = [f"i.horizon IN ({placeholders})"]
    params: list[object] = list(horizons)

    if not include_all:
        clauses.append("i.status IN ('active', 'in_progress')")

    where = " AND ".join(clauses)
    sql = f"""
        SELECT i.*, GROUP_CONCAT(t.name) as tags
        FROM items i
        LEFT JOIN item_tags it ON it.item_id = i.id
        LEFT JOIN tags t ON t.id = it.tag_id
        WHERE {where}
        GROUP BY i.id
        ORDER BY CASE i.horizon
                     WHEN 'now' THEN 0
                     WHEN 'soon' THEN 1
                     WHEN 'later' THEN 2
                     WHEN 'waiting' THEN 3
                     ELSE 4
                   END,
                 COALESCE(i.priority, 99), i.created_at DESC, i.id DESC
    """
    return [Item.from_row(row) for row in conn.execute(sql, params).fetchall()]


def update_item(
    conn: sqlite3.Connection,
    item_id: int,
    *,
    clear_fields: set[str] | None = None,
    **changes,
) -> Item | None:
    allowed = {"title", "description", "horizon", "priority", "target_date"}
    nullable = {"description", "priority", "target_date"}
    clear_fields = clear_fields or set()
    unknown_clear_fields = clear_fields - nullable
    if unknown_clear_fields:
        raise ValueError(f"cannot clear fields: {', '.join(sorted(unknown_clear_fields))}")

    updates = {key: value for key, value in changes.items() if key in allowed and value is not None}
    conflicts = clear_fields & updates.keys()
    if conflicts:
        raise ValueError(f"cannot set and clear fields: {', '.join(sorted(conflicts))}")
    updates.update({field: None for field in clear_fields})

    if not updates:
        return get_item(conn, item_id)
    if "title" in updates and not str(updates["title"]).strip():
        raise ValueError("title is required")
    if "horizon" in updates:
        validate_horizon(str(updates["horizon"]))
    if "priority" in updates:
        validate_priority(updates["priority"])
    assignments = ", ".join(f"{column} = ?" for column in updates)
    params = list(updates.values()) + [item_id]
    with conn:
        result = conn.execute(f"UPDATE items SET {assignments} WHERE id = ?", params)
    if result.rowcount == 0:
        return None
    return get_item(conn, item_id)


def set_status(conn: sqlite3.Connection, item_id: int, status: str) -> Item | None:
    validate_status(status)
    completed_at = utc_now() if status == "completed" else None
    with conn:
        result = conn.execute(
            "UPDATE items SET status = ?, completed_at = ? WHERE id = ?",
            (status, completed_at, item_id),
        )
    if result.rowcount == 0:
        return None
    return get_item(conn, item_id)


def delete_item(conn: sqlite3.Connection, item_id: int) -> Item | None:
    item = get_item(conn, item_id)
    if item is None:
        return None
    with conn:
        conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    return item


def ranking_eligibility_sql(*, horizon: str | None = None, include_all: bool = False) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if horizon:
        validate_horizon(horizon)
        clauses.append("horizon = ?")
        params.append(horizon)
    if not include_all:
        clauses.extend([
            "status IN ('active', 'in_progress')",
            "horizon != 'waiting'",
            "blocked_by IS NULL",
        ])
    return " AND ".join(clauses), params


def _items_with_tags_sql(where: str, order: str) -> str:
    return f"""
        SELECT i.*, GROUP_CONCAT(t.name) as tags
        FROM items i
        LEFT JOIN item_tags it ON it.item_id = i.id
        LEFT JOIN tags t ON t.id = it.tag_id
        WHERE {where}
        GROUP BY i.id
        ORDER BY {order}
    """


def get_ranked_items(
    conn: sqlite3.Connection,
    *,
    horizon: str | None = None,
    include_all: bool = False,
) -> list[Item]:
    where, params = ranking_eligibility_sql(horizon=horizon, include_all=include_all)
    clauses = ["i.rank IS NOT NULL"]
    if where:
        clauses.append(f"i.id IN (SELECT id FROM items WHERE {where})")
    sql = _items_with_tags_sql(" AND ".join(clauses), "i.rank ASC")
    return [Item.from_row(row) for row in conn.execute(sql, params).fetchall()]


def _ranking_candidate_by_rank_state(
    conn: sqlite3.Connection,
    *,
    rank_is_null: bool,
    horizon: str | None,
    include_all: bool,
    excluded: set[int],
) -> Item | None:
    where, params = ranking_eligibility_sql(horizon=horizon, include_all=include_all)
    clauses = ["rank IS NULL" if rank_is_null else "rank IS NOT NULL"]
    if where:
        clauses.append(where)
    if excluded:
        placeholders = ", ".join("?" for _ in excluded)
        clauses.append(f"id NOT IN ({placeholders})")
        params.extend(sorted(excluded))
    sql = "SELECT id FROM items WHERE " + " AND ".join(clauses) + " ORDER BY rank_quiz_count ASC, RANDOM() LIMIT 1"
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    return get_item(conn, int(row["id"]))


def choose_ranking_candidate(
    conn: sqlite3.Connection,
    *,
    horizon: str | None = None,
    include_all: bool = False,
    allow_rerank: bool = True,
    exclude_item_ids: set[int] | None = None,
) -> tuple[Item | None, bool]:
    """Return (candidate, is_rerank). Unranked eligible items are preferred."""
    excluded = exclude_item_ids or set()
    candidate = _ranking_candidate_by_rank_state(
        conn,
        rank_is_null=True,
        horizon=horizon,
        include_all=include_all,
        excluded=excluded,
    )
    if candidate is not None:
        return candidate, False
    if not allow_rerank:
        return None, False

    candidate = _ranking_candidate_by_rank_state(
        conn,
        rank_is_null=False,
        horizon=horizon,
        include_all=include_all,
        excluded=excluded,
    )
    return (candidate, True) if candidate is not None else (None, False)


def increment_rank_quiz_counts(conn: sqlite3.Connection, item_ids: list[int]) -> None:
    if not item_ids:
        return
    placeholders = ", ".join("?" for _ in item_ids)
    with conn:
        conn.execute(
            f"UPDATE items SET rank_quiz_count = rank_quiz_count + 1 WHERE id IN ({placeholders})",
            item_ids,
        )


@contextmanager
def immediate_transaction(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise


def remove_item_from_ranking(conn: sqlite3.Connection, item_id: int) -> Item | None:
    with immediate_transaction(conn):
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            return None
        item = Item.from_row(row)
        if item.rank is None:
            return item
        conn.execute("UPDATE items SET rank = NULL, ranked_at = NULL WHERE id = ?", (item_id,))
        conn.execute("UPDATE items SET rank = rank - 1 WHERE rank > ?", (item.rank,))
    return get_item(conn, item_id)


def max_rank(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(rank), 0) AS max_rank FROM items").fetchone()
    return int(row["max_rank"])


def insert_item_at_rank(conn: sqlite3.Connection, item_id: int, target_rank: int) -> Item | None:
    with immediate_transaction(conn):
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            return None
        item = Item.from_row(row)
        if item.rank is not None:
            conn.execute("UPDATE items SET rank = NULL, ranked_at = NULL WHERE id = ?", (item_id,))
            conn.execute("UPDATE items SET rank = rank - 1 WHERE rank > ?", (item.rank,))
        row = conn.execute("SELECT COALESCE(MAX(rank), 0) AS max_rank FROM items").fetchone()
        target_rank = max(1, min(target_rank, int(row["max_rank"]) + 1))
        conn.execute("UPDATE items SET rank = rank + 1 WHERE rank >= ?", (target_rank,))
        conn.execute(
            "UPDATE items SET rank = ?, ranked_at = ? WHERE id = ?",
            (target_rank, utc_now(), item_id),
        )
    return get_item(conn, item_id)


def detect_circular_dependency(conn: sqlite3.Connection, item_id: int, blocked_by_id: int) -> bool:
    """Return True if setting item.blocked_by = blocked_by_id would create a cycle."""
    visited: set[int] = set()
    current: int | None = blocked_by_id
    while current is not None:
        if current == item_id:
            return True
        if current in visited:
            return True
        visited.add(current)
        row = conn.execute("SELECT blocked_by FROM items WHERE id = ?", (current,)).fetchone()
        current = row["blocked_by"] if row else None
    return False


def block_item(conn: sqlite3.Connection, item_id: int, blocked_by_id: int) -> Item | None:
    if item_id == blocked_by_id:
        raise ValueError("an item cannot block itself")
    item = get_item(conn, item_id)
    if item is None:
        return None
    blocker = get_item(conn, blocked_by_id)
    if blocker is None:
        raise BlockerNotFoundError("blocker not found")
    if detect_circular_dependency(conn, item_id, blocked_by_id):
        raise ValueError("circular dependency detected")
    with conn:
        conn.execute(
            "UPDATE items SET blocked_by = ?, horizon = 'waiting' WHERE id = ?",
            (blocked_by_id, item_id),
        )
    return get_item(conn, item_id)


def unblock_item(conn: sqlite3.Connection, item_id: int) -> Item | None:
    item = get_item(conn, item_id)
    if item is None:
        return None
    with conn:
        conn.execute(
            "UPDATE items SET blocked_by = NULL WHERE id = ?",
            (item_id,),
        )
    return get_item(conn, item_id)


def target_rank_for_filtered_insert(conn: sqlite3.Connection, ranked_items: list[Item], insertion_index: int) -> int:
    if ranked_items and insertion_index < len(ranked_items):
        assert ranked_items[insertion_index].rank is not None
        return ranked_items[insertion_index].rank
    if ranked_items:
        assert ranked_items[-1].rank is not None
        return ranked_items[-1].rank + 1
    return max_rank(conn) + 1


def get_ranking_session(conn: sqlite3.Connection, candidate_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM ranking_sessions WHERE candidate_id = ?", (candidate_id,)).fetchone()


def get_any_ranking_session(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM ranking_sessions ORDER BY updated_at DESC, candidate_id LIMIT 1").fetchone()


def save_ranking_session(
    conn: sqlite3.Connection,
    *,
    candidate_id: int,
    low: int,
    high: int,
    pivot_id: int | None,
    pivot_index: int | None,
    horizon: str | None,
    include_all: bool,
    randomize: bool,
) -> None:
    if horizon:
        validate_horizon(horizon)
    with conn:
        conn.execute(
            """
            INSERT INTO ranking_sessions (
                candidate_id, low, high, pivot_id, pivot_index, horizon, include_all, randomize
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_id) DO UPDATE SET
                low = excluded.low,
                high = excluded.high,
                pivot_id = excluded.pivot_id,
                pivot_index = excluded.pivot_index,
                horizon = excluded.horizon,
                include_all = excluded.include_all,
                randomize = excluded.randomize
            """,
            (candidate_id, low, high, pivot_id, pivot_index, horizon, int(include_all), int(randomize)),
        )


def delete_ranking_session(conn: sqlite3.Connection, candidate_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM ranking_sessions WHERE candidate_id = ?", (candidate_id,))


def _normalize_tag_name(tag_name: str) -> str:
    name = tag_name.strip().lower()
    if not name:
        raise ValueError("tag name is required")
    if "," in name:
        raise ValueError("tag name cannot contain a comma")
    return name


def add_tag_to_item(conn: sqlite3.Connection, item_id: int, tag_name: str) -> Item | None:
    name = _normalize_tag_name(tag_name)
    item = get_item(conn, item_id)
    if item is None:
        return None
    with conn:
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
        row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
        assert row is not None
        tag_id = row["id"]
        conn.execute("INSERT OR IGNORE INTO item_tags (item_id, tag_id) VALUES (?, ?)", (item_id, tag_id))
    return get_item(conn, item_id)


def remove_tag_from_item(conn: sqlite3.Connection, item_id: int, tag_name: str) -> Item | None:
    name = _normalize_tag_name(tag_name)
    item = get_item(conn, item_id)
    if item is None:
        return None
    with conn:
        row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
        if row is None:
            return item
        tag_id = row["id"]
        conn.execute("DELETE FROM item_tags WHERE item_id = ? AND tag_id = ?", (item_id, tag_id))
        count = conn.execute("SELECT COUNT(*) FROM item_tags WHERE tag_id = ?", (tag_id,)).fetchone()[0]
        if count == 0:
            conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    return get_item(conn, item_id)


def list_tags(conn: sqlite3.Connection) -> list[Tag]:
    rows = conn.execute(
        """
        SELECT t.id, t.name, COUNT(it.item_id) as item_count
        FROM tags t
        LEFT JOIN item_tags it ON it.tag_id = t.id
        GROUP BY t.id, t.name
        ORDER BY t.name
        """
    ).fetchall()
    return [Tag.from_row(row) for row in rows]


def _escape_like_pattern(query: str) -> str:
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def add_note(conn: sqlite3.Connection, item_id: int, body: str) -> Note | None:
    if not body.strip():
        raise ValueError("note body is required")
    item = get_item(conn, item_id)
    if item is None:
        return None
    with conn:
        cursor = conn.execute(
            "INSERT INTO notes (item_id, body, created_at) VALUES (?, ?, ?)",
            (item_id, body.strip(), utc_now()),
        )
    row = conn.execute("SELECT * FROM notes WHERE id = ?", (cursor.lastrowid,)).fetchone()
    assert row is not None
    return Note.from_row(row)


def get_notes_for_item(conn: sqlite3.Connection, item_id: int) -> list[Note]:
    rows = conn.execute(
        "SELECT * FROM notes WHERE item_id = ? ORDER BY created_at DESC, id DESC", (item_id,)
    ).fetchall()
    return [Note.from_row(row) for row in rows]


def get_note_by_id(conn: sqlite3.Connection, note_id: int) -> Note | None:
    row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    return Note.from_row(row) if row else None


def delete_note(conn: sqlite3.Connection, note_id: int) -> Note | None:
    note = get_note_by_id(conn, note_id)
    if note is None:
        return None
    with conn:
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    return note


def get_stats(conn: sqlite3.Connection) -> dict:
    total_row = conn.execute("SELECT COUNT(*) FROM items").fetchone()
    total = int(total_row[0])

    by_status: dict[str, int] = {s: 0 for s in STATUSES}
    for row in conn.execute("SELECT status, COUNT(*) as c FROM items GROUP BY status").fetchall():
        by_status[row["status"]] = int(row["c"])

    by_horizon: dict[str, int] = {h: 0 for h in HORIZONS}
    for row in conn.execute("SELECT horizon, COUNT(*) as c FROM items GROUP BY horizon").fetchall():
        by_horizon[row["horizon"]] = int(row["c"])

    ranked_row = conn.execute("SELECT COUNT(*) FROM items WHERE rank IS NOT NULL").fetchone()
    ranked_total = int(ranked_row[0])

    actionable_where, actionable_params = ranking_eligibility_sql(include_all=False)
    actionable_row = conn.execute(f"SELECT COUNT(*) FROM items WHERE {actionable_where}", actionable_params).fetchone()
    actionable_items = int(actionable_row[0])
    ranked_actionable_row = conn.execute(
        f"SELECT COUNT(*) FROM items WHERE rank IS NOT NULL AND {actionable_where}", actionable_params
    ).fetchone()
    ranked_actionable = int(ranked_actionable_row[0])

    blocked_row = conn.execute("SELECT COUNT(*) FROM items WHERE blocked_by IS NOT NULL").fetchone()
    blocked = int(blocked_row[0])

    tags = [
        {"name": row["name"], "count": int(row["c"])}
        for row in conn.execute(
            """
            SELECT t.name, COUNT(it.item_id) as c
            FROM tags t
            LEFT JOIN item_tags it ON it.tag_id = t.id
            GROUP BY t.id, t.name
            ORDER BY t.name
            """
        ).fetchall()
    ]

    completed = by_status.get("completed", 0)
    completion_rate = round(completed / total, 4) if total else 0.0

    # `total`, `ranked`, and `unranked` are backwards-compatible aliases.
    # Prefer the explicit `*_items` / `*_total` / `*_actionable` keys in new callers.
    return {
        "total": total,
        "total_items": total,
        "actionable_items": actionable_items,
        "by_status": by_status,
        "by_horizon": by_horizon,
        "completion_rate": completion_rate,
        "ranked": ranked_total,
        "unranked": total - ranked_total,
        "ranked_total": ranked_total,
        "unranked_total": total - ranked_total,
        "ranked_actionable": ranked_actionable,
        "unranked_actionable": actionable_items - ranked_actionable,
        "blocked": blocked,
        "waiting_items": by_horizon.get("waiting", 0),
        "completed_items": by_status.get("completed", 0),
        "no_longer_me_items": by_status.get("no_longer_me", 0),
        "by_tag": tags,
    }


def search_items(conn: sqlite3.Connection, query: str) -> list[Item]:
    escaped = _escape_like_pattern(query)
    pattern = f"%{escaped}%"
    rows = conn.execute(
        """
        SELECT i.*, GROUP_CONCAT(t.name) as tags
        FROM items i
        LEFT JOIN item_tags it ON it.item_id = i.id
        LEFT JOIN tags t ON t.id = it.tag_id
        WHERE i.title LIKE ? ESCAPE '\\' OR i.description LIKE ? ESCAPE '\\'
        GROUP BY i.id
        ORDER BY COALESCE(priority, 99), created_at DESC, i.id DESC
        """,
        (pattern, pattern),
    ).fetchall()
    return [Item.from_row(row) for row in rows]
