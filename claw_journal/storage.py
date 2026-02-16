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

                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    event_ts TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content_text TEXT,
                    message_type TEXT,
                    source TEXT NOT NULL,
                    source_path TEXT,
                    raw_json TEXT NOT NULL,
                    message_fingerprint TEXT NOT NULL
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

            convo_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(conversation_messages)").fetchall()
            }
            if convo_columns and "session_id" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN session_id TEXT NOT NULL DEFAULT 'unknown'")
            if convo_columns and "event_ts" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN event_ts TEXT NOT NULL DEFAULT ''")
            if convo_columns and "message_ts" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN message_ts TEXT")
            if convo_columns and "role" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN role TEXT NOT NULL DEFAULT 'unknown'")
            if convo_columns and "agent_id" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN agent_id TEXT")
            if convo_columns and "turn_index" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN turn_index INTEGER NOT NULL DEFAULT 0")
            if convo_columns and "message_fingerprint" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN message_fingerprint TEXT")
            if convo_columns and "event_fingerprint" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN event_fingerprint TEXT")
            if convo_columns and "source" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN source TEXT NOT NULL DEFAULT 'transcript'")
            if convo_columns and "source_path" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN source_path TEXT")
            if convo_columns and "message_type" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN message_type TEXT")
            if convo_columns and "provider" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN provider TEXT")
            if convo_columns and "model" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN model TEXT")
            if convo_columns and "content_text" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN content_text TEXT")
            if convo_columns and "text_content" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN text_content TEXT")
            if convo_columns and "content_json" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN content_json TEXT NOT NULL DEFAULT ''")
            if convo_columns and "raw_json" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN raw_json TEXT NOT NULL DEFAULT ''")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_conversation_messages_fingerprint ON conversation_messages(message_fingerprint)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversation_messages_session_ts ON conversation_messages(session_id, event_ts)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversation_messages_source_path ON conversation_messages(source_path)"
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

    def get_dashboard_summary(self) -> dict:
        with self._connect() as conn:
            usage_row = conn.execute(
                """
                SELECT
                    SUM(COALESCE(cost_usd, 0.0)) as total_spend,
                    SUM(total_tokens) as usage_tokens,
                    COUNT(DISTINCT session_id) as usage_sessions,
                    SUM(context_tokens) as cache_reads
                FROM usage_events
                """
            ).fetchone()

            snapshot_row = conn.execute(
                """
                SELECT
                    SUM(total_tokens) as snapshot_tokens,
                    COUNT(DISTINCT session_id) as snapshot_sessions,
                    COUNT(DISTINCT session_key) as snapshot_agents
                FROM session_snapshots
                """
            ).fetchone()

            total_spend = usage_row["total_spend"] or 0.0
            usage_tokens = usage_row["usage_tokens"] or 0
            usage_sessions = usage_row["usage_sessions"] or 0
            cache_reads = usage_row["cache_reads"] or 0

            snapshot_tokens = snapshot_row["snapshot_tokens"] or 0
            snapshot_sessions = snapshot_row["snapshot_sessions"] or 0
            snapshot_agents = snapshot_row["snapshot_agents"] or 0

            total_tokens = usage_tokens if usage_tokens > 0 else snapshot_tokens
            sessions = usage_sessions if usage_sessions > 0 else snapshot_sessions

            usage_total_agents = conn.execute(
                "SELECT COUNT(DISTINCT session_key) as c FROM usage_events WHERE session_key IS NOT NULL"
            ).fetchone()["c"]
            usage_active_agents = conn.execute(
                "SELECT COUNT(DISTINCT session_key) as c FROM usage_events WHERE session_key IS NOT NULL AND datetime(event_ts) > datetime('now', '-7 days')"
            ).fetchone()["c"]

            snapshot_active_agents = conn.execute(
                """
                SELECT COUNT(DISTINCT session_key) as c
                FROM session_snapshots
                WHERE session_key IS NOT NULL
                  AND updated_at >= CAST((strftime('%s','now') - 7 * 86400) * 1000 AS INTEGER)
                """
            ).fetchone()["c"]

            total_agents = usage_total_agents if usage_total_agents > 0 else snapshot_agents
            active_agents = usage_active_agents if usage_active_agents > 0 else snapshot_active_agents

            avg_session_cost = total_spend / sessions if sessions > 0 else 0.0

            # Cache hit rate estimation (context tokens / total input tokens?)
            # This is rough as schema doesn't strictly track cache hits vs misses
            # Using context_tokens as "cache reads" proxy
            cache_hit_pct = "0%" 
            if total_tokens > 0:
                 # Very rough approximation
                 pct = (cache_reads / total_tokens) * 100
                 cache_hit_pct = f"{pct:.1f}%"

            # Check for mocked data if DB is empty (per user request to match image exactly if empty?)
            # No, user wants updates based on "the given text" which uses mock data.
            # But the user also wants to "Update the UI".
            # I will return real data primarily, but formatted to match the frontend expectations.

            return {
                "totalSpend": round(total_spend, 2),
                "totalTokens": f"{total_tokens / 1000000:.1f}M" if total_tokens >= 1000000 else (f"{total_tokens / 1000:.1f}K" if total_tokens >= 1000 else str(total_tokens)),
                "sessions": sessions,
                "activeAgents": f"{active_agents}/{total_agents}",
                "avgSession": round(avg_session_cost, 2),
                "cacheHit": cache_hit_pct,
                "cacheReads": f"{cache_reads / 1000000:.1f}M" if cache_reads >= 1000000 else (f"{cache_reads / 1000:.1f}K" if cache_reads >= 1000 else str(cache_reads)),
                "cacheCost": 0.0 # Placeholder
            }

    def get_cost_trend(self, days: int = 7) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    strftime('%m-%d', event_ts) as date_str,
                    SUM(COALESCE(cost_usd, 0.0)) as cost
                FROM usage_events
                WHERE datetime(event_ts) > datetime('now', ?)
                GROUP BY date_str
                ORDER BY date_str ASC
                """,
                (f"-{days} days",),
            ).fetchall()
        return [{"date": r["date_str"], "cost": r["cost"] or 0.0} for r in rows]

    def get_cost_by_agent(self, limit: int = 5) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    session_key as name,
                    SUM(COALESCE(cost_usd, 0.0)) as cost
                FROM usage_events
                WHERE session_key IS NOT NULL
                GROUP BY session_key
                ORDER BY cost DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()

            if not rows:
                rows = conn.execute(
                    """
                    SELECT
                        session_key as name,
                        0.0 as cost
                    FROM session_snapshots
                    WHERE session_key IS NOT NULL
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,)
                ).fetchall()

        # Clean up session key for display (e.g. "agent:steward:main" -> "Steward")
        data = []
        for r in rows:
            name = r["name"]
            if name.startswith("agent:"):
                parts = name.split(":")
                if len(parts) > 1:
                    name = parts[1].replace("_", " ").title()
            data.append({"name": name, "cost": r["cost"] or 0.0})
        return data

    def get_top_tools(self, limit: int = 5) -> list[dict]:
        # Attempt to retrieve tools if logged in event_type or raw_json
        # Current schema has event_type. Let's assume tool usage is an event type or we return empty
        with self._connect() as conn:
             rows = conn.execute(
                """
                SELECT event_type as name, COUNT(*) as count
                FROM usage_events
                GROUP BY event_type
                ORDER BY count DESC
                LIMIT ?
                """,
                (limit,)
             ).fetchall()
        return [{"name": r["name"], "count": r["count"]} for r in rows]
    def get_recent_sessions(self, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    session_key,
                    session_id,
                    provider,
                    model,
                    COUNT(*) as msg_count,
                    SUM(COALESCE(cost_usd, 0.0)) as cost,
                    SUM(total_tokens) as tokens,
                    MAX(event_ts) as last_active
                FROM usage_events
                GROUP BY session_id
                ORDER BY last_active DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()

            if not rows:
                rows = conn.execute(
                    """
                    SELECT
                        session_key,
                        session_id,
                        provider,
                        model,
                        0 as msg_count,
                        0.0 as cost,
                        total_tokens as tokens,
                        datetime(updated_at / 1000, 'unixepoch') as last_active
                    FROM session_snapshots
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,)
                ).fetchall()
        
        result = []
        for r in rows:
            # Parse agent name from session_key if possible
            agent_name = "unknown"
            s_key = r["session_key"]
            if s_key and s_key.startswith("agent:"):
                parts = s_key.split(":")
                if len(parts) > 1:
                    agent_name = parts[1]
            elif r["provider"]:
                agent_name = r["provider"]
            
            result.append({
                "agent": agent_name,
                "sessionKey": r["session_key"] or r["session_id"] or "unknown",
                "msgs": r["msg_count"],
                "cost": r["cost"] or 0.0,
                "tokens": f"{r['tokens'] / 1000000:.1f}M" if r["tokens"] >= 1000000 else (f"{r['tokens'] / 1000:.1f}K" if r["tokens"] >= 1000 else str(r["tokens"])),
                "lastActive": r["last_active"]
            })
        return result
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

    def get_session_snapshots(self, limit: int = 200) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
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
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()

        return [
            {
                "session_id": row["session_id"],
                "session_key": row["session_key"],
                "provider": row["provider"],
                "model": row["model"],
                "account_id": row["account_id"],
                "input_tokens": int(row["input_tokens"] or 0),
                "output_tokens": int(row["output_tokens"] or 0),
                "total_tokens": int(row["total_tokens"] or 0),
                "context_tokens": int(row["context_tokens"] or 0),
                "updated_at": int(row["updated_at"] or 0),
                "raw_json": row["raw_json"],
            }
            for row in rows
        ]

    def insert_conversation_messages(self, messages: list[dict]) -> int:
        filtered = [
            message
            for message in messages
            if message.get("message_fingerprint") and message.get("event_ts")
        ]

        if not filtered:
            return 0

        with self._connect() as conn:
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(conversation_messages)").fetchall()
            }

            insert_columns = ["session_id", "role", "raw_json"]
            if "event_ts" in columns:
                insert_columns.append("event_ts")
            if "message_ts" in columns:
                insert_columns.append("message_ts")

            if "content_text" in columns:
                insert_columns.append("content_text")
            if "text_content" in columns:
                insert_columns.append("text_content")
            if "content_json" in columns:
                insert_columns.append("content_json")

            if "message_type" in columns:
                insert_columns.append("message_type")
            if "provider" in columns:
                insert_columns.append("provider")
            if "model" in columns:
                insert_columns.append("model")
            if "source" in columns:
                insert_columns.append("source")
            if "source_path" in columns:
                insert_columns.append("source_path")

            if "message_fingerprint" in columns:
                insert_columns.append("message_fingerprint")
            if "event_fingerprint" in columns:
                insert_columns.append("event_fingerprint")

            if "turn_index" in columns:
                insert_columns.append("turn_index")
            if "agent_id" in columns:
                insert_columns.append("agent_id")

            rows: list[tuple] = []
            for message in filtered:
                session_id = str(message.get("session_id") or "unknown")
                role = str(message.get("role") or "unknown")
                event_ts = str(message.get("event_ts") or "")
                content_text = str(message.get("content_text") or "")
                raw_json = str(message.get("raw_json") or "")
                message_fingerprint = str(message.get("message_fingerprint") or "")
                source = str(message.get("source") or "transcript")
                source_path = message.get("source_path")
                message_type = message.get("message_type")
                provider = message.get("provider")
                model = message.get("model")
                turn_index = int(message.get("turn_index") or 0)
                content_json = str(message.get("content_json") or raw_json)

                agent_id = None
                if session_id.startswith("agent:"):
                    parts = session_id.split(":")
                    if len(parts) > 1:
                        agent_id = parts[1]

                value_by_column = {
                    "session_id": session_id,
                    "role": role,
                    "raw_json": raw_json,
                    "event_ts": event_ts,
                    "message_ts": event_ts,
                    "content_text": content_text,
                    "text_content": content_text,
                    "content_json": content_json,
                    "message_type": message_type,
                    "provider": provider,
                    "model": model,
                    "source": source,
                    "source_path": source_path,
                    "message_fingerprint": message_fingerprint,
                    "event_fingerprint": message_fingerprint,
                    "turn_index": turn_index,
                    "agent_id": agent_id,
                }
                rows.append(tuple(value_by_column.get(column) for column in insert_columns))

            placeholders = ", ".join(["?"] * len(insert_columns))
            column_names = ",\n                    ".join(insert_columns)
            before = conn.total_changes
            conn.executemany(
                f"""
                INSERT OR IGNORE INTO conversation_messages (
                    {column_names}
                ) VALUES ({placeholders})
                """,
                rows,
            )
            inserted = conn.total_changes - before
        return inserted

    def get_chat_sessions(self, limit: int = 100, offset: int = 0) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    COALESCE(NULLIF(source_path, ''), session_id) AS session_group,
                    MIN(session_id) AS session_id,
                    MIN(source_path) AS source_path,
                    COUNT(*) AS message_count,
                    MAX(COALESCE(NULLIF(event_ts, ''), message_ts)) AS last_event_ts,
                    MIN(COALESCE(NULLIF(event_ts, ''), message_ts)) AS first_event_ts,
                    SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END) AS user_messages,
                    SUM(CASE WHEN role = 'assistant' THEN 1 ELSE 0 END) AS assistant_messages,
                    SUM(CASE WHEN COALESCE(NULLIF(content_text, ''), text_content, '') LIKE 'Read HEARTBEAT%' THEN 1 ELSE 0 END) AS heartbeat_messages,
                    SUM(CASE WHEN COALESCE(NULLIF(content_text, ''), text_content, '') LIKE '[WhatsApp %' THEN 1 ELSE 0 END) AS whatsapp_messages,
                    SUM(CASE WHEN COALESCE(NULLIF(content_text, ''), text_content, '') LIKE '[cron:%' THEN 1 ELSE 0 END) AS cron_messages
                FROM conversation_messages
                GROUP BY COALESCE(NULLIF(source_path, ''), session_id)
                ORDER BY last_event_ts DESC
                LIMIT ? OFFSET ?
                """,
                (int(limit), int(offset)),
            ).fetchall()

            snapshot_rows = conn.execute(
                """
                SELECT
                    session_id,
                    session_key,
                    provider,
                    model,
                    updated_at,
                    total_tokens
                FROM session_snapshots
                """
            ).fetchall()

            meta_rows = conn.execute(
                """
                SELECT
                    COALESCE(NULLIF(source_path, ''), session_id) AS session_group,
                    provider,
                    model,
                    COALESCE(NULLIF(event_ts, ''), message_ts) AS ts
                FROM conversation_messages
                ORDER BY ts DESC
                """
            ).fetchall()

        snapshot_by_session = {
            str(row["session_id"]): {
                "session_key": row["session_key"],
                "provider": row["provider"],
                "model": row["model"],
                "updated_at": int(row["updated_at"] or 0),
                "total_tokens": int(row["total_tokens"] or 0),
            }
            for row in snapshot_rows
        }

        message_meta_by_group: dict[str, dict] = {}
        for row in meta_rows:
            session_group = str(row["session_group"] or "")
            if not session_group or session_group in message_meta_by_group:
                continue
            message_meta_by_group[session_group] = {
                "provider": row["provider"],
                "model": row["model"],
            }

        result: list[dict] = []
        for row in rows:
            session_id_raw = str(row["session_id"] or "unknown")
            source_path = row["source_path"]
            canonical_session_id = _canonical_session_id(session_id=session_id_raw, source_path=source_path)
            snapshot = snapshot_by_session.get(canonical_session_id, {})
            session_group = str(row["session_group"] or "")
            message_meta = message_meta_by_group.get(session_group, {})

            heartbeat_messages = int(row["heartbeat_messages"] or 0)
            whatsapp_messages = int(row["whatsapp_messages"] or 0)
            cron_messages = int(row["cron_messages"] or 0)
            user_messages = int(row["user_messages"] or 0)
            assistant_messages = int(row["assistant_messages"] or 0)

            session_type = "general"
            if heartbeat_messages > 0 and user_messages <= max(heartbeat_messages, 1):
                session_type = "heartbeat"
            elif whatsapp_messages > 0:
                session_type = "whatsapp"
            elif cron_messages > 0:
                session_type = "cron"
            elif user_messages > 0 and assistant_messages > 0:
                session_type = "conversation"

            result.append(
                {
                    "session_id": canonical_session_id,
                    "session_key": snapshot.get("session_key"),
                    "provider": message_meta.get("provider") or snapshot.get("provider"),
                    "model": message_meta.get("model") or snapshot.get("model"),
                    "message_count": int(row["message_count"] or 0),
                    "user_messages": user_messages,
                    "assistant_messages": assistant_messages,
                    "first_event_ts": row["first_event_ts"],
                    "last_event_ts": row["last_event_ts"],
                    "snapshot_updated_at": snapshot.get("updated_at", 0),
                    "snapshot_total_tokens": snapshot.get("total_tokens", 0),
                    "session_type": session_type,
                    "source_path": source_path,
                }
            )
        return result

    def get_chat_session_messages(self, session_id: str, limit: int = 300, before_id: int | None = None) -> dict:
        with self._connect() as conn:
            source_like = f"%/{session_id}.jsonl"
            if before_id and before_id > 0:
                rows = conn.execute(
                    """
                    SELECT
                        id,
                        session_id,
                        COALESCE(NULLIF(event_ts, ''), message_ts) AS event_ts,
                        role,
                        COALESCE(NULLIF(content_text, ''), text_content) AS content_text,
                        message_type,
                        provider,
                        model,
                        source,
                        source_path,
                        raw_json
                    FROM conversation_messages
                    WHERE (session_id = ? OR source_path LIKE ?) AND id < ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (session_id, source_like, int(before_id), int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT
                        id,
                        session_id,
                        COALESCE(NULLIF(event_ts, ''), message_ts) AS event_ts,
                        role,
                        COALESCE(NULLIF(content_text, ''), text_content) AS content_text,
                        message_type,
                        provider,
                        model,
                        source,
                        source_path,
                        raw_json
                    FROM conversation_messages
                    WHERE session_id = ? OR source_path LIKE ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (session_id, source_like, int(limit)),
                ).fetchall()

        ordered_rows = list(reversed(rows))
        messages = [
            {
                "id": int(row["id"]),
                "session_id": row["session_id"],
                "event_ts": row["event_ts"],
                "role": row["role"],
                "content_text": row["content_text"],
                "message_type": row["message_type"],
                "provider": row["provider"],
                "model": row["model"],
                "source": row["source"],
                "source_path": row["source_path"],
                "raw_json": row["raw_json"],
            }
            for row in ordered_rows
        ]

        next_before_id = None
        if rows:
            next_before_id = int(rows[-1]["id"])

        return {
            "session_id": session_id,
            "rows": messages,
            "next_before_id": next_before_id,
        }


def _canonical_session_id(session_id: str, source_path: object) -> str:
    if isinstance(source_path, str) and source_path.strip():
        stem = Path(source_path).stem
        if stem:
            return stem
    return session_id or "unknown"

    def get_checkpoints(self, limit: int = 500) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_key, cursor, updated_at
                FROM checkpoints
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()

        checkpoints: list[dict] = []
        for row in rows:
            cursor_value: int | str = row["cursor"]
            try:
                cursor_value = int(row["cursor"])
            except (TypeError, ValueError):
                cursor_value = str(row["cursor"] or "")

            checkpoints.append(
                {
                    "source_key": row["source_key"],
                    "cursor": cursor_value,
                    "updated_at": row["updated_at"],
                }
            )
        return checkpoints

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
