"""SQLite storage. Every entry query is scoped by user_id in the SQL itself,
so one user can never read or change another user's entries through here."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    kind       TEXT NOT NULL,          -- 'web', 'cli' or 'api'
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entry_date TEXT NOT NULL,          -- the writer's local calendar day, YYYY-MM-DD
    created_at TEXT NOT NULL,          -- UTC timestamp
    updated_at TEXT,
    title      TEXT,
    place      TEXT,
    text       TEXT NOT NULL,
    prompt     TEXT,
    sentiment  TEXT NOT NULL,
    polarity   REAL NOT NULL,
    emotions   TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_entries_user_date ON entries (user_id, entry_date);

-- Tags group entries into collections, like a trip ("morocco") or a part of
-- life ("school"). They belong to a user through their entry.
CREATE TABLE IF NOT EXISTS entry_tags (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    tag      TEXT NOT NULL,
    PRIMARY KEY (entry_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_entry_tags_tag ON entry_tags (tag);
"""


def data_dir() -> Path:
    path = Path(os.getenv("CALMCONNECT_DATA_DIR", PROJECT_ROOT / "data"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    # DB_PATH is still honoured so older .env files keep working.
    path = Path(os.getenv("DB_PATH") or data_dir() / "journal.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _move_legacy_table(conn):
    """The first version stored user_id as free text with no accounts. Keep
    those rows in legacy_entries so they can be imported into an account
    instead of being dropped."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(entries)")}
    if "date" in columns and "entry_date" not in columns:
        conn.execute("ALTER TABLE entries RENAME TO legacy_entries")


@contextmanager
def get_db():
    """Yield a connection that commits on success and rolls back on error."""
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        # Cheap to repeat: everything in SCHEMA is "IF NOT EXISTS".
        _move_legacy_table(conn)
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _to_entry(row) -> dict:
    entry = dict(row)
    entry["emotions"] = [e for e in entry["emotions"].split(",") if e]
    return entry


# --- users and tokens -------------------------------------------------------

def create_user(username: str, password_hash: str, created_at: str) -> int | None:
    """Insert a user and return the new id, or None if the name is taken."""
    try:
        with get_db() as conn:
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, created_at),
            )
            return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None


def get_user_by_username(username: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None


def save_token(user_id: int, token_hash: str, kind: str, created_at: str, expires_at: str):
    with get_db() as conn:
        conn.execute("DELETE FROM auth_tokens WHERE expires_at <= ?", (created_at,))
        conn.execute(
            "INSERT INTO auth_tokens (user_id, token_hash, kind, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, token_hash, kind, created_at, expires_at),
        )


def get_user_for_token(token_hash: str, now: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT users.id, users.username FROM auth_tokens "
            "JOIN users ON users.id = auth_tokens.user_id "
            "WHERE auth_tokens.token_hash = ? AND auth_tokens.expires_at > ?",
            (token_hash, now),
        ).fetchone()
        return dict(row) if row else None


def delete_token(token_hash: str):
    with get_db() as conn:
        conn.execute("DELETE FROM auth_tokens WHERE token_hash = ?", (token_hash,))


# --- entries ----------------------------------------------------------------

# Columns that callers are allowed to change with update_entry().
EDITABLE_COLUMNS = ("entry_date", "title", "place", "text", "sentiment", "polarity", "emotions")


def _attach_tags(conn, entries: list[dict]) -> list[dict]:
    """Load tags for a batch of entries with one query instead of one per entry."""
    by_id = {entry["id"]: entry for entry in entries}
    for entry in entries:
        entry["tags"] = []
    if by_id:
        placeholders = ",".join("?" * len(by_id))
        rows = conn.execute(
            f"SELECT entry_id, tag FROM entry_tags WHERE entry_id IN ({placeholders}) "
            "ORDER BY tag",
            list(by_id),
        )
        for row in rows:
            by_id[row["entry_id"]]["tags"].append(row["tag"])
    return entries


def _replace_tags(conn, entry_id: int, tags: list[str]):
    conn.execute("DELETE FROM entry_tags WHERE entry_id = ?", (entry_id,))
    conn.executemany(
        "INSERT INTO entry_tags (entry_id, tag) VALUES (?, ?)",
        [(entry_id, tag) for tag in tags],
    )


def insert_entry(user_id: int, entry: dict) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO entries (user_id, entry_date, created_at, title, place, text, "
            "prompt, sentiment, polarity, emotions) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                entry["entry_date"],
                entry["created_at"],
                entry.get("title"),
                entry.get("place"),
                entry["text"],
                entry.get("prompt"),
                entry["sentiment"],
                entry["polarity"],
                ",".join(entry["emotions"]),
            ),
        )
        _replace_tags(conn, cursor.lastrowid, entry.get("tags", []))
        return cursor.lastrowid


def get_entry(user_id: int, entry_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM entries WHERE id = ? AND user_id = ?", (entry_id, user_id)
        ).fetchone()
        return _attach_tags(conn, [_to_entry(row)])[0] if row else None


def update_entry(user_id: int, entry_id: int, changes: dict, updated_at: str,
                 tags: list[str] | None = None) -> bool:
    """Apply `changes` (column -> value) and, if given, replace the tags.
    Returns False if the entry doesn't exist or belongs to someone else."""
    unknown = set(changes) - set(EDITABLE_COLUMNS)
    if unknown:
        raise ValueError(f"Can't update columns: {sorted(unknown)}")
    changes = {**changes, "updated_at": updated_at}
    if "emotions" in changes:
        changes["emotions"] = ",".join(changes["emotions"])
    # Column names come from the whitelist above, never from user input.
    assignments = ", ".join(f"{column} = ?" for column in changes)

    with get_db() as conn:
        cursor = conn.execute(
            f"UPDATE entries SET {assignments} WHERE id = ? AND user_id = ?",
            [*changes.values(), entry_id, user_id],
        )
        if cursor.rowcount != 1:
            return False
        if tags is not None:
            _replace_tags(conn, entry_id, tags)
        return True


def delete_entry(user_id: int, entry_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM entries WHERE id = ? AND user_id = ?", (entry_id, user_id)
        )
        return cursor.rowcount == 1


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_entries(user_id: int, search: str | None = None, tag: str | None = None,
                 date_from: str | None = None, date_to: str | None = None,
                 oldest_first: bool = False, limit: int | None = None,
                 offset: int = 0) -> list[dict]:
    """Filter a user's entries. Dates are inclusive YYYY-MM-DD strings and the
    search matches the title, place or text, ignoring case."""
    sql = "SELECT * FROM entries WHERE user_id = ?"
    params: list = [user_id]
    if search:
        pattern = f"%{_escape_like(search)}%"
        sql += (" AND (text LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\'"
                " OR place LIKE ? ESCAPE '\\')")
        params.extend([pattern] * 3)
    if tag:
        sql += " AND id IN (SELECT entry_id FROM entry_tags WHERE tag = ?)"
        params.append(tag)
    if date_from:
        sql += " AND entry_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND entry_date <= ?"
        params.append(date_to)
    direction = "ASC" if oldest_first else "DESC"
    sql += f" ORDER BY entry_date {direction}, created_at {direction}, id {direction}"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    with get_db() as conn:
        return _attach_tags(conn, [_to_entry(row) for row in conn.execute(sql, params)])


def list_tags(user_id: int) -> list[dict]:
    """Each tag the user has used, with how many entries and the dates they span."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT entry_tags.tag, COUNT(*) AS entries, "
            "MIN(entries.entry_date) AS first_date, MAX(entries.entry_date) AS last_date "
            "FROM entry_tags JOIN entries ON entries.id = entry_tags.entry_id "
            "WHERE entries.user_id = ? GROUP BY entry_tags.tag "
            "ORDER BY last_date DESC, entry_tags.tag",
            (user_id,),
        )
        return [dict(row) for row in rows]


def get_entry_dates(user_id: int) -> list[str]:
    """Distinct days the user wrote on, oldest first."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT entry_date FROM entries WHERE user_id = ? ORDER BY entry_date",
            (user_id,),
        )
        return [row["entry_date"] for row in rows]


# --- importing data from the first version ----------------------------------

def get_legacy_entries(legacy_name: str) -> list[dict]:
    with get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'legacy_entries'"
        ).fetchone()
        if not exists:
            return []
        rows = conn.execute(
            "SELECT * FROM legacy_entries WHERE user_id = ? ORDER BY date, id",
            (legacy_name,),
        )
        return [dict(row) for row in rows]


def move_legacy_entries(user_id: int, legacy_name: str, entries: list[dict]) -> int:
    """Insert already-analysed entries and remove the legacy rows, atomically."""
    with get_db() as conn:
        for entry in entries:
            conn.execute(
                "INSERT INTO entries (user_id, entry_date, created_at, text, "
                "sentiment, polarity, emotions) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    entry["entry_date"],
                    entry["created_at"],
                    entry["text"],
                    entry["sentiment"],
                    entry["polarity"],
                    ",".join(entry["emotions"]),
                ),
            )
        conn.execute("DELETE FROM legacy_entries WHERE user_id = ?", (legacy_name,))
    return len(entries)
