from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

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
                    input_cost_usd REAL,
                    output_cost_usd REAL,
                    cost_source TEXT NOT NULL DEFAULT 'missing',
                    billing_mode TEXT NOT NULL DEFAULT 'token',
                    duration_ms INTEGER,
                    reasoning_text TEXT,
                    raw_json TEXT NOT NULL,
                    event_fingerprint TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_usage_events_ts ON usage_events(event_ts);
                CREATE INDEX IF NOT EXISTS idx_usage_events_session ON usage_events(session_id);
                CREATE INDEX IF NOT EXISTS idx_usage_events_model ON usage_events(model);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_events_fingerprint ON usage_events(event_fingerprint) WHERE event_fingerprint IS NOT NULL;

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

                CREATE TABLE IF NOT EXISTS session_backfill_state (
                    session_id TEXT PRIMARY KEY,
                    last_updated_at INTEGER NOT NULL,
                    last_input_tokens INTEGER NOT NULL,
                    last_output_tokens INTEGER NOT NULL,
                    last_total_tokens INTEGER NOT NULL,
                    last_context_tokens INTEGER NOT NULL
                );
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
            if "input_cost_usd" not in columns:
                conn.execute("ALTER TABLE usage_events ADD COLUMN input_cost_usd REAL")
            if "output_cost_usd" not in columns:
                conn.execute("ALTER TABLE usage_events ADD COLUMN output_cost_usd REAL")
            if "billing_mode" not in columns:
                conn.execute("ALTER TABLE usage_events ADD COLUMN billing_mode TEXT NOT NULL DEFAULT 'token'")
            if "event_fingerprint" not in columns:
                conn.execute("ALTER TABLE usage_events ADD COLUMN event_fingerprint TEXT")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_events_fingerprint ON usage_events(event_fingerprint) WHERE event_fingerprint IS NOT NULL"
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
                e.input_cost_usd,
                e.output_cost_usd,
                e.cost_source,
                e.billing_mode,
                e.duration_ms,
                e.reasoning_text,
                e.raw_json,
                e.event_fingerprint,
            )
            for e in events
        ]

        if not rows:
            return 0

        with self._connect() as conn:
            before = conn.total_changes
            conn.executemany(
                """
                INSERT OR IGNORE INTO usage_events (
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
                    input_cost_usd,
                    output_cost_usd,
                    cost_source,
                    billing_mode,
                    duration_ms,
                    reasoning_text,
                    raw_json,
                    event_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            inserted = conn.total_changes - before
        return inserted

    def get_daily_usage(self, days: int = 30) -> list[DailyUsageRow]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    DATE(event_ts) AS usage_date,
                    SUM(input_tokens) AS input_tokens,
                    SUM(output_tokens) AS output_tokens,
                    SUM(total_tokens) AS total_tokens,
                    COALESCE(SUM(input_cost_usd), 0.0) AS input_cost_usd,
                    COALESCE(SUM(output_cost_usd), 0.0) AS output_cost_usd,
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
                input_cost_usd=row["input_cost_usd"] or 0.0,
                output_cost_usd=row["output_cost_usd"] or 0.0,
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
                    COALESCE(SUM(input_cost_usd), 0.0) AS input_cost_usd,
                    COALESCE(SUM(output_cost_usd), 0.0) AS output_cost_usd,
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
                input_cost_usd=row["input_cost_usd"] or 0.0,
                output_cost_usd=row["output_cost_usd"] or 0.0,
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

        summary = {"observed": 0, "estimated": 0, "missing": 0, "subscription": 0}
        for row in rows:
            key = row["cost_source"] or "missing"
            summary[str(key)] = int(row["count"] or 0)
        return summary

    def get_data_status(self) -> dict:
        with self._connect() as conn:
            usage_count = conn.execute("SELECT COUNT(*) AS count FROM usage_events").fetchone()["count"]
            snapshot_usage_count = conn.execute(
                "SELECT COUNT(*) AS count FROM usage_events WHERE event_type = 'session.snapshot'"
            ).fetchone()["count"]
            snapshot_count = conn.execute("SELECT COUNT(*) AS count FROM session_snapshots").fetchone()["count"]
            latest_usage = conn.execute("SELECT MAX(event_ts) AS ts FROM usage_events").fetchone()["ts"]
            latest_snapshot_usage = conn.execute(
                "SELECT MAX(event_ts) AS ts FROM usage_events WHERE event_type = 'session.snapshot'"
            ).fetchone()["ts"]

        log_usage_count = int(usage_count or 0) - int(snapshot_usage_count or 0)

        return {
            "usage_events": int(usage_count or 0),
            "snapshot_backfill_events": int(snapshot_usage_count or 0),
            "session_snapshots": int(snapshot_count or 0),
            "latest_usage_event_ts": latest_usage,
            "latest_snapshot_backfill_ts": latest_snapshot_usage,
            "log_usage_available": log_usage_count > 0,
            "snapshot_backfill_available": int(snapshot_usage_count or 0) > 0,
            "reconciled_available": int(snapshot_count or 0) > 0,
        }

    def backfill_snapshot_deltas(
        self,
        billing_mode: str,
        cost_estimator: Callable[[str | None, str | None, int, int], tuple[float, float, float] | None] | None = None,
    ) -> int:
        with self._connect() as conn:
            snapshots = conn.execute(
                """
                SELECT
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
                FROM session_snapshots
                ORDER BY updated_at ASC
                """
            ).fetchall()

            state_rows = conn.execute(
                "SELECT * FROM session_backfill_state"
            ).fetchall()

            state = {row["session_id"]: row for row in state_rows}
            events: list[NormalizedUsageEvent] = []
            next_state: list[tuple] = []

            for row in snapshots:
                session_id = row["session_id"]
                previous = state.get(session_id)
                current_updated_at = int(row["updated_at"] or 0)
                if current_updated_at <= 0:
                    continue

                if previous is not None and current_updated_at <= int(previous["last_updated_at"] or 0):
                    continue

                current_input = int(row["input_tokens"] or 0)
                current_output = int(row["output_tokens"] or 0)
                current_total = int(row["total_tokens"] or 0)
                current_context = int(row["context_tokens"] or 0)

                if previous is None:
                    delta_input = current_input
                    delta_output = current_output
                    delta_total = current_total
                else:
                    delta_input = max(0, current_input - int(previous["last_input_tokens"] or 0))
                    delta_output = max(0, current_output - int(previous["last_output_tokens"] or 0))
                    delta_total = max(0, current_total - int(previous["last_total_tokens"] or 0))

                if delta_total <= 0 and delta_input <= 0 and delta_output <= 0:
                    next_state.append(
                        (
                            session_id,
                            current_updated_at,
                            current_input,
                            current_output,
                            current_total,
                            current_context,
                        )
                    )
                    continue

                if delta_total <= 0:
                    delta_total = delta_input + delta_output

                event_ts = datetime.fromtimestamp(current_updated_at / 1000.0, tz=timezone.utc)
                fingerprint_src = (
                    f"snapshot:{session_id}:{current_updated_at}:{delta_input}:{delta_output}:{delta_total}"
                )
                fingerprint = hashlib.sha256(fingerprint_src.encode("utf-8")).hexdigest()

                if billing_mode == "claude_max":
                    cost_usd = 0.0
                    input_cost_usd = 0.0
                    output_cost_usd = 0.0
                    cost_source = "subscription"
                else:
                    estimated = None
                    if cost_estimator is not None:
                        estimated = cost_estimator(
                            row["provider"],
                            row["model"],
                            delta_input,
                            delta_output,
                        )
                    if estimated is not None:
                        cost_usd, input_cost_usd, output_cost_usd = estimated
                        cost_source = "estimated"
                    else:
                        cost_usd = None
                        input_cost_usd = None
                        output_cost_usd = None
                        cost_source = "missing"

                events.append(
                    NormalizedUsageEvent(
                        event_ts=event_ts,
                        event_type="session.snapshot",
                        session_id=session_id,
                        session_key=row["session_key"],
                        provider=row["provider"],
                        model=row["model"],
                        channel="snapshot",
                        account_id=row["account_id"],
                        input_tokens=delta_input,
                        output_tokens=delta_output,
                        total_tokens=delta_total,
                        context_tokens=current_context,
                        cost_usd=cost_usd,
                        input_cost_usd=input_cost_usd,
                        output_cost_usd=output_cost_usd,
                        cost_source=cost_source,
                        billing_mode=billing_mode,
                        duration_ms=None,
                        reasoning_text=None,
                        raw_json=str(row["raw_json"]),
                        event_fingerprint=fingerprint,
                    )
                )

                next_state.append(
                    (
                        session_id,
                        current_updated_at,
                        current_input,
                        current_output,
                        current_total,
                        current_context,
                    )
                )

            inserted = self.insert_usage_events(events)

            if next_state:
                conn.executemany(
                    """
                    INSERT INTO session_backfill_state (
                        session_id,
                        last_updated_at,
                        last_input_tokens,
                        last_output_tokens,
                        last_total_tokens,
                        last_context_tokens
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id)
                    DO UPDATE SET
                        last_updated_at = excluded.last_updated_at,
                        last_input_tokens = excluded.last_input_tokens,
                        last_output_tokens = excluded.last_output_tokens,
                        last_total_tokens = excluded.last_total_tokens,
                        last_context_tokens = excluded.last_context_tokens
                    """,
                    next_state,
                )

        return inserted

    def get_models_used(self, limit: int = 200) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    provider,
                    model,
                    COUNT(DISTINCT session_id) AS sessions,
                    SUM(total_tokens) AS total_tokens,
                    MAX(updated_at) AS last_seen_at
                FROM session_snapshots
                WHERE model IS NOT NULL AND TRIM(model) <> ''
                GROUP BY provider, model
                ORDER BY total_tokens DESC, last_seen_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()

        return [
            {
                "provider": row["provider"],
                "model": row["model"],
                "sessions": int(row["sessions"] or 0),
                "total_tokens": int(row["total_tokens"] or 0),
                "last_seen_at": row["last_seen_at"],
            }
            for row in rows
        ]

    def get_session_events(self, session_id: str, limit: int = 300) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    event_ts,
                    event_type,
                    session_id,
                    provider,
                    model,
                    channel,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    context_tokens,
                    input_cost_usd,
                    output_cost_usd,
                    cost_usd,
                    cost_source,
                    billing_mode,
                    reasoning_text,
                    raw_json
                FROM usage_events
                WHERE session_id = ?
                ORDER BY event_ts DESC
                LIMIT ?
                """,
                (session_id, int(limit)),
            ).fetchall()

        return [
            {
                "event_ts": row["event_ts"],
                "event_type": row["event_type"],
                "session_id": row["session_id"],
                "provider": row["provider"],
                "model": row["model"],
                "channel": row["channel"],
                "input_tokens": int(row["input_tokens"] or 0),
                "output_tokens": int(row["output_tokens"] or 0),
                "total_tokens": int(row["total_tokens"] or 0),
                "context_tokens": int(row["context_tokens"] or 0),
                "input_cost_usd": float(row["input_cost_usd"] or 0.0),
                "output_cost_usd": float(row["output_cost_usd"] or 0.0),
                "cost_usd": float(row["cost_usd"] or 0.0),
                "cost_source": row["cost_source"],
                "billing_mode": row["billing_mode"],
                "reasoning_text": row["reasoning_text"],
                "raw_json": row["raw_json"],
            }
            for row in rows
        ]

    def get_token_accuracy(self, limit: int = 200) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.session_id,
                    s.provider,
                    s.model,
                    s.input_tokens AS snapshot_input_tokens,
                    s.output_tokens AS snapshot_output_tokens,
                    s.total_tokens AS snapshot_total_tokens,
                    COALESCE(e.input_tokens, 0) AS event_input_tokens,
                    COALESCE(e.output_tokens, 0) AS event_output_tokens,
                    COALESCE(e.total_tokens, 0) AS event_total_tokens,
                    COALESCE(e.snapshot_event_total_tokens, 0) AS snapshot_event_total_tokens,
                    s.updated_at
                FROM session_snapshots s
                LEFT JOIN (
                    SELECT
                        session_id,
                        SUM(input_tokens) AS input_tokens,
                        SUM(output_tokens) AS output_tokens,
                        SUM(total_tokens) AS total_tokens,
                        SUM(CASE WHEN event_type = 'session.snapshot' THEN total_tokens ELSE 0 END) AS snapshot_event_total_tokens
                    FROM usage_events
                    WHERE session_id IS NOT NULL
                    GROUP BY session_id
                ) e ON e.session_id = s.session_id
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()

        report = []
        for row in rows:
            snapshot_total = int(row["snapshot_total_tokens"] or 0)
            snapshot_event_total = int(row["snapshot_event_total_tokens"] or 0)
            total_delta = snapshot_total - snapshot_event_total
            report.append(
                {
                    "session_id": row["session_id"],
                    "provider": row["provider"],
                    "model": row["model"],
                    "snapshot_input_tokens": int(row["snapshot_input_tokens"] or 0),
                    "snapshot_output_tokens": int(row["snapshot_output_tokens"] or 0),
                    "snapshot_total_tokens": snapshot_total,
                    "event_input_tokens": int(row["event_input_tokens"] or 0),
                    "event_output_tokens": int(row["event_output_tokens"] or 0),
                    "event_total_tokens": int(row["event_total_tokens"] or 0),
                    "snapshot_event_total_tokens": snapshot_event_total,
                    "snapshot_delta_tokens": total_delta,
                    "snapshot_match": total_delta == 0,
                    "updated_at": int(row["updated_at"] or 0),
                }
            )
        return report
