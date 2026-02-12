from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from .models import DailyUsageRow, NormalizedUsageEvent, SessionUsageRow


class UsageRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_ts TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    session_id TEXT,
                    session_key TEXT,
                    provider TEXT,
                    model TEXT,
                    channel TEXT,
                    account_id TEXT,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    context_tokens INTEGER NOT NULL,
                    cost_usd REAL,
                    cost_source TEXT NOT NULL DEFAULT 'missing',
                    duration_ms INTEGER,
                    reasoning_text TEXT,
                    raw_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_usage_events_ts ON usage_events(event_ts);
                CREATE INDEX IF NOT EXISTS idx_usage_events_session ON usage_events(session_id);
                CREATE INDEX IF NOT EXISTS idx_usage_events_model ON usage_events(model);

                CREATE TABLE IF NOT EXISTS checkpoints (
                    source_key TEXT PRIMARY KEY,
                    cursor TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS session_snapshots (
                    session_id TEXT PRIMARY KEY,
                    session_key TEXT,
                    provider TEXT,
                    model TEXT,
                    account_id TEXT,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    context_tokens INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_session_snapshots_updated_at ON session_snapshots(updated_at);
                """
            )

            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(usage_events)").fetchall()
            }
            if "cost_source" not in columns:
                conn.execute(
                    "ALTER TABLE usage_events ADD COLUMN cost_source TEXT NOT NULL DEFAULT 'missing'"
                )

    def insert_usage_events(self, events: Iterable[NormalizedUsageEvent]) -> int:
        rows = [
            (
                e.event_ts.isoformat(),
                e.event_type,
                e.session_id,
                e.session_key,
                e.provider,
                e.model,
                e.channel,
                e.account_id,
                e.input_tokens,
                e.output_tokens,
                e.total_tokens,
                e.context_tokens,
                e.cost_usd,
                e.cost_source,
                e.duration_ms,
                e.reasoning_text,
                e.raw_json,
            )
            for e in events
        ]

        if not rows:
            return 0

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO usage_events (
                    event_ts,
                    event_type,
                    session_id,
                    session_key,
                    provider,
                    model,
                    channel,
                    account_id,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    context_tokens,
                    cost_usd,
                    cost_source,
                    duration_ms,
                    reasoning_text,
                    raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def get_daily_usage(self, days: int = 30) -> list[DailyUsageRow]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    DATE(event_ts) AS usage_date,
                    SUM(input_tokens) AS input_tokens,
                    SUM(output_tokens) AS output_tokens,
                    SUM(total_tokens) AS total_tokens,
                    COALESCE(SUM(cost_usd), 0.0) AS cost_usd
                FROM usage_events
                WHERE event_ts >= datetime('now', ?)
                GROUP BY DATE(event_ts)
                ORDER BY usage_date DESC
                """,
                (f"-{int(days)} days",),
            ).fetchall()

        return [
            DailyUsageRow(
                usage_date=row["usage_date"],
                input_tokens=row["input_tokens"] or 0,
                output_tokens=row["output_tokens"] or 0,
                total_tokens=row["total_tokens"] or 0,
                cost_usd=row["cost_usd"] or 0.0,
            )
            for row in rows
        ]

    def get_session_usage(self, limit: int = 100) -> list[SessionUsageRow]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    COALESCE(session_id, 'unknown') AS session_id,
                    provider,
                    model,
                    SUM(total_tokens) AS total_tokens,
                    COALESCE(SUM(cost_usd), 0.0) AS cost_usd,
                    MAX(event_ts) AS last_event_ts
                FROM usage_events
                GROUP BY COALESCE(session_id, 'unknown'), provider, model
                ORDER BY last_event_ts DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()

        return [
            SessionUsageRow(
                session_id=row["session_id"],
                provider=row["provider"],
                model=row["model"],
                total_tokens=row["total_tokens"] or 0,
                cost_usd=row["cost_usd"] or 0.0,
                last_event_ts=row["last_event_ts"],
            )
            for row in rows
        ]

    def get_reasoning_events(self, limit: int = 100) -> list[dict[str, str | None]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_ts, session_id, provider, model, reasoning_text
                FROM usage_events
                WHERE reasoning_text IS NOT NULL AND TRIM(reasoning_text) <> ''
                ORDER BY event_ts DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()

        return [
            {
                "event_ts": row["event_ts"],
                "session_id": row["session_id"],
                "provider": row["provider"],
                "model": row["model"],
                "reasoning_text": row["reasoning_text"],
            }
            for row in rows
        ]

    def get_checkpoint(self, source_key: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT cursor FROM checkpoints WHERE source_key = ?",
                (source_key,),
            ).fetchone()

        if not row:
            return 0

        try:
            return int(row["cursor"])
        except (ValueError, TypeError):
            return 0

    def upsert_checkpoint(self, source_key: str, cursor: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints(source_key, cursor, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(source_key)
                DO UPDATE SET cursor = excluded.cursor, updated_at = datetime('now')
                """,
                (source_key, str(cursor)),
            )

    def upsert_session_snapshots(self, sessions: list[dict]) -> int:
        rows = []
        for session in sessions:
            origin = session.get("origin") if isinstance(session.get("origin"), dict) else {}
            rows.append(
                (
                    session.get("sessionId") or "unknown",
                    session.get("key"),
                    session.get("modelProvider") or origin.get("provider"),
                    session.get("model"),
                    origin.get("accountId"),
                    int(session.get("inputTokens") or 0),
                    int(session.get("outputTokens") or 0),
                    int(session.get("totalTokens") or 0),
                    int(session.get("contextTokens") or 0),
                    int(session.get("updatedAt") or 0),
                    str(session),
                )
            )

        if not rows:
            return 0

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO session_snapshots (
                    session_id,
                    session_key,
                    provider,
                    model,
                    account_id,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    context_tokens,
                    updated_at,
                    raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id)
                DO UPDATE SET
                    session_key = excluded.session_key,
                    provider = excluded.provider,
                    model = excluded.model,
                    account_id = excluded.account_id,
                    input_tokens = excluded.input_tokens,
                    output_tokens = excluded.output_tokens,
                    total_tokens = excluded.total_tokens,
                    context_tokens = excluded.context_tokens,
                    updated_at = excluded.updated_at,
                    raw_json = excluded.raw_json
                """,
                rows,
            )
        return len(rows)

    def get_reconciled_session_usage(self, limit: int = 100) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.session_id,
                    s.provider,
                    s.model,
                    s.input_tokens,
                    s.output_tokens,
                    s.total_tokens,
                    s.context_tokens,
                    s.updated_at,
                    COALESCE(e.cost_usd, 0.0) AS observed_cost_usd,
                    COALESCE(e.event_count, 0) AS observed_event_count
                FROM session_snapshots s
                LEFT JOIN (
                    SELECT
                        COALESCE(session_id, 'unknown') AS session_id,
                        SUM(COALESCE(cost_usd, 0.0)) AS cost_usd,
                        COUNT(*) AS event_count
                    FROM usage_events
                    GROUP BY COALESCE(session_id, 'unknown')
                ) e ON e.session_id = s.session_id
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()

        return [
            {
                "session_id": row["session_id"],
                "provider": row["provider"],
                "model": row["model"],
                "input_tokens": row["input_tokens"] or 0,
                "output_tokens": row["output_tokens"] or 0,
                "total_tokens": row["total_tokens"] or 0,
                "context_tokens": row["context_tokens"] or 0,
                "updated_at": row["updated_at"],
                "observed_cost_usd": row["observed_cost_usd"] or 0.0,
                "observed_event_count": row["observed_event_count"] or 0,
            }
            for row in rows
        ]

    def get_cost_source_summary(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT cost_source, COUNT(*) AS count
                FROM usage_events
                GROUP BY cost_source
                """
            ).fetchall()

        summary = {"observed": 0, "estimated": 0, "missing": 0}
        for row in rows:
            key = row["cost_source"] or "missing"
            summary[str(key)] = int(row["count"] or 0)
        return summary
