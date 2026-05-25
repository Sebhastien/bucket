from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .models import HORIZONS, STATUSES, Item


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
    return row_to_item(conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())


def list_items(
    conn: sqlite3.Connection,
    *,
    horizon: str | None = None,
    status: str | None = None,
    all_items: bool = False,
    ranked: bool = False,
) -> list[Item]:
    clauses: list[str] = []
    params: list[object] = []
    if horizon:
        validate_horizon(horizon)
        clauses.append("horizon = ?")
        params.append(horizon)
    elif not all_items:
        clauses.append("horizon = ?")
        params.append("now")
    if status:
        validate_status(status)
        clauses.append("status = ?")
        params.append(status)
    sql = "SELECT * FROM items"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    if ranked:
        sql += " ORDER BY rank IS NULL, rank ASC, COALESCE(priority, 99), created_at DESC, id DESC"
    else:
        sql += " ORDER BY COALESCE(priority, 99), created_at DESC, id DESC"
    return [Item.from_row(row) for row in conn.execute(sql, params).fetchall()]


def update_item(conn: sqlite3.Connection, item_id: int, **changes) -> Item | None:
    allowed = {"title", "description", "horizon", "priority", "target_date"}
    updates = {key: value for key, value in changes.items() if key in allowed and value is not None}
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
            "horizon != 'blocked'",
            "blocked_by IS NULL",
        ])
    return " AND ".join(clauses), params


def get_ranked_items(
    conn: sqlite3.Connection,
    *,
    horizon: str | None = None,
    include_all: bool = False,
) -> list[Item]:
    where, params = ranking_eligibility_sql(horizon=horizon, include_all=include_all)
    clauses = ["rank IS NOT NULL"]
    if where:
        clauses.append(where)
    sql = "SELECT * FROM items WHERE " + " AND ".join(clauses) + " ORDER BY rank ASC"
    return [Item.from_row(row) for row in conn.execute(sql, params).fetchall()]


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
    where, params = ranking_eligibility_sql(horizon=horizon, include_all=include_all)
    clauses = ["rank IS NULL"]
    if where:
        clauses.append(where)
    if excluded:
        placeholders = ", ".join("?" for _ in excluded)
        clauses.append(f"id NOT IN ({placeholders})")
        params.extend(sorted(excluded))
    sql = "SELECT * FROM items WHERE " + " AND ".join(clauses) + " ORDER BY rank_quiz_count ASC, RANDOM() LIMIT 1"
    row = conn.execute(sql, params).fetchone()
    if row:
        return Item.from_row(row), False
    if not allow_rerank:
        return None, False

    where, params = ranking_eligibility_sql(horizon=horizon, include_all=include_all)
    clauses = ["rank IS NOT NULL"]
    if where:
        clauses.append(where)
    if excluded:
        placeholders = ", ".join("?" for _ in excluded)
        clauses.append(f"id NOT IN ({placeholders})")
        params.extend(sorted(excluded))
    sql = "SELECT * FROM items WHERE " + " AND ".join(clauses) + " ORDER BY rank_quiz_count ASC, RANDOM() LIMIT 1"
    row = conn.execute(sql, params).fetchone()
    return (Item.from_row(row), True) if row else (None, False)


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


def target_rank_for_filtered_insert(conn: sqlite3.Connection, ranked_items: list[Item], insertion_index: int) -> int:
    if ranked_items and insertion_index < len(ranked_items):
        assert ranked_items[insertion_index].rank is not None
        return ranked_items[insertion_index].rank
    if ranked_items:
        assert ranked_items[-1].rank is not None
        return ranked_items[-1].rank + 1
    return max_rank(conn) + 1
