CREATE TABLE IF NOT EXISTS ranking_sessions (
  candidate_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
  low INTEGER NOT NULL,
  high INTEGER NOT NULL,
  pivot_id INTEGER REFERENCES items(id) ON DELETE CASCADE,
  pivot_index INTEGER,
  horizon TEXT CHECK (horizon IS NULL OR horizon IN ('now', 'soon', 'later', 'waiting')),
  include_all INTEGER NOT NULL DEFAULT 0,
  randomize INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS ranking_sessions_updated_at
AFTER UPDATE ON ranking_sessions
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
  UPDATE ranking_sessions SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE candidate_id = OLD.candidate_id;
END;
