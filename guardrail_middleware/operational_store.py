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

    def record(self, event: Any) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO evaluations
                (request_id, decision, reason_code, provider_used, degraded_mode, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.request_id,
                    event.decision.value,
                    event.reason_code,
                    event.provider_used,
                    int(event.degraded_mode),
                    event.latency_ms,
                ),
            )

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 500))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT request_id, decision, reason_code, provider_used,
                       degraded_mode, latency_ms, created_at
                FROM evaluations
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        return [dict(row) for row in rows]
