"""
Persistent storage for caffeine entries using SQLite.

The database is stored at ~/.caffeine_curfew/entries.db so it survives
server restarts and is isolated per user account on the host machine.

All operations are scoped by user_id so multiple users can share one
server instance without their data mixing. The user_id is derived from
the key query parameter in the SSE connection URL.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB_DIR = Path.home() / ".caffeine_curfew"
DB_PATH = DB_DIR / "entries.db"


def _connect() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the entries table if it does not already exist."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT    NOT NULL DEFAULT 'default',
                amount_mg   REAL    NOT NULL,
                consumed_at TEXT    NOT NULL,
                drink_name  TEXT,
                logged_at   TEXT    NOT NULL
            )
        """)

        existing_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(entries)")
        ]
        if "user_id" not in existing_columns:
            conn.execute(
                "ALTER TABLE entries ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'"
            )

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_entries_user_consumed
            ON entries (user_id, consumed_at)
        """)


def insert_entry(
    amount_mg: float,
    consumed_at: datetime,
    user_id: str = "default",
    drink_name: str = "",
) -> int:
    """Insert a new entry and return its assigned id."""
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO entries (user_id, amount_mg, consumed_at, drink_name, logged_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                amount_mg,
                consumed_at.isoformat(),
                drink_name or None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cursor.lastrowid


def fetch_entries_since(
    since: datetime,
    user_id: str = "default",
) -> list[dict[str, Any]]:
    """Return all entries for user_id with consumed_at >= since, oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, amount_mg, consumed_at, drink_name, logged_at
            FROM entries
            WHERE user_id = ? AND consumed_at >= ?
            ORDER BY consumed_at ASC
            """,
            (user_id, since.isoformat()),
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_entry_by_id(
    entry_id: int,
    user_id: str = "default",
) -> dict[str, Any] | None:
    """Return a single entry by id scoped to user_id, or None if not found."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM entries WHERE id = ? AND user_id = ?",
            (entry_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def remove_entry(
    entry_id: int,
    user_id: str = "default",
) -> bool:
    """Delete an entry by id scoped to user_id. Returns True if a row was deleted."""
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM entries WHERE id = ? AND user_id = ?",
            (entry_id, user_id),
        )
        return cursor.rowcount > 0
