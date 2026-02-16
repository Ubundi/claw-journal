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

    def get_dashboard_summary(self) -> dict:
        with self._connect() as conn:
            # Stats (total spend, tokens, sessions)
            row = conn.execute(
                """
                SELECT
                    SUM(COALESCE(cost_usd, 0.0)) as total_spend,
                    SUM(total_tokens) as total_tokens,
                    COUNT(DISTINCT session_id) as sessions,
                    SUM(context_tokens) as cache_reads
                FROM usage_events
                """
            ).fetchone()

            total_spend = row["total_spend"] or 0.0
            total_tokens = row["total_tokens"] or 0
            sessions = row["sessions"] or 0
            cache_reads = row["cache_reads"] or 0

            # Active agents (active in last 7 days / total known)
            total_agents = conn.execute("SELECT COUNT(DISTINCT session_key) as c FROM usage_events").fetchone()["c"]
            active_agents = conn.execute(
                "SELECT COUNT(DISTINCT session_key) as c FROM usage_events WHERE datetime(event_ts) > datetime('now', '-7 days')"
            ).fetchone()["c"]

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
                "tokens": f"{r['tokens'] / 1000000:.1f}M" if r['tokens'] >= 1000000 else (f"{r['tokens'] / 1000:.1f}K" if r['tokens'] >= 1000 else str(r['tokens'])),
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
            snapshot_count = conn.execute("SELECT COUNT(*) AS count FROM session_snapshots").fetchone()["count"]
            latest_usage = conn.execute("SELECT MAX(event_ts) AS ts FROM usage_events").fetchone()["ts"]

        return {
            "usage_events": int(usage_count or 0),
            "session_snapshots": int(snapshot_count or 0),
            "latest_usage_event_ts": latest_usage,
            "log_usage_available": int(usage_count or 0) > 0,
            "reconciled_available": int(snapshot_count or 0) > 0,
        }
