from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .service import UsageService

_PKG_DIR = Path(__file__).parent


def create_app(usage_service: UsageService) -> FastAPI:
    app = FastAPI(title="Claw Journal", version="0.2.0")

    templates = Jinja2Templates(directory=str(_PKG_DIR / "templates"))
    app.mount("/static", StaticFiles(directory=str(_PKG_DIR / "static")), name="static")

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

    # ── Web UI routes ──────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        sessions = usage_service.sessions_with_transcripts(limit=50)
        daily = usage_service.daily_usage(days=14)
        return templates.TemplateResponse(
            "dashboard.html", {"request": request, "sessions": sessions, "daily": daily}
        )

    @app.get("/conversation/{session_id}", response_class=HTMLResponse)
    def conversation_page(request: Request, session_id: str):
        messages = usage_service.session_conversation(session_id, limit=500)
        return templates.TemplateResponse(
            "conversation.html",
            {"request": request, "session_id": session_id, "messages": messages},
        )

    @app.get("/thinking", response_class=HTMLResponse)
    def thinking_page(request: Request, session_id: str | None = None):
        blocks = usage_service.thinking_blocks(session_id, limit=200)
        return templates.TemplateResponse(
            "thinking.html",
            {"request": request, "blocks": blocks, "session_id": session_id},
        )

    @app.get("/tools", response_class=HTMLResponse)
    def tools_page(
        request: Request,
        session_id: str | None = None,
        tool_name: str | None = None,
    ):
        invocations = usage_service.tool_invocations(session_id, tool_name, limit=200)
        summary = usage_service.tool_usage_summary(session_id)
        return templates.TemplateResponse(
            "tools.html",
            {
                "request": request,
                "invocations": invocations,
                "summary": summary,
                "session_id": session_id,
                "tool_name": tool_name,
            },
        )

    @app.get("/search", response_class=HTMLResponse)
    def search_page(request: Request, q: str = "", session_id: str | None = None):
        results = usage_service.search_conversations(q, session_id) if q else []
        return templates.TemplateResponse(
            "search.html",
            {"request": request, "query": q, "results": results, "session_id": session_id},
        )

    return app
