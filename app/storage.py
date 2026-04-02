import sqlite3
import os
from contextlib import contextmanager


def _db_path():
    path = os.getenv("DB_PATH", "data/journal.db")
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path


@contextmanager
def get_db():
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                date TEXT NOT NULL,
                text TEXT NOT NULL,
                mood TEXT NOT NULL,
                polarity REAL NOT NULL,
                emotions TEXT DEFAULT ''
            )
        """)
        conn.commit()


def save_entry(entry):
    init_db()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO entries (user_id, date, text, mood, polarity, emotions) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                entry["user_id"],
                entry["date"],
                entry["text"],
                entry["mood"],
                entry["polarity"],
                entry.get("emotions", ""),
            ),
        )
        conn.commit()


def get_user_entries(user_id, limit=None):
    init_db()
    with get_db() as conn:
        if limit:
            rows = conn.execute(
                "SELECT * FROM entries WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM entries WHERE user_id = ? ORDER BY date DESC, id DESC",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]
