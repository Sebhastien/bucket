from __future__ import annotations

from dataclasses import dataclass, field

HORIZONS = ("now", "soon", "someday", "blocked")
STATUSES = ("active", "in_progress", "completed", "abandoned")


@dataclass(frozen=True)
class Item:
    id: int
    title: str
    description: str | None
    status: str
    horizon: str
    blocked_by: int | None
    category: str | None
    priority: int | None
    target_date: str | None
    completed_at: str | None
    created_at: str
    updated_at: str
    rank: int | None
    rank_quiz_count: int
    ranked_at: str | None
    tags: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_row(cls, row) -> "Item":
        d = dict(row)
        if "tags" in d:
            val = d["tags"]
            d["tags"] = () if val is None else tuple(sorted(val.split(",")))
        return cls(**d)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "horizon": self.horizon,
            "blocked_by": self.blocked_by,
            "category": self.category,
            "priority": self.priority,
            "target_date": self.target_date,
            "completed_at": self.completed_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "rank": self.rank,
            "rank_quiz_count": self.rank_quiz_count,
            "ranked_at": self.ranked_at,
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class Tag:
    id: int
    name: str
    item_count: int = 0

    @classmethod
    def from_row(cls, row) -> "Tag":
        return cls(**dict(row))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "item_count": self.item_count,
        }
