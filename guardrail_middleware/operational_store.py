from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class OperationalStore:
    """Small SQLite store for sanitized runtime evaluations and audit events."""

    def __init__(self, path: str | Path = "data/guardryle_runtime.sqlite3"):
        self.path = Path(path)
        self._memory_connection: sqlite3.Connection | None = None
        if str(path) == ":memory:":
            self._memory_connection = sqlite3.connect(":memory:")
            self._memory_connection.row_factory = sqlite3.Row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_connection is not None:
            return self._memory_connection
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS evaluations (
                    request_id TEXT PRIMARY KEY,
                    decision TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    provider_used TEXT,
                    degraded_mode INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(evaluations)").fetchall()
            }
            if "reviewed" not in columns:
                connection.execute(
                    "ALTER TABLE evaluations ADD COLUMN reviewed INTEGER NOT NULL DEFAULT 0"
                )

    def record(self, event: Any) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO evaluations
                (request_id, decision, reason_code, provider_used, degraded_mode, latency_ms, reviewed)
                VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT reviewed FROM evaluations WHERE request_id = ?), 0))
                """,
                (
                    event.request_id,
                    event.decision.value,
                    event.reason_code,
                    event.provider_used,
                    int(event.degraded_mode),
                    event.latency_ms,
                    event.request_id,
                ),
            )

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 500))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT request_id, decision, reason_code, provider_used,
                       degraded_mode, latency_ms, reviewed, created_at
                FROM evaluations
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def summary(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN decision = 'deny' THEN 1 ELSE 0 END) AS denied,
                       SUM(CASE WHEN decision = 'review' THEN 1 ELSE 0 END) AS review,
                       SUM(CASE WHEN decision = 'allow' THEN 1 ELSE 0 END) AS allowed,
                       SUM(CASE WHEN degraded_mode = 1 THEN 1 ELSE 0 END) AS degraded,
                       SUM(CASE WHEN reviewed = 1 THEN 1 ELSE 0 END) AS reviewed,
                       AVG(latency_ms) AS average_latency_ms,
                       MAX(created_at) AS last_event_at
                FROM evaluations
                """
            ).fetchone()
        values = dict(row)
        return {
            key: (0 if value is None and key != "average_latency_ms" else value)
            for key, value in values.items()
        }

    def mark_reviewed(self, request_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE evaluations SET reviewed = 1 WHERE request_id = ?",
                (request_id,),
            )
        return cursor.rowcount == 1
