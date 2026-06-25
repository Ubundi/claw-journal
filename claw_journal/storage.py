from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from .models import DailyUsageRow, NormalizedUsageEvent, SessionUsageRow
from .transcript_models import ConversationMessage, ModelChangeEvent, ThinkingBlock, ToolInvocation

logger = logging.getLogger(__name__)


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
                    event_ts TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL,
                    content_text TEXT,
                    text_content TEXT,
                    message_type TEXT,
                    source TEXT NOT NULL DEFAULT 'transcript',
                    source_path TEXT,
                    raw_json TEXT NOT NULL,
                    message_fingerprint TEXT,
                    event_fingerprint TEXT,
                    content_json TEXT NOT NULL DEFAULT '',
                    provider TEXT,
                    model TEXT,
                    message_ts TEXT,
                    turn_index INTEGER NOT NULL DEFAULT 0,
                    agent_id TEXT,
                    has_thinking INTEGER NOT NULL DEFAULT 0,
                    has_tool_use INTEGER NOT NULL DEFAULT 0,
                    has_tool_result INTEGER NOT NULL DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_conv_messages_session ON conversation_messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_conv_messages_ts ON conversation_messages(message_ts);
                CREATE INDEX IF NOT EXISTS idx_conv_messages_role ON conversation_messages(role);
                CREATE INDEX IF NOT EXISTS idx_conv_messages_agent ON conversation_messages(agent_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_conv_messages_fingerprint
                    ON conversation_messages(event_fingerprint) WHERE event_fingerprint IS NOT NULL;
                CREATE UNIQUE INDEX IF NOT EXISTS idx_conversation_messages_fingerprint
                    ON conversation_messages(message_fingerprint) WHERE message_fingerprint IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_conversation_messages_session_ts
                    ON conversation_messages(session_id, event_ts);
                CREATE INDEX IF NOT EXISTS idx_conversation_messages_source_path
                    ON conversation_messages(source_path);

                CREATE TABLE IF NOT EXISTS thinking_blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    agent_id TEXT,
                    message_id INTEGER NOT NULL,
                    block_index INTEGER NOT NULL,
                    thinking_text TEXT NOT NULL,
                    thinking_ts TEXT,
                    model TEXT,
                    preceding_user_text TEXT,
                    following_tool_names TEXT,
                    FOREIGN KEY (message_id) REFERENCES conversation_messages(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_thinking_session ON thinking_blocks(session_id);
                CREATE INDEX IF NOT EXISTS idx_thinking_ts ON thinking_blocks(thinking_ts);
                CREATE INDEX IF NOT EXISTS idx_thinking_message ON thinking_blocks(message_id);

                CREATE TABLE IF NOT EXISTS tool_invocations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    agent_id TEXT,
                    message_id INTEGER NOT NULL,
                    tool_use_id TEXT,
                    tool_name TEXT NOT NULL,
                    tool_input TEXT,
                    tool_result TEXT,
                    result_message_id INTEGER,
                    invocation_ts TEXT,
                    is_error INTEGER NOT NULL DEFAULT 0,
                    is_subagent INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (message_id) REFERENCES conversation_messages(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_tool_inv_session ON tool_invocations(session_id);
                CREATE INDEX IF NOT EXISTS idx_tool_inv_name ON tool_invocations(tool_name);
                CREATE INDEX IF NOT EXISTS idx_tool_inv_ts ON tool_invocations(invocation_ts);
                CREATE INDEX IF NOT EXISTS idx_tool_inv_use_id ON tool_invocations(tool_use_id);

                CREATE TABLE IF NOT EXISTS model_change_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    agent_id TEXT,
                    event_id TEXT,
                    timestamp TEXT,
                    provider TEXT,
                    model_id TEXT,
                    raw_json TEXT NOT NULL,
                    event_fingerprint TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_model_change_session ON model_change_events(session_id);
                CREATE INDEX IF NOT EXISTS idx_model_change_ts ON model_change_events(timestamp);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_model_change_fingerprint
                    ON model_change_events(event_fingerprint) WHERE event_fingerprint IS NOT NULL;
                """
            )

            # FTS5 virtual table for full-text search (may not be available)
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS conversation_messages_fts
                    USING fts5(text_content, session_id, role,
                               content='conversation_messages', content_rowid='id')
                    """
                )
                conn.executescript(
                    """
                    CREATE TRIGGER IF NOT EXISTS conv_messages_ai AFTER INSERT ON conversation_messages BEGIN
                        INSERT INTO conversation_messages_fts(rowid, text_content, session_id, role)
                        VALUES (new.id, new.text_content, new.session_id, new.role);
                    END;

                    CREATE TRIGGER IF NOT EXISTS conv_messages_ad AFTER DELETE ON conversation_messages BEGIN
                        INSERT INTO conversation_messages_fts(conversation_messages_fts, rowid, text_content, session_id, role)
                        VALUES ('delete', old.id, old.text_content, old.session_id, old.role);
                    END;
                    """
                )
                self._fts_available = True
            except sqlite3.OperationalError:
                logger.warning("FTS5 not available; full-text search will be disabled")
                self._fts_available = False

            # ── Migrate usage_events ──────────────────────────────────────
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

            # ── Migrate conversation_messages ─────────────────────────────
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
            if convo_columns and "has_thinking" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN has_thinking INTEGER NOT NULL DEFAULT 0")
            if convo_columns and "has_tool_use" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN has_tool_use INTEGER NOT NULL DEFAULT 0")
            if convo_columns and "has_tool_result" not in convo_columns:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN has_tool_result INTEGER NOT NULL DEFAULT 0")

            # ── Migrate thinking_blocks ───────────────────────────────────
            tb_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(thinking_blocks)").fetchall()
            }
            if "following_tool_names" not in tb_columns:
                conn.execute(
                    "ALTER TABLE thinking_blocks ADD COLUMN following_tool_names TEXT"
                )

            # ── Migrate tool_invocations ──────────────────────────────────
            ti_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(tool_invocations)").fetchall()
            }
            if "is_subagent" not in ti_columns:
                conn.execute(
                    "ALTER TABLE tool_invocations ADD COLUMN is_subagent INTEGER NOT NULL DEFAULT 0"
                )

    # ══════════════════════════════════════════════════════════════════
    # Usage events
    # ══════════════════════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════════════════════
    # Checkpoints
    # ══════════════════════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════════════════════
    # Session snapshots
    # ══════════════════════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════════════════════
    # Dashboard & analytics (dev)
    # ══════════════════════════════════════════════════════════════════

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

            cache_hit_pct = "0%"
            if total_tokens > 0:
                pct = (cache_reads / total_tokens) * 100
                cache_hit_pct = f"{pct:.1f}%"

            return {
                "totalSpend": round(total_spend, 2),
                "totalTokens": f"{total_tokens / 1000000:.1f}M" if total_tokens >= 1000000 else (f"{total_tokens / 1000:.1f}K" if total_tokens >= 1000 else str(total_tokens)),
                "sessions": sessions,
                "activeAgents": f"{active_agents}/{total_agents}",
                "avgSession": round(avg_session_cost, 2),
                "cacheHit": cache_hit_pct,
                "cacheReads": f"{cache_reads / 1000000:.1f}M" if cache_reads >= 1000000 else (f"{cache_reads / 1000:.1f}K" if cache_reads >= 1000 else str(cache_reads)),
                "cacheCost": 0.0,
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
                    session_key,
                    SUM(COALESCE(cost_usd, 0.0)) as cost,
                    MAX(event_ts) as last_event_ts
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
                        session_key,
                        0.0 as cost,
                        datetime(updated_at / 1000, 'unixepoch') as last_event_ts
                    FROM session_snapshots
                    WHERE session_key IS NOT NULL
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,)
                ).fetchall()

        data = []
        for r in rows:
            session_key = str(r["session_key"] or "unknown")

            agent_name = session_key
            conversation_name = "default"
            if session_key.startswith("agent:"):
                parts = session_key.split(":")
                if len(parts) > 1:
                    agent_name = parts[1].replace("_", " ").title()
                if len(parts) > 2:
                    conversation_name = ":".join(parts[2:]).replace("_", " ")

            event_ts_raw = str(r["last_event_ts"] or "")
            event_date = "-"
            try:
                event_date = datetime.fromisoformat(event_ts_raw.replace("Z", "+00:00")).strftime("%Y-%m-%d")
            except ValueError:
                if len(event_ts_raw) >= 10:
                    event_date = event_ts_raw[:10]

            label = f"{agent_name} \u00b7 {conversation_name} \u00b7 {event_date}"
            data.append({"name": label, "cost": r["cost"] or 0.0})
        return data

    def get_top_tools(self, limit: int = 5) -> list[dict]:
        tool_counter: Counter[str] = Counter()
        activity_counter: Counter[str] = Counter()

        with self._connect() as conn:
            usage_rows = conn.execute(
                """
                SELECT event_type as name, COUNT(*) as count
                FROM usage_events
                WHERE event_type LIKE 'tool.%' OR event_type LIKE 'tool:%' OR event_type LIKE 'tool_%'
                GROUP BY event_type
                ORDER BY count DESC
                LIMIT 100
                """,
            ).fetchall()

            transcript_rows = conn.execute(
                """
                SELECT message_type, role, content_text, raw_json
                FROM conversation_messages
                WHERE (raw_json IS NOT NULL AND raw_json != '')
                   OR (content_text IS NOT NULL AND content_text != '')
                   OR (message_type IS NOT NULL AND message_type != '')
                   OR (role IS NOT NULL AND role != '')
                ORDER BY id DESC
                LIMIT 12000
                """
            ).fetchall()

        for row in usage_rows:
            raw_name = str(row["name"] or "").strip()
            if not raw_name:
                continue
            normalized = raw_name
            if raw_name.startswith("tool."):
                normalized = raw_name.split("tool.", 1)[1]
            elif raw_name.startswith("tool:"):
                normalized = raw_name.split("tool:", 1)[1]
            elif raw_name.startswith("tool_"):
                normalized = raw_name.split("tool_", 1)[1]
            if normalized:
                tool_counter[normalized] += int(row["count"] or 0)

        for row in transcript_rows:
            raw_json = row["raw_json"]
            content_text = str(row["content_text"] or "")
            message_type = str(row["message_type"] or "").strip().lower()
            role = str(row["role"] or "").strip().lower()

            extracted_tools = _extract_tool_names_from_raw_json(raw_json)
            extracted_tools.extend(_extract_tool_names_from_text(content_text))
            for tool_name in extracted_tools:
                tool_counter[tool_name] += 1

            if message_type == "toolcall":
                activity_counter["tool calls"] += 1
            elif message_type == "toolresult":
                activity_counter["tool results"] += 1
            elif message_type == "thinking":
                activity_counter["thinking blocks"] += 1
            elif role == "assistant":
                activity_counter["assistant messages"] += 1
            elif role == "user":
                activity_counter["user messages"] += 1

        if tool_counter:
            top = tool_counter.most_common(max(1, int(limit)))
            return [{"name": f"tool:{name}", "count": count} for name, count in top]

        if activity_counter:
            top = activity_counter.most_common(max(1, int(limit)))
            return [{"name": name, "count": count} for name, count in top]

        if not tool_counter and not activity_counter:
            with self._connect() as conn:
                fallback_rows = conn.execute(
                    """
                    SELECT event_type as name, COUNT(*) as count
                    FROM usage_events
                    GROUP BY event_type
                    ORDER BY count DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
            return [{"name": str(row["name"] or "unknown"), "count": int(row["count"] or 0)} for row in fallback_rows]

        return []

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

    def get_user_prompts_by_day(self, days: int = 7) -> list[dict[str, int | str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    DATE(COALESCE(NULLIF(event_ts, ''), message_ts)) AS usage_date,
                    COUNT(*) AS prompt_count
                FROM conversation_messages
                WHERE (
                    LOWER(TRIM(COALESCE(role, ''))) = 'user'
                    OR LOWER(COALESCE(raw_json, '')) LIKE '%"role":"user"%'
                    OR LOWER(COALESCE(raw_json, '')) LIKE '%"role": "user"%'
                )
                  AND DATE(COALESCE(NULLIF(event_ts, ''), message_ts)) >= DATE('now', ?)
                GROUP BY DATE(COALESCE(NULLIF(event_ts, ''), message_ts))
                ORDER BY usage_date ASC
                """,
                (f"-{int(days)} days",),
            ).fetchall()

        return [
            {
                "date": str(row["usage_date"] or ""),
                "count": int(row["prompt_count"] or 0),
            }
            for row in rows
            if row["usage_date"]
        ]

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

    # ══════════════════════════════════════════════════════════════════
    # Conversation messages (dev chat browser)
    # ══════════════════════════════════════════════════════════════════

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

            first_user_rows = conn.execute(
                """
                SELECT
                    COALESCE(NULLIF(source_path, ''), session_id) AS session_group,
                    COALESCE(NULLIF(content_text, ''), text_content, '') AS content_text
                FROM conversation_messages
                WHERE role = 'user'
                    AND COALESCE(NULLIF(content_text, ''), text_content, '') != ''
                ORDER BY id ASC
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

        first_user_text_by_group: dict[str, str] = {}
        for row in first_user_rows:
            session_group = str(row["session_group"] or "")
            if not session_group or session_group in first_user_text_by_group:
                continue
            text_value = str(row["content_text"] or "").strip()
            if text_value:
                first_user_text_by_group[session_group] = text_value

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
                    "display_title": _session_display_title(
                        first_user_text_by_group.get(session_group),
                        canonical_session_id,
                    ),
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

    def search_chat_messages(self, query: str, limit: int = 200) -> dict:
        normalized = str(query or "").strip()
        if len(normalized) < 2:
            return {"query": normalized, "rows": [], "sessions": []}

        pattern = f"%{normalized}%"

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    session_id,
                    source_path,
                    COALESCE(NULLIF(event_ts, ''), message_ts) AS event_ts,
                    role,
                    COALESCE(NULLIF(content_text, ''), text_content) AS content_text,
                    message_type,
                    provider,
                    model,
                    raw_json
                FROM conversation_messages
                WHERE
                    COALESCE(NULLIF(content_text, ''), text_content, '') LIKE ?
                    OR raw_json LIKE ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (pattern, pattern, int(limit)),
            ).fetchall()

        result_rows: list[dict] = []
        sessions_seen: set[str] = set()
        session_rows: list[dict] = []

        for row in rows:
            canonical_sid = _canonical_session_id(
                session_id=str(row["session_id"] or "unknown"),
                source_path=row["source_path"],
            )

            message_row = {
                "id": int(row["id"]),
                "session_id": canonical_sid,
                "event_ts": row["event_ts"],
                "role": row["role"],
                "content_text": row["content_text"],
                "message_type": row["message_type"],
                "provider": row["provider"],
                "model": row["model"],
                "source_path": row["source_path"],
                "raw_json": row["raw_json"],
            }
            result_rows.append(message_row)

            if canonical_sid not in sessions_seen:
                sessions_seen.add(canonical_sid)
                session_rows.append(
                    {
                        "session_id": canonical_sid,
                        "provider": row["provider"],
                        "model": row["model"],
                        "last_event_ts": row["event_ts"],
                    }
                )

        return {
            "query": normalized,
            "rows": result_rows,
            "sessions": session_rows,
        }

    # ══════════════════════════════════════════════════════════════════
    # Conversation messages (reasoning / transcript-based)
    # ══════════════════════════════════════════════════════════════════

    def get_message_count_for_session(self, session_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM conversation_messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row["cnt"]) if row else 0

    def insert_conversation_messages(self, messages):
        """Unified dispatcher: accepts either list[ConversationMessage] or list[dict]."""
        if not messages:
            return [] if isinstance(messages, list) and len(messages) > 0 and hasattr(messages[0] if messages else None, 'session_id') else 0
        if messages and hasattr(messages[0], 'session_id') and hasattr(messages[0], 'turn_index'):
            return self._insert_conversation_messages_typed(messages)
        return self._insert_conversation_messages_dict(messages)

    def _insert_conversation_messages_typed(
        self, messages: list[ConversationMessage]
    ) -> list[int | None]:
        """Insert ConversationMessage dataclass instances (reasoning branch)."""
        if not messages:
            return []

        inserted_ids: list[int | None] = []
        with self._connect() as conn:
            for msg in messages:
                try:
                    cursor = conn.execute(
                        """
                        INSERT OR IGNORE INTO conversation_messages (
                            session_id, agent_id, turn_index, role, message_ts, model,
                            text_content, has_thinking, has_tool_use, has_tool_result,
                            content_json, raw_json, event_fingerprint
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            msg.session_id,
                            msg.agent_id,
                            msg.turn_index,
                            msg.role,
                            msg.message_ts,
                            msg.model,
                            msg.text_content,
                            int(msg.has_thinking),
                            int(msg.has_tool_use),
                            int(msg.has_tool_result),
                            msg.content_json,
                            msg.raw_json,
                            msg.event_fingerprint,
                        ),
                    )
                    if cursor.rowcount > 0:
                        inserted_ids.append(cursor.lastrowid)
                    else:
                        inserted_ids.append(None)
                except sqlite3.IntegrityError:
                    inserted_ids.append(None)
        return inserted_ids

    def _insert_conversation_messages_dict(self, messages: list[dict]) -> int:
        """Insert dict-based conversation messages (dev branch)."""
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

    # ══════════════════════════════════════════════════════════════════
    # Thinking blocks (reasoning)
    # ══════════════════════════════════════════════════════════════════

    def insert_thinking_blocks(self, blocks: list[ThinkingBlock]) -> int:
        if not blocks:
            return 0

        rows = [
            (
                b.session_id,
                b.agent_id,
                b.message_id,
                b.block_index,
                b.thinking_text,
                b.thinking_ts,
                b.model,
                b.preceding_user_text,
                b.following_tool_names,
            )
            for b in blocks
        ]

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO thinking_blocks (
                    session_id, agent_id, message_id, block_index,
                    thinking_text, thinking_ts, model, preceding_user_text,
                    following_tool_names
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def get_thinking_blocks(
        self, session_id: str | None = None, limit: int = 100
    ) -> list[dict]:
        params: list[object] = []
        where = ""
        if session_id:
            where = "WHERE t.session_id = ?"
            params.append(session_id)
        params.append(int(limit))

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT t.id, t.session_id, t.agent_id, t.block_index,
                       t.thinking_text, t.thinking_ts, t.model,
                       t.preceding_user_text, t.message_id,
                       t.following_tool_names
                FROM thinking_blocks t
                {where}
                ORDER BY t.thinking_ts DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        return [dict(row) for row in rows]

    def get_session_thinking(self, session_id: str, limit: int = 100) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT t.id, t.session_id, t.block_index,
                       t.thinking_text, t.thinking_ts, t.model,
                       t.preceding_user_text, t.message_id,
                       t.following_tool_names,
                       c.turn_index
                FROM thinking_blocks t
                JOIN conversation_messages c ON c.id = t.message_id
                WHERE t.session_id = ?
                ORDER BY c.turn_index ASC, t.block_index ASC
                LIMIT ?
                """,
                (session_id, int(limit)),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_annotated_thinking(
        self, session_id: str | None = None, limit: int = 100
    ) -> list[dict]:
        params: list[object] = []
        where = ""
        if session_id:
            where = "WHERE t.session_id = ?"
            params.append(session_id)
        params.append(int(limit))

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT t.id, t.session_id, t.agent_id, t.block_index,
                       t.thinking_text, t.thinking_ts, t.model,
                       t.preceding_user_text, t.message_id,
                       t.following_tool_names
                FROM thinking_blocks t
                {where}
                ORDER BY t.thinking_ts DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        return [dict(row) for row in rows]

    # ══════════════════════════════════════════════════════════════════
    # Tool invocations (reasoning)
    # ══════════════════════════════════════════════════════════════════

    def insert_tool_invocations(self, invocations: list[ToolInvocation]) -> int:
        if not invocations:
            return 0

        rows = [
            (
                inv.session_id,
                inv.agent_id,
                inv.message_id,
                inv.tool_use_id,
                inv.tool_name,
                inv.tool_input,
                inv.tool_result,
                inv.result_message_id,
                inv.invocation_ts,
                int(inv.is_error),
                int(inv.is_subagent),
            )
            for inv in invocations
        ]

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO tool_invocations (
                    session_id, agent_id, message_id, tool_use_id, tool_name,
                    tool_input, tool_result, result_message_id, invocation_ts, is_error,
                    is_subagent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def update_tool_result(
        self, tool_use_id: str, tool_result: str, result_message_id: int, is_error: bool
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE tool_invocations
                SET tool_result = ?, result_message_id = ?, is_error = ?
                WHERE tool_use_id = ? AND tool_result IS NULL
                """,
                (tool_result, result_message_id, int(is_error), tool_use_id),
            )

    def get_tool_invocations(
        self,
        session_id: str | None = None,
        tool_name: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        params: list[object] = []
        where_parts = []
        if session_id:
            where_parts.append("session_id = ?")
            params.append(session_id)
        if tool_name:
            where_parts.append("tool_name = ?")
            params.append(tool_name)

        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
        params.append(int(limit))

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, session_id, agent_id, message_id, tool_use_id,
                       tool_name, tool_input, tool_result, result_message_id,
                       invocation_ts, is_error, is_subagent
                FROM tool_invocations
                {where}
                ORDER BY invocation_ts DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        return [dict(row) for row in rows]

    def get_tool_usage_summary(self, session_id: str | None = None) -> list[dict]:
        params: list[object] = []
        where = ""
        if session_id:
            where = "WHERE session_id = ?"
            params.append(session_id)

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT tool_name,
                       COUNT(*) AS invocation_count,
                       SUM(is_error) AS error_count,
                       SUM(is_subagent) AS subagent_count
                FROM tool_invocations
                {where}
                GROUP BY tool_name
                ORDER BY invocation_count DESC
                """,
                params,
            ).fetchall()

        return [dict(row) for row in rows]

    def get_tool_detail(self, tool_name: str, limit: int = 100) -> list[dict]:
        """Get tool invocations joined with the thinking block from the same message."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ti.id, ti.session_id, ti.agent_id, ti.message_id,
                       ti.tool_use_id, ti.tool_name, ti.tool_input, ti.tool_result,
                       ti.invocation_ts, ti.is_error, ti.is_subagent,
                       tb.thinking_text AS reasoning,
                       tb.preceding_user_text AS trigger_text,
                       (SELECT SUBSTR(c2.text_content, 1, 120)
                        FROM conversation_messages c2
                        WHERE c2.session_id = ti.session_id
                          AND c2.role = 'user'
                          AND c2.text_content IS NOT NULL
                          AND c2.text_content != ''
                        ORDER BY COALESCE(NULLIF(c2.event_ts, ''), c2.message_ts) ASC
                        LIMIT 1) AS session_title
                FROM tool_invocations ti
                LEFT JOIN thinking_blocks tb ON tb.message_id = ti.message_id
                WHERE ti.tool_name = ?
                GROUP BY ti.id
                ORDER BY ti.invocation_ts DESC
                LIMIT ?
                """,
                (tool_name, int(limit)),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_distinct_tool_names(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT tool_name FROM tool_invocations ORDER BY tool_name"
            ).fetchall()
        return [row["tool_name"] for row in rows]

    def get_sessions_filtered_by_tool(
        self, tool_name: str, limit: int = 100, date: str | None = None,
    ) -> list[dict]:
        params: list[object] = [tool_name]
        having = ""
        if date:
            having = "HAVING DATE(last_message_ts) = ?"
            params.append(date)
        params.append(int(limit))

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    cm.session_id,
                    cm.agent_id,
                    COUNT(DISTINCT cm.id) AS message_count,
                    SUM(cm.has_thinking) AS thinking_count,
                    SUM(cm.has_tool_use) AS tool_use_count,
                    MIN(COALESCE(NULLIF(cm.event_ts, ''), cm.message_ts)) AS first_message_ts,
                    MAX(COALESCE(NULLIF(cm.event_ts, ''), cm.message_ts)) AS last_message_ts,
                    MAX(cm.model) AS model,
                    (SELECT SUBSTR(c2.text_content, 1, 120)
                     FROM conversation_messages c2
                     WHERE c2.session_id = cm.session_id
                       AND c2.role = 'user'
                       AND c2.text_content IS NOT NULL
                       AND c2.text_content != ''
                     ORDER BY COALESCE(NULLIF(c2.event_ts, ''), c2.message_ts) ASC
                     LIMIT 1) AS display_title,
                    (SELECT SUBSTR(c3.text_content, 1, 120)
                     FROM conversation_messages c3
                     WHERE c3.session_id = cm.session_id
                       AND c3.role = 'assistant'
                       AND c3.text_content IS NOT NULL
                       AND c3.text_content != ''
                     ORDER BY COALESCE(NULLIF(c3.event_ts, ''), c3.message_ts) ASC
                     LIMIT 1) AS assistant_title
                FROM conversation_messages cm
                WHERE cm.session_id IN (
                    SELECT DISTINCT session_id FROM tool_invocations WHERE tool_name = ?
                )
                GROUP BY cm.session_id
                {having}
                ORDER BY last_message_ts DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    # ══════════════════════════════════════════════════════════════════
    # Model change events (reasoning)
    # ══════════════════════════════════════════════════════════════════

    def insert_model_change_events(self, events: list[ModelChangeEvent]) -> int:
        if not events:
            return 0

        rows = [
            (
                e.session_id,
                e.agent_id,
                e.event_id,
                e.timestamp,
                e.provider,
                e.model_id,
                e.raw_json,
                e.event_fingerprint,
            )
            for e in events
        ]

        with self._connect() as conn:
            before = conn.total_changes
            conn.executemany(
                """
                INSERT OR IGNORE INTO model_change_events (
                    session_id, agent_id, event_id, timestamp, provider,
                    model_id, raw_json, event_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            return conn.total_changes - before

    def get_model_changes(
        self, session_id: str | None = None, limit: int = 100
    ) -> list[dict]:
        params: list[object] = []
        where = ""
        if session_id:
            where = "WHERE session_id = ?"
            params.append(session_id)
        params.append(int(limit))

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, session_id, agent_id, event_id, timestamp,
                       provider, model_id
                FROM model_change_events
                {where}
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        return [dict(row) for row in rows]

    def get_session_model_timeline(self, session_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, provider, model_id
                FROM model_change_events
                WHERE session_id = ?
                ORDER BY timestamp ASC
                """,
                (session_id,),
            ).fetchall()

        return [dict(row) for row in rows]

    # ══════════════════════════════════════════════════════════════════
    # Search (reasoning FTS5 + LIKE fallback)
    # ══════════════════════════════════════════════════════════════════

    def search_conversations(
        self,
        query: str,
        session_id: str | None = None,
        role: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        if not query.strip() or not getattr(self, "_fts_available", False):
            return self._search_conversations_like(query, session_id, role, limit, offset)

        params: list[object] = [query]
        where_parts = []
        if session_id:
            where_parts.append("c.session_id = ?")
            params.append(session_id)
        if role:
            where_parts.append("c.role = ?")
            params.append(role)

        extra_where = (" AND " + " AND ".join(where_parts)) if where_parts else ""
        params.extend([int(limit), int(offset)])

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT c.id, c.session_id, c.agent_id, c.turn_index, c.role,
                       c.message_ts, c.model,
                       highlight(conversation_messages_fts, 0, '<mark>', '</mark>') AS snippet,
                       c.has_thinking, c.has_tool_use
                FROM conversation_messages_fts fts
                JOIN conversation_messages c ON c.id = fts.rowid
                WHERE fts.text_content MATCH ?{extra_where}
                ORDER BY fts.rank
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()

        return [dict(row) for row in rows]

    def _search_conversations_like(
        self,
        query: str,
        session_id: str | None,
        role: str | None,
        limit: int,
        offset: int,
    ) -> list[dict]:
        params: list[object] = []
        where_parts = []

        if query.strip():
            where_parts.append("text_content LIKE ?")
            params.append(f"%{query}%")
        if session_id:
            where_parts.append("session_id = ?")
            params.append(session_id)
        if role:
            where_parts.append("role = ?")
            params.append(role)

        where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
        params.extend([int(limit), int(offset)])

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, session_id, agent_id, turn_index, role,
                       message_ts, model, text_content AS snippet,
                       has_thinking, has_tool_use
                FROM conversation_messages
                {where_clause}
                ORDER BY message_ts DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()

        return [dict(row) for row in rows]

    def get_session_conversation(self, session_id: str, limit: int = 200) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, agent_id, turn_index, role, message_ts, model,
                       text_content, has_thinking, has_tool_use, has_tool_result,
                       content_json
                FROM conversation_messages
                WHERE session_id = ?
                ORDER BY turn_index ASC
                LIMIT ?
                """,
                (session_id, int(limit)),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_session_list_with_transcript_info(
        self, limit: int = 100, date: str | None = None,
    ) -> list[dict]:
        params: list[object] = []
        having = ""
        if date:
            having = "HAVING DATE(last_message_ts) = ?"
            params.append(date)
        params.append(int(limit))

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    session_id,
                    agent_id,
                    COUNT(*) AS message_count,
                    SUM(has_thinking) AS thinking_count,
                    SUM(has_tool_use) AS tool_use_count,
                    MIN(COALESCE(NULLIF(event_ts, ''), message_ts)) AS first_message_ts,
                    MAX(COALESCE(NULLIF(event_ts, ''), message_ts)) AS last_message_ts,
                    MAX(model) AS model,
                    MAX(source_path) AS source_path,
                    (SELECT SUBSTR(c2.text_content, 1, 120)
                     FROM conversation_messages c2
                     WHERE c2.session_id = conversation_messages.session_id
                       AND c2.role = 'user'
                       AND c2.text_content IS NOT NULL
                       AND c2.text_content != ''
                     ORDER BY COALESCE(NULLIF(c2.event_ts, ''), c2.message_ts) ASC
                     LIMIT 1) AS display_title,
                    (SELECT SUBSTR(c3.text_content, 1, 120)
                     FROM conversation_messages c3
                     WHERE c3.session_id = conversation_messages.session_id
                       AND c3.role = 'assistant'
                       AND c3.text_content IS NOT NULL
                       AND c3.text_content != ''
                     ORDER BY COALESCE(NULLIF(c3.event_ts, ''), c3.message_ts) ASC
                     LIMIT 1) AS assistant_title
                FROM conversation_messages
                GROUP BY session_id
                {having}
                ORDER BY last_message_ts DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        return [dict(row) for row in rows]

    def get_tootoo_reviews(self, limit: int = 1000) -> list[dict]:
        """Return TooToo sessions with their alignment feedback content_json."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    cm.session_id,
                    cm.message_ts,
                    cm.model,
                    cm.content_json,
                    cm.source_path
                FROM conversation_messages cm
                WHERE cm.role = 'assistant'
                                    AND (
                                        LOWER(COALESCE(cm.agent_id, '')) = 'tootoo'
                                        OR cm.source_path LIKE '%/agents/tootoo/%'
                                    )
                  AND cm.content_json LIKE '%alignment_score%'
                ORDER BY cm.message_ts DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()

        return [dict(row) for row in rows]


# ══════════════════════════════════════════════════════════════════════
# Module-level helpers (dev)
# ══════════════════════════════════════════════════════════════════════


def _canonical_session_id(session_id: str, source_path: object) -> str:
    if isinstance(source_path, str) and source_path.strip():
        stem = Path(source_path).stem
        if stem:
            return stem
    return session_id or "unknown"


def _session_display_title(first_user_text: str | None, fallback: str) -> str:
    text = " ".join(str(first_user_text or "").split()).strip()
    if not text:
        return fallback
    if len(text) <= 72:
        return text
    return f"{text[:69].rstrip()}..."


def _extract_tool_names_from_raw_json(raw_json: object) -> list[str]:
    if not isinstance(raw_json, str) or not raw_json.strip():
        return []

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return []

    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict):
        return []

    content = message.get("content")
    if not isinstance(content, list):
        return []

    names: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").lower()
        if item_type == "toolcall":
            name = str(item.get("name") or "").strip()
            if name:
                names.append(name)
        elif item_type == "toolresult":
            name = str(item.get("toolName") or item.get("name") or "").strip()
            if name:
                names.append(name)
    return names


def _extract_tool_names_from_text(content_text: object) -> list[str]:
    if not isinstance(content_text, str) or not content_text.strip():
        return []

    text = content_text.strip()
    matches: list[str] = []

    patterns = [
        r"toolcall\s*[\u00b7:\-]\s*([A-Za-z0-9._/\-]+)",
        r"tool\s*[.:]\s*([A-Za-z0-9._/\-]+)",
    ]

    for pattern in patterns:
        for raw_name in re.findall(pattern, text, flags=re.IGNORECASE):
            clean_name = str(raw_name or "").strip().lower()
            if clean_name:
                matches.append(clean_name)

    return matches
