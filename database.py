"""SQLite storage for tracking published (and in-progress) Pixabay videos.

Keeps the MVP honest about one rule above all others:
never upload the same Pixabay video to YouTube twice.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    pixabay_id INTEGER PRIMARY KEY,
    page_url   TEXT,
    title      TEXT,
    youtube_id TEXT,
    status     TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    uploaded_at TEXT
);
"""

# status values: pending -> uploaded
# 'pending' rows are only ever created right before a download/upload
# attempt starts, and are removed again if that attempt fails, so a
# retry after a crash never blocks re-selection of the same video.


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str):
        self.path = path
        with self._connect() as conn:
            conn.execute(SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def exists(self, pixabay_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM videos WHERE pixabay_id = ?", (pixabay_id,)
            ).fetchone()
            return row is not None

    def mark_pending(self, pixabay_id: int, page_url: str, title: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO videos "
                "(pixabay_id, page_url, title, status, created_at) "
                "VALUES (?, ?, ?, 'pending', ?)",
                (pixabay_id, page_url, title, _now()),
            )

    def mark_uploaded(self, pixabay_id: int, youtube_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE videos SET status = 'uploaded', youtube_id = ?, "
                "uploaded_at = ? WHERE pixabay_id = ?",
                (youtube_id, _now(), pixabay_id),
            )

    def remove_pending(self, pixabay_id: int) -> None:
        """Undo mark_pending after a failed attempt so the video can be
        retried later without ever being seen as a duplicate."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM videos WHERE pixabay_id = ? AND status = 'pending'",
                (pixabay_id,),
            )
