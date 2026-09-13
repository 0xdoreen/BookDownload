from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from .models import BookRequest, BookStatus


SCHEMA = """
CREATE TABLE IF NOT EXISTS queue_items (
    id TEXT PRIMARY KEY,
    position INTEGER NOT NULL,
    status TEXT NOT NULL,
    book_json TEXT NOT NULL,
    output_dir TEXT NOT NULL,
    source_list TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    last_error TEXT,
    result_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_queue_due
ON queue_items(status, next_attempt_at, position);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class QueueStore:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "bookdownload.db"
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def add_books(self, books: list[BookRequest], output_dir: Path, source_list: Path) -> list[str]:
        now = _now()
        with self.connect() as connection:
            position = connection.execute("SELECT COALESCE(MAX(position), 0) FROM queue_items").fetchone()[0]
            ids: list[str] = []
            for offset, book in enumerate(books, 1):
                item_id = uuid.uuid4().hex[:12]
                ids.append(item_id)
                connection.execute(
                    """INSERT INTO queue_items
                    (id, position, status, book_json, output_dir, source_list, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        item_id,
                        position + offset,
                        BookStatus.PENDING,
                        json.dumps(book.as_dict(), ensure_ascii=False),
                        str(output_dir.resolve()),
                        str(source_list.resolve()),
                        now,
                        now,
                    ),
                )
        return ids

    def list_items(self, status: BookStatus | None = None) -> list[sqlite3.Row]:
        query = "SELECT * FROM queue_items"
        params: tuple[str, ...] = ()
        if status:
            query += " WHERE status = ?"
            params = (status.value,)
        query += " ORDER BY position"
        with self.connect() as connection:
            return list(connection.execute(query, params))

    def get(self, item_id: str) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute("SELECT * FROM queue_items WHERE id = ?", (item_id,)).fetchone()

    def update_status(
        self,
        item_id: str,
        status: BookStatus,
        *,
        error: str | None = None,
        next_attempt_at: datetime | None = None,
        result_path: Path | None = None,
        increment_attempts: bool = False,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """UPDATE queue_items SET status = ?, last_error = ?, next_attempt_at = ?,
                result_path = COALESCE(?, result_path), updated_at = ?,
                attempts = attempts + ? WHERE id = ?""",
                (
                    status.value,
                    error,
                    next_attempt_at.astimezone(UTC).isoformat() if next_attempt_at else None,
                    str(result_path) if result_path else None,
                    _now(),
                    1 if increment_attempts else 0,
                    item_id,
                ),
            )

    def due_items(self, now: datetime | None = None) -> list[sqlite3.Row]:
        timestamp = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
        eligible = (BookStatus.PENDING.value, BookStatus.READY.value, BookStatus.QUOTA_WAIT.value)
        with self.connect() as connection:
            return list(
                connection.execute(
                    """SELECT * FROM queue_items
                    WHERE status IN (?, ?, ?)
                    AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                    ORDER BY position""",
                    (*eligible, timestamp),
                )
            )

    def next_due_at(self) -> datetime | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT MIN(next_attempt_at) FROM queue_items
                WHERE status = ? AND next_attempt_at IS NOT NULL""",
                (BookStatus.QUOTA_WAIT.value,),
            ).fetchone()
        return datetime.fromisoformat(row[0]) if row and row[0] else None

    def delete(self, item_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM queue_items WHERE id = ? AND status != ?",
                (item_id, BookStatus.DOWNLOADING.value),
            )
            return cursor.rowcount > 0

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self.connect() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default


def row_to_book(row: sqlite3.Row) -> BookRequest:
    return BookRequest(**json.loads(row["book_json"]))


def _now() -> str:
    return datetime.now(UTC).isoformat()
