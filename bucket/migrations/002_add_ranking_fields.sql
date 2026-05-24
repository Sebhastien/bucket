ALTER TABLE items ADD COLUMN rank INTEGER;
ALTER TABLE items ADD COLUMN rank_quiz_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE items ADD COLUMN ranked_at TEXT;

CREATE INDEX IF NOT EXISTS idx_items_rank ON items(rank);
CREATE INDEX IF NOT EXISTS idx_items_rank_quiz_count ON items(rank_quiz_count);
