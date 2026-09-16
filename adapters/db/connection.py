import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".local" / "share" / "diffr" / "diffr.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    id          TEXT PRIMARY KEY,
    repo_path   TEXT NOT NULL,
    branch      TEXT NOT NULL,
    base_branch TEXT NOT NULL DEFAULT 'main',
    status      TEXT NOT NULL DEFAULT 'in_progress',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS comments (
    id          TEXT PRIMARY KEY,
    review_id   TEXT NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    file_path   TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    side        TEXT NOT NULL DEFAULT 'right',
    body        TEXT NOT NULL,
    author      TEXT NOT NULL DEFAULT 'user',
    resolved    INTEGER NOT NULL DEFAULT 0,
    processed   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reactions (
    id          TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    review_id   TEXT NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    emoji       TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(target_type, target_id, emoji, review_id)
);

CREATE INDEX IF NOT EXISTS idx_comments_review ON comments(review_id, file_path);
CREATE INDEX IF NOT EXISTS idx_reactions_target ON reactions(target_type, target_id);

CREATE TABLE IF NOT EXISTS stacks (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    repo_path   TEXT NOT NULL,
    branches    TEXT NOT NULL DEFAULT '[]',
    sidecars    TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_stacks_repo ON stacks(repo_path);
"""


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(comments)").fetchall()}
    if "author" not in cols:
        conn.execute(
            "ALTER TABLE comments ADD COLUMN author TEXT NOT NULL DEFAULT 'user'"
        )
    if "processed" not in cols:
        conn.execute(
            "ALTER TABLE comments ADD COLUMN processed INTEGER NOT NULL DEFAULT 0"
        )
    if "parent_id" not in cols:
        conn.execute(
            "ALTER TABLE comments ADD COLUMN parent_id TEXT DEFAULT NULL"
        )
    stack_cols = {row[1] for row in conn.execute("PRAGMA table_info(stacks)").fetchall()}
    if stack_cols and "sidecars" not in stack_cols:
        conn.execute(
            "ALTER TABLE stacks ADD COLUMN sidecars TEXT NOT NULL DEFAULT '{}'"
        )
