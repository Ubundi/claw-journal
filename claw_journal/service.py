from __future__ import annotations

from .storage import UsageRepository


class UsageService:
    def __init__(self, repository: UsageRepository) -> None:
        self._repository = repository

    def daily_usage(self, days: int = 30) -> list[dict]:
        return [row.__dict__ for row in self._repository.get_daily_usage(days=days)]

    def session_usage(self, limit: int = 100) -> list[dict]:
        return [row.__dict__ for row in self._repository.get_session_usage(limit=limit)]

    def reasoning_events(self, limit: int = 100) -> list[dict]:
        return self._repository.get_reasoning_events(limit=limit)

    def reconciled_session_usage(self, limit: int = 100) -> list[dict]:
        return self._repository.get_reconciled_session_usage(limit=limit)

    def cost_source_summary(self) -> dict:
        return self._repository.get_cost_source_summary()

    # ── Conversation logs ──────────────────────────────────────────────

    def search_conversations(
        self,
        query: str,
        session_id: str | None = None,
        role: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        return self._repository.search_conversations(query, session_id, role, limit, offset)

    def session_conversation(self, session_id: str, limit: int = 200) -> list[dict]:
        return self._repository.get_session_conversation(session_id, limit)

    def sessions_with_transcripts(self, limit: int = 100, date: str | None = None) -> list[dict]:
        return self._repository.get_session_list_with_transcript_info(limit, date=date)

    def sessions_filtered_by_tool(self, tool_name: str, limit: int = 100, date: str | None = None) -> list[dict]:
        return self._repository.get_sessions_filtered_by_tool(tool_name, limit, date=date)

    def distinct_tool_names(self) -> list[str]:
        return self._repository.get_distinct_tool_names()

    # ── Thinking blocks ────────────────────────────────────────────────

    def thinking_blocks(self, session_id: str | None = None, limit: int = 100) -> list[dict]:
        return self._repository.get_thinking_blocks(session_id, limit)

    def session_thinking(self, session_id: str, limit: int = 100) -> list[dict]:
        return self._repository.get_session_thinking(session_id, limit)

    # ── Tool invocations ───────────────────────────────────────────────

    def tool_invocations(
        self,
        session_id: str | None = None,
        tool_name: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        return self._repository.get_tool_invocations(session_id, tool_name, limit)

    def tool_usage_summary(self, session_id: str | None = None) -> list[dict]:
        return self._repository.get_tool_usage_summary(session_id)

    def tool_detail(self, tool_name: str, limit: int = 100) -> list[dict]:
        return self._repository.get_tool_detail(tool_name, limit)

    # ── Model changes ──────────────────────────────────────────────────

    def model_changes(self, session_id: str | None = None, limit: int = 100) -> list[dict]:
        return self._repository.get_model_changes(session_id, limit)

    def session_model_timeline(self, session_id: str) -> list[dict]:
        return self._repository.get_session_model_timeline(session_id)

    # ── Annotated thinking (with tool links) ───────────────────────────

    def annotated_thinking(self, session_id: str | None = None, limit: int = 100) -> list[dict]:
        return self._repository.get_annotated_thinking(session_id, limit)
