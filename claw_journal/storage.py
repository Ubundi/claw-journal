from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Iterable

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
                    cost_source TEXT NOT NULL DEFAULT 'missing',
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

                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    agent_id TEXT,
                    turn_index INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    message_ts TEXT,
                    model TEXT,
                    text_content TEXT,
                    has_thinking INTEGER NOT NULL DEFAULT 0,
                    has_tool_use INTEGER NOT NULL DEFAULT 0,
                    has_tool_result INTEGER NOT NULL DEFAULT 0,
                    content_json TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    event_fingerprint TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_conv_messages_session ON conversation_messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_conv_messages_ts ON conversation_messages(message_ts);
                CREATE INDEX IF NOT EXISTS idx_conv_messages_role ON conversation_messages(role);
                CREATE INDEX IF NOT EXISTS idx_conv_messages_agent ON conversation_messages(agent_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_conv_messages_fingerprint
                    ON conversation_messages(event_fingerprint) WHERE event_fingerprint IS NOT NULL;

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

            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(usage_events)").fetchall()
            }
            if "cost_source" not in columns:
                conn.execute(
                    "ALTER TABLE usage_events ADD COLUMN cost_source TEXT NOT NULL DEFAULT 'missing'"
                )
            if "event_fingerprint" not in columns:
                conn.execute("ALTER TABLE usage_events ADD COLUMN event_fingerprint TEXT")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_events_fingerprint ON usage_events(event_fingerprint) WHERE event_fingerprint IS NOT NULL"
            )

            # Migrate thinking_blocks: add following_tool_names
            tb_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(thinking_blocks)").fetchall()
            }
            if "following_tool_names" not in tb_columns:
                conn.execute(
                    "ALTER TABLE thinking_blocks ADD COLUMN following_tool_names TEXT"
                )

            # Migrate tool_invocations: add is_subagent
            ti_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(tool_invocations)").fetchall()
            }
            if "is_subagent" not in ti_columns:
                conn.execute(
                    "ALTER TABLE tool_invocations ADD COLUMN is_subagent INTEGER NOT NULL DEFAULT 0"
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
                    cost_source,
                    duration_ms,
                    reasoning_text,
                    raw_json,
                    event_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    # ── Conversation messages ──────────────────────────────────────────

    def get_message_count_for_session(self, session_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM conversation_messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row["cnt"]) if row else 0

    def insert_conversation_messages(
        self, messages: list[ConversationMessage]
    ) -> list[int | None]:
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

    def get_session_list_with_transcript_info(self, limit: int = 100) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    session_id,
                    agent_id,
                    COUNT(*) AS message_count,
                    SUM(has_thinking) AS thinking_count,
                    SUM(has_tool_use) AS tool_use_count,
                    MIN(message_ts) AS first_message_ts,
                    MAX(message_ts) AS last_message_ts,
                    MAX(model) AS model
                FROM conversation_messages
                GROUP BY session_id
                ORDER BY last_message_ts DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()

        return [dict(row) for row in rows]

    # ── Thinking blocks ────────────────────────────────────────────────

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

    # ── Tool invocations ───────────────────────────────────────────────

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

    # ── Model change events ────────────────────────────────────────────

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

    def get_tool_detail(self, tool_name: str, limit: int = 100) -> list[dict]:
        """Get tool invocations joined with the thinking block from the same message."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ti.id, ti.session_id, ti.agent_id, ti.message_id,
                       ti.tool_use_id, ti.tool_name, ti.tool_input, ti.tool_result,
                       ti.invocation_ts, ti.is_error, ti.is_subagent,
                       tb.thinking_text AS reasoning,
                       tb.preceding_user_text AS trigger_text
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

    # ── Annotated thinking (with tool links) ───────────────────────────

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
