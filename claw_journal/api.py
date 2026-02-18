from __future__ import annotations

from fastapi import FastAPI, Query

from .service import UsageService


def create_app(usage_service: UsageService) -> FastAPI:
    app = FastAPI(title="Claw Journal", version="0.4.0")

    # ── Health ─────────────────────────────────────────────────────────

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # ── Existing usage API ─────────────────────────────────────────────

    @app.get("/api/usage/daily")
    def daily_usage(days: int = Query(default=30, ge=1, le=365)) -> dict[str, object]:
        return {"days": days, "rows": usage_service.daily_usage(days=days)}

    @app.get("/api/usage/sessions")
    def session_usage(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        return {"limit": limit, "rows": usage_service.session_usage(limit=limit)}

    @app.get("/api/reasoning")
    def reasoning(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        return {"limit": limit, "rows": usage_service.reasoning_events(limit=limit)}

    @app.get("/api/usage/reconciled")
    def reconciled_usage(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        return {"limit": limit, "rows": usage_service.reconciled_session_usage(limit=limit)}

    @app.get("/api/usage/cost-sources")
    def cost_sources() -> dict[str, object]:
        return {"rows": usage_service.cost_source_summary()}

    # ── Conversation API ───────────────────────────────────────────────

    @app.get("/api/conversations/search")
    def search_conversations(
        q: str = Query(default=""),
        session_id: str | None = Query(default=None),
        role: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, object]:
        return {
            "query": q,
            "rows": usage_service.search_conversations(q, session_id, role, limit, offset),
        }

    @app.get("/api/conversations/{session_id}")
    def session_conversation(
        session_id: str,
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> dict[str, object]:
        return {
            "session_id": session_id,
            "rows": usage_service.session_conversation(session_id, limit),
        }

    @app.get("/api/sessions/transcripts")
    def sessions_with_transcripts(
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict[str, object]:
        return {"rows": usage_service.sessions_with_transcripts(limit)}

    # ── Thinking API ───────────────────────────────────────────────────

    @app.get("/api/thinking")
    def thinking_blocks(
        session_id: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict[str, object]:
        return {"rows": usage_service.thinking_blocks(session_id, limit)}

    @app.get("/api/thinking/annotated")
    def annotated_thinking(
        session_id: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict[str, object]:
        return {"rows": usage_service.annotated_thinking(session_id, limit)}

    @app.get("/api/thinking/{session_id}")
    def session_thinking(
        session_id: str,
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict[str, object]:
        return {
            "session_id": session_id,
            "rows": usage_service.session_thinking(session_id, limit),
        }

    # ── Tools API ──────────────────────────────────────────────────────

    @app.get("/api/tools")
    def tool_invocations(
        session_id: str | None = Query(default=None),
        tool_name: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict[str, object]:
        return {"rows": usage_service.tool_invocations(session_id, tool_name, limit)}

    @app.get("/api/tools/summary")
    def tool_usage_summary(
        session_id: str | None = Query(default=None),
    ) -> dict[str, object]:
        return {"rows": usage_service.tool_usage_summary(session_id)}

    # ── Model changes API ────────────────────────────────────────────────

    @app.get("/api/model-changes")
    def model_changes(
        session_id: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict[str, object]:
        return {"rows": usage_service.model_changes(session_id, limit)}

    @app.get("/api/model-changes/{session_id}")
    def session_model_timeline(session_id: str) -> dict[str, object]:
        return {
            "session_id": session_id,
            "rows": usage_service.session_model_timeline(session_id),
        }

    return app
