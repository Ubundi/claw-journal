from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .service import UsageService

_PKG_DIR = Path(__file__).parent


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
    # Collapse newlines to spaces
    text = re.sub(r"\s*\n\s*", " ", text)
    # Strip "System: " prefix first (so bracket regex can catch what follows)
    text = _SYSTEM_PREFIX_RE.sub("", text)
    # Strip leading bracket prefixes like [WhatsApp...], [cron:...], [Slack...], [timestamp]
    text = _BRACKET_PREFIX_RE.sub("", text)
    # Strip HEARTBEAT boilerplate
    text = _HEARTBEAT_RE.sub("", text)
    # Strip "HEARTBEAT_OK" anywhere
    text = re.sub(r"\s*HEARTBEAT_OK\b", "", text)
    # Strip OpenClaw system banner (lobster emoji + version info)
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
    """Parse a preceding_user_text into structured trigger info.

    Returns {"name": ..., "description": ..., "raw": ...}.
    """
    if not value:
        return {"name": "", "description": "", "raw": ""}
    text = str(value).strip()
    # Try parsing as JSON (OpenClaw job definitions) — may be truncated
    if text.startswith("{"):
        # Try full parse first
        name = ""
        desc = ""
        try:
            obj = json.loads(text)
            name = obj.get("name", "")
            desc = obj.get("description", "")
        except (json.JSONDecodeError, AttributeError):
            # Truncated JSON — extract fields with regex
            m = _JSON_NAME_RE.search(text)
            if m:
                name = m.group(1)
            m = _JSON_DESC_RE.search(text)
            if m:
                desc = m.group(1)
        if name:
            # Unescape JSON string escapes
            desc = desc.replace("\\n", "\n").replace('\\"', '"').strip()
            if len(desc) > 200:
                desc = desc[:200].rstrip() + "..."
            return {"name": name, "description": desc, "raw": ""}
    # Not JSON — return as cleaned raw text
    cleaned = _clean_title(text, max_len=150)
    return {"name": "", "description": "", "raw": cleaned}


_WHATSAPP_RE = re.compile(r"^\[WhatsApp\s+(\+?\d+)")
_SLACK_RE = re.compile(r"^\[?Slack\s+(?:DM\s+from\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)")
_SYSTEM_SENDER_RE = re.compile(r"^System:\s*", re.IGNORECASE)
_OPENCLAW_BANNER_RE = re.compile(r"^🦞\s*OpenClaw\s")
_HEARTBEAT_SENDER_RE = re.compile(r"^Read HEARTBEAT\.md", re.IGNORECASE)


def _parse_sender(msg: dict) -> dict:
    """Identify the sender from a conversation message.

    Returns {"label": ..., "channel": ..., "color": ...}.
    """
    role = msg.get("role", "")
    if role == "assistant":
        return {"label": "Rune", "channel": "", "color": "orange"}

    text = msg.get("text_content") or ""
    has_tool_result = msg.get("has_tool_result", 0)

    # Tool results
    if has_tool_result and role == "user":
        # Check if it's an OpenClaw system banner
        if _OPENCLAW_BANNER_RE.match(text):
            return {"label": "System", "channel": "OpenClaw", "color": "gray"}
        return {"label": "Tool Result", "channel": "", "color": "emerald"}

    # WhatsApp message
    m = _WHATSAPP_RE.match(text)
    if m:
        return {"label": "Adii", "channel": "WhatsApp", "color": "green"}

    # Slack message
    m = _SLACK_RE.search(text)
    if m:
        return {"label": m.group(1), "channel": "Slack", "color": "purple"}

    # System prefix
    if _SYSTEM_SENDER_RE.match(text):
        return {"label": "System", "channel": "", "color": "gray"}

    # Heartbeat
    if _HEARTBEAT_SENDER_RE.match(text):
        return {"label": "System", "channel": "Heartbeat", "color": "gray"}

    # OpenClaw banner without tool_result flag
    if _OPENCLAW_BANNER_RE.match(text):
        return {"label": "System", "channel": "OpenClaw", "color": "gray"}

    # Default user
    return {"label": "Adii", "channel": "", "color": "cyan"}


def create_app(usage_service: UsageService) -> FastAPI:
    app = FastAPI(title="Claw Journal", version="0.4.0")

    templates = Jinja2Templates(directory=str(_PKG_DIR / "templates"))
    templates.env.filters["fromjson"] = json.loads
    templates.env.filters["ts"] = _fmt_ts
    templates.env.filters["short_id"] = _short_id
    templates.env.filters["clean_title"] = _clean_title
    templates.env.filters["parse_trigger"] = _parse_trigger
    templates.env.filters["parse_sender"] = _parse_sender
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

    # ── Web UI routes ──────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, tool: str | None = None, date: str | None = None):
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

    @app.get("/conversation/{session_id}", response_class=HTMLResponse)
    def conversation_page(request: Request, session_id: str):
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

    @app.get("/thinking", response_class=HTMLResponse)
    def thinking_page(request: Request, session_id: str | None = None):
        blocks = usage_service.annotated_thinking(session_id, limit=200)
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

    @app.get("/tools/detail/{tool_name}", response_class=HTMLResponse)
    def tool_detail_page(request: Request, tool_name: str):
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

    @app.get("/search", response_class=HTMLResponse)
    def search_page(request: Request, q: str = "", session_id: str | None = None):
        results = usage_service.search_conversations(q, session_id) if q else []
        return templates.TemplateResponse(
            "search.html",
            {"request": request, "query": q, "results": results, "session_id": session_id},
        )

    return app
