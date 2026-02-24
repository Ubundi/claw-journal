from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .service import UsageService

_PKG_DIR = Path(__file__).parent

# ── Jinja2 template helpers ─────────────────────────────────────────────────


def _fmt_ts(value: str | None) -> str:
    """Format an ISO timestamp to a short human-readable form."""
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(str(value))
        now = datetime.now(dt.tzinfo)
        if dt.date() == now.date():
            return dt.strftime("Today %H:%M")
        elif (now.date() - dt.date()).days == 1:
            return dt.strftime("Yesterday %H:%M")
        elif (now.date() - dt.date()).days < 7:
            return dt.strftime("%a %H:%M")
        else:
            return dt.strftime("%b %d, %H:%M")
    except (ValueError, TypeError):
        return str(value)[:16]


def _short_id(value: str | None, length: int = 8) -> str:
    """Truncate a UUID/session ID to a short prefix."""
    if not value:
        return ""
    return str(value)[:length]


_BRACKET_PREFIX_RE = re.compile(r"^(\[[^\]]*\]\s*)+")
_SYSTEM_PREFIX_RE = re.compile(r"^System:\s*", re.IGNORECASE)
_HEARTBEAT_RE = re.compile(
    r"^Read HEARTBEAT\.md if it exists \(workspace context\)\.\s*"
    r"(Follow it strictly\.\s*Do not infer or repeat old tasks from prior chat\s*)?",
    re.IGNORECASE,
)


def _clean_title(value: str | None, max_len: int = 80) -> str:
    """Strip noisy prefixes and truncate to a clean session title."""
    if not value:
        return ""
    text = str(value).strip()
    text = re.sub(r"\s*\n\s*", " ", text)
    text = _SYSTEM_PREFIX_RE.sub("", text)
    text = _BRACKET_PREFIX_RE.sub("", text)
    text = _HEARTBEAT_RE.sub("", text)
    text = re.sub(r"\s*HEARTBEAT_OK\b", "", text)
    text = re.sub(r"^🦞\s*OpenClaw\s+[\d.]+\S*\s*\([\w]+\)\s*🕒.*$", "", text)
    text = text.strip()
    if not text:
        return ""
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "..."
    return text


_JSON_NAME_RE = re.compile(r'"name"\s*:\s*"([^"]*)"')
_JSON_DESC_RE = re.compile(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"?')


def _parse_trigger(value: str | None) -> dict:
    """Parse a preceding_user_text into structured trigger info."""
    if not value:
        return {"name": "", "description": "", "raw": ""}
    text = str(value).strip()
    if text.startswith("{"):
        name = ""
        desc = ""
        try:
            obj = json.loads(text)
            name = obj.get("name", "")
            desc = obj.get("description", "")
        except (json.JSONDecodeError, AttributeError):
            m = _JSON_NAME_RE.search(text)
            if m:
                name = m.group(1)
            m = _JSON_DESC_RE.search(text)
            if m:
                desc = m.group(1)
        if name:
            desc = desc.replace("\\n", "\n").replace('\\"', '"').strip()
            if len(desc) > 200:
                desc = desc[:200].rstrip() + "..."
            return {"name": name, "description": desc, "raw": ""}
    cleaned = _clean_title(text, max_len=150)
    return {"name": "", "description": "", "raw": cleaned}


_WHATSAPP_RE = re.compile(r"^\[WhatsApp\s+(\+?\d+)")
_SLACK_RE = re.compile(r"^\[?Slack\s+(?:DM\s+from\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)")
_SYSTEM_SENDER_RE = re.compile(r"^System:\s*", re.IGNORECASE)
_OPENCLAW_BANNER_RE = re.compile(r"^🦞\s*OpenClaw\s")
_HEARTBEAT_SENDER_RE = re.compile(r"^Read HEARTBEAT\.md", re.IGNORECASE)


def _parse_sender(msg: dict) -> dict:
    """Identify the sender from a conversation message."""
    role = msg.get("role", "")
    if role == "assistant":
        return {"label": "Rune", "channel": "", "color": "orange"}

    text = msg.get("text_content") or ""
    has_tool_result = msg.get("has_tool_result", 0)

    if has_tool_result and role == "user":
        if _OPENCLAW_BANNER_RE.match(text):
            return {"label": "System", "channel": "OpenClaw", "color": "gray"}
        return {"label": "Tool Result", "channel": "", "color": "emerald"}

    m = _WHATSAPP_RE.match(text)
    if m:
        return {"label": "Adii", "channel": "WhatsApp", "color": "green"}

    m = _SLACK_RE.search(text)
    if m:
        return {"label": m.group(1), "channel": "Slack", "color": "purple"}

    if _SYSTEM_SENDER_RE.match(text):
        return {"label": "System", "channel": "", "color": "gray"}

    if _HEARTBEAT_SENDER_RE.match(text):
        return {"label": "System", "channel": "Heartbeat", "color": "gray"}

    if _OPENCLAW_BANNER_RE.match(text):
        return {"label": "System", "channel": "OpenClaw", "color": "gray"}

    return {"label": "Adii", "channel": "", "color": "cyan"}


# ── App factory ──────────────────────────────────────────────────────────────


def create_app(usage_service: UsageService) -> FastAPI:
    app = FastAPI(title="Claw Journal", version="0.5.0")

    # CORS for React frontend dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Jinja2 templates for reasoning visualization views
    templates = Jinja2Templates(directory=str(_PKG_DIR / "templates"))
    templates.env.filters["fromjson"] = json.loads
    templates.env.filters["ts"] = _fmt_ts
    templates.env.filters["short_id"] = _short_id
    templates.env.filters["clean_title"] = _clean_title
    templates.env.filters["parse_trigger"] = _parse_trigger
    templates.env.filters["parse_sender"] = _parse_sender
    app.mount("/static", StaticFiles(directory=str(_PKG_DIR / "static")), name="static")

    # ── Health ─────────────────────────────────────────────────────────

    # ── SPA static file serving ───────────────────────────────────────
    _FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    _spa_enabled = _FRONTEND_DIST.is_dir() and (_FRONTEND_DIST / "index.html").exists()

    @app.get("/", response_model=None)
    def root():
        if _spa_enabled:
            return HTMLResponse((_FRONTEND_DIST / "index.html").read_text())
        return {
            "name": "Claw Journal API",
            "dashboard": "Run the React dashboard from frontend/ (npm run dev)",
            "views": "Server-rendered reasoning views available at /view/",
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # ── Dashboard + system API (from dev) ──────────────────────────────

    @app.get("/api/dashboard-data")
    def dashboard_data() -> dict[str, object]:
        return usage_service.get_dashboard_data()

    @app.get("/api/usage/daily")
    def daily_usage(days: int = Query(default=30, ge=1, le=365)) -> dict[str, object]:
        return {"days": days, "rows": usage_service.daily_usage(days=days)}

    @app.get("/api/usage/forecast")
    def usage_forecast(lookback_days: int = Query(default=7, ge=1, le=30)) -> dict[str, object]:
        return usage_service.usage_forecast(lookback_days=lookback_days)

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

    @app.get("/api/system/profile")
    def system_profile() -> dict[str, object]:
        return usage_service.system_profile()

    @app.get("/api/system/models")
    def system_models() -> dict[str, object]:
        return usage_service.model_catalog()

    @app.get("/api/system/connection")
    def system_connection() -> dict[str, object]:
        return usage_service.connection_info()

    @app.get("/api/system/token-accuracy")
    def token_accuracy(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        return usage_service.token_accuracy(limit=limit)

    @app.get("/api/system/session-snapshots")
    def session_snapshots(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        return usage_service.session_snapshots(limit=limit)

    @app.get("/api/system/logs-explorer")
    def logs_explorer(
        file_limit: int = Query(default=12, ge=1, le=30),
        tail_lines: int = Query(default=80, ge=1, le=300),
    ) -> dict[str, object]:
        return usage_service.logs_explorer(file_limit=file_limit, tail_lines=tail_lines)

    # ── Chat API (from dev) ────────────────────────────────────────────

    @app.get("/api/chat/sessions")
    def chat_sessions(
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, object]:
        return usage_service.chat_sessions(limit=limit, offset=offset)

    @app.get("/api/chat/session/{session_id}")
    def chat_session_messages(
        session_id: str,
        limit: int = Query(default=300, ge=1, le=2000),
        before_id: int | None = Query(default=None, ge=1),
    ) -> dict[str, object]:
        return usage_service.chat_session_messages(
            session_id=session_id,
            limit=limit,
            before_id=before_id,
        )

    @app.get("/api/chat/search")
    def chat_search(
        query: str = Query(..., min_length=2),
        limit: int = Query(default=200, ge=1, le=2000),
    ) -> dict[str, object]:
        return usage_service.chat_search(query=query, limit=limit)

    # ── Memory API (from dev) ──────────────────────────────────────────

    @app.get("/api/memory/files")
    def memory_files() -> dict[str, object]:
        return usage_service.memory_files()

    @app.get("/api/memory/file")
    def memory_file(path: str = Query(..., min_length=1)) -> dict[str, object]:
        return usage_service.memory_file(path=path)

    # ── Session detail + pricing (from dev) ────────────────────────────

    @app.get("/api/usage/session/{session_id}")
    def session_detail(session_id: str, limit: int = Query(default=300, ge=1, le=2000)) -> dict[str, object]:
        return usage_service.session_detail(session_id=session_id, limit=limit)

    @app.get("/api/pricing")
    def pricing_table() -> dict[str, object]:
        return usage_service.pricing_table()

    @app.get("/api/usage/plan-cost")
    def plan_cost() -> dict[str, object]:
        return usage_service.plan_cost_summary()

    @app.post("/api/pricing/upsert")
    def pricing_upsert(payload: dict = Body(...)) -> dict[str, object]:
        provider = str(payload.get("provider") or "").strip()
        model = str(payload.get("model") or "").strip()
        if not provider or not model:
            raise HTTPException(status_code=400, detail="provider and model are required")

        input_per_million = float(payload.get("input_per_million") or 0.0)
        output_per_million = float(payload.get("output_per_million") or 0.0)
        if input_per_million < 0 or output_per_million < 0:
            raise HTTPException(
                status_code=400,
                detail="input_per_million and output_per_million must be >= 0",
            )

        return usage_service.upsert_model_pricing(
            provider=provider,
            model=model,
            input_per_million=input_per_million,
            output_per_million=output_per_million,
        )

    # ── Conversation API (from reasoning) ──────────────────────────────

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

    # ── TooToo API ─────────────────────────────────────────────────────

    @app.get("/api/tootoo/reviews")
    def tootoo_reviews(
        limit: int = Query(default=1000, ge=1, le=5000),
    ) -> dict[str, object]:
        return {"rows": usage_service.tootoo_reviews(limit)}

    # ── Thinking API (from reasoning) ──────────────────────────────────

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

    # ── Tools API (from reasoning) ────────────────────────────────────

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

    @app.get("/api/tools/detail/{tool_name}")
    def tool_detail_api(
        tool_name: str,
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> dict[str, object]:
        invocations = usage_service.tool_detail(tool_name, limit=limit)
        summary_row = None
        for s in usage_service.tool_usage_summary():
            if s["tool_name"] == tool_name:
                summary_row = s
                break
        return {
            "tool_name": tool_name,
            "summary": summary_row,
            "rows": invocations,
        }

    @app.get("/api/tools/names")
    def tool_names() -> dict[str, object]:
        return {"rows": usage_service.distinct_tool_names()}

    # ── Model changes API (from reasoning) ─────────────────────────────

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

    # ── Web UI views (from reasoning, mounted at /view/) ───────────────

    @app.get("/view/", response_class=HTMLResponse)
    def view_dashboard(request: Request, tool: str | None = None, date: str | None = None):
        if tool:
            sessions = usage_service.sessions_filtered_by_tool(tool, limit=50, date=date)
        else:
            sessions = usage_service.sessions_with_transcripts(limit=50, date=date)
        daily = usage_service.daily_usage(days=14)
        tool_names = usage_service.distinct_tool_names()
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "sessions": sessions,
                "daily": daily,
                "tool_names": tool_names,
                "active_tool": tool,
                "active_date": date,
            },
        )

    @app.get("/view/conversation/{session_id}", response_class=HTMLResponse)
    def view_conversation(request: Request, session_id: str):
        messages = usage_service.session_conversation(session_id, limit=500)
        model_timeline = usage_service.session_model_timeline(session_id)
        return templates.TemplateResponse(
            "conversation.html",
            {
                "request": request,
                "session_id": session_id,
                "messages": messages,
                "model_timeline": model_timeline,
            },
        )

    @app.get("/view/thinking", response_class=HTMLResponse)
    def view_thinking(request: Request, session_id: str | None = None):
        blocks = usage_service.annotated_thinking(session_id, limit=200)
        return templates.TemplateResponse(
            "thinking.html",
            {"request": request, "blocks": blocks, "session_id": session_id},
        )

    @app.get("/view/tools", response_class=HTMLResponse)
    def view_tools(
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

    @app.get("/view/tools/detail/{tool_name}", response_class=HTMLResponse)
    def view_tool_detail(request: Request, tool_name: str):
        invocations = usage_service.tool_detail(tool_name, limit=200)
        summary_row = None
        for s in usage_service.tool_usage_summary():
            if s["tool_name"] == tool_name:
                summary_row = s
                break
        return templates.TemplateResponse(
            "tool_detail.html",
            {
                "request": request,
                "tool_name": tool_name,
                "invocations": invocations,
                "summary": summary_row,
            },
        )

    @app.get("/view/search", response_class=HTMLResponse)
    def view_search(request: Request, q: str = "", session_id: str | None = None):
        results = usage_service.search_conversations(q, session_id) if q else []
        return templates.TemplateResponse(
            "search.html",
            {"request": request, "query": q, "results": results, "session_id": session_id},
        )

    # ── Serve React SPA (production build) ─────────────────────────────
    if _spa_enabled:
        # Mount built assets (JS, CSS, images) under /assets/
        app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="frontend-assets")

        # SPA catch-all: serve real files from dist/ if they exist, otherwise index.html
        @app.get("/{path:path}")
        def spa_fallback(path: str):
            # Serve actual static files (clawjournalicon.png, tootoo-icon.png, etc.)
            candidate = _FRONTEND_DIST / path
            if candidate.is_file() and _FRONTEND_DIST in candidate.resolve().parents:
                return FileResponse(str(candidate))
            # Everything else gets the SPA shell
            return HTMLResponse((_FRONTEND_DIST / "index.html").read_text())

    return app
