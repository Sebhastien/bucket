PRAGMA defer_foreign_keys = ON;

DROP TRIGGER IF EXISTS items_updated_at;

ALTER TABLE items RENAME TO items_old;

CREATE TABLE items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'in_progress', 'completed', 'no_longer_me')),
  horizon TEXT NOT NULL DEFAULT 'now' CHECK (horizon IN ('now', 'soon', 'later', 'waiting')),
  blocked_by INTEGER REFERENCES items(id) ON DELETE SET NULL,
  category TEXT,
  priority INTEGER CHECK (priority IS NULL OR (priority >= 1 AND priority <= 5)),
  target_date TEXT,
  completed_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  rank INTEGER,
  rank_quiz_count INTEGER NOT NULL DEFAULT 0,
  ranked_at TEXT
);

INSERT INTO items (
  id, title, description, status, horizon, blocked_by, category, priority,
  target_date, completed_at, created_at, updated_at, rank, rank_quiz_count, ranked_at
)
SELECT
  id,
  title,
  description,
  CASE status
    WHEN 'abandoned' THEN 'no_longer_me'
    ELSE status
  END,
  CASE horizon
    WHEN 'someday' THEN 'later'
    WHEN 'blocked' THEN 'waiting'
    ELSE horizon
  END,
  blocked_by,
  category,
  priority,
  target_date,
  completed_at,
  created_at,
  updated_at,
  rank,
  rank_quiz_count,
  ranked_at
FROM items_old;

CREATE TABLE item_tags_new (
  item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, tag_id)
);
INSERT INTO item_tags_new (item_id, tag_id) SELECT item_id, tag_id FROM item_tags;
DROP TABLE item_tags;
ALTER TABLE item_tags_new RENAME TO item_tags;

CREATE TABLE notes_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL
);
INSERT INTO notes_new (id, item_id, body, created_at) SELECT id, item_id, body, created_at FROM notes;
DROP TABLE notes;
ALTER TABLE notes_new RENAME TO notes;

DROP TABLE items_old;

CREATE INDEX IF NOT EXISTS idx_items_rank ON items(rank);
CREATE INDEX IF NOT EXISTS idx_items_rank_quiz_count ON items(rank_quiz_count);

CREATE TRIGGER items_updated_at
AFTER UPDATE ON items
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
  UPDATE items SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = OLD.id;
END;
