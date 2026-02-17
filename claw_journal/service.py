from __future__ import annotations

import getpass
import json
import socket
from collections import deque
from datetime import datetime, timedelta, timezone
from glob import glob
from pathlib import Path

from .config import Settings
from .pricing import PricingEngine
from .redaction import redact_raw_json_line
from .storage import UsageRepository


class UsageService:
    def __init__(
        self,
        repository: UsageRepository,
        settings: Settings,
        pricing_engine: PricingEngine,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._pricing_engine = pricing_engine

    def daily_usage(self, days: int = 30) -> list[dict]:
        return [row.__dict__ for row in self._repository.get_daily_usage(days=days)]

    def session_usage(self, limit: int = 100) -> list[dict]:
        return [row.__dict__ for row in self._repository.get_session_usage(limit=limit)]

    def reasoning_events(self, limit: int = 100) -> list[dict]:
        return self._repository.get_reasoning_events(limit=limit)

    def reconciled_session_usage(self, limit: int = 100) -> list[dict]:
        return self._repository.get_reconciled_session_usage(limit=limit)

    def get_dashboard_data(self) -> dict:
        user_prompts = self._repository.get_user_prompts_by_day(days=7)
        return {
            "summary": self._repository.get_dashboard_summary(),
            "costTrend": self._repository.get_cost_trend(days=7),
            "costByAgent": self._repository.get_cost_by_agent(limit=5),
            "topTools": self._repository.get_top_tools(limit=5),
            "userPromptsByDay": _fill_recent_days(rows=user_prompts, days=7),
            "recentSessions": self._repository.get_recent_sessions(limit=10),
        }

    def cost_source_summary(self) -> dict:
        return self._repository.get_cost_source_summary()

    def system_profile(self) -> dict:
        costs = self._repository.get_cost_source_summary()
        data_status = self._repository.get_data_status()

        if self._settings.auth_mode == "auto":
            inferred_auth_mode = "api_key" if costs.get("observed", 0) > 0 else "oauth"
        else:
            inferred_auth_mode = self._settings.auth_mode

        notes: list[str] = []
        if not data_status["log_usage_available"] and data_status["reconciled_available"]:
            notes.append("Session totals are available from gateway reconciliation, but log-derived usage events are absent.")
        if inferred_auth_mode == "oauth" and self._settings.billing_mode == "token":
            notes.append("OAuth mode typically hides direct per-response costs; token-mode costs may require local estimation.")
        if self._settings.billing_mode == "claude_max":
            notes.append("Claude Max billing mode is active; token costs are shown as included in subscription.")

        return {
            "auth_mode": inferred_auth_mode,
            "auth_mode_config": self._settings.auth_mode,
            "billing_mode": self._settings.billing_mode,
            "claude_max_monthly_usd": self._settings.claude_max_monthly_usd,
            "plan_cost": self.plan_cost_summary(),
            "cost_sources": costs,
            "data_status": data_status,
            "notes": notes,
        }

    def plan_cost_summary(self) -> dict:
        if self._settings.billing_mode != "claude_max":
            return {
                "enabled": False,
                "monthly_usd": 0.0,
                "daily_usd": 0.0,
            }

        daily = round(self._settings.claude_max_monthly_usd / 30.4375, 4)
        return {
            "enabled": True,
            "monthly_usd": float(self._settings.claude_max_monthly_usd),
            "daily_usd": daily,
        }

    def pricing_table(self) -> dict:
        return {
            "rows": self._pricing_engine.table,
            "available_models": self._pricing_engine.available_models,
        }

    def models_used(self, limit: int = 200) -> list[dict]:
        return self._repository.get_models_used(limit=limit)

    def model_catalog(self) -> dict:
        used = self._repository.get_models_used(limit=500)
        used_keys = {
            f"{(row.get('provider') or '').strip().lower()}/{(row.get('model') or '').strip().lower()}"
            for row in used
        }

        catalog_rows = []
        for row in self._pricing_engine.available_models:
            provider = str(row.get("provider") or "").strip().lower()
            model = str(row.get("model") or "").strip().lower()
            used_key = f"{provider}/{model}" if provider and model else ""
            catalog_rows.append(
                {
                    **row,
                    "used_by_openclaw": used_key in used_keys,
                }
            )
        return {"available_models": catalog_rows, "used_models": used}

    def token_accuracy(self, limit: int = 200) -> dict:
        rows = self._repository.get_token_accuracy(limit=limit)
        total = len(rows)
        matched = sum(1 for row in rows if row.get("snapshot_match"))
        return {
            "rows": rows,
            "summary": {
                "sessions_checked": total,
                "snapshot_matches": matched,
                "snapshot_mismatches": max(total - matched, 0),
            },
        }

    def session_detail(self, session_id: str, limit: int = 300) -> dict:
        events = self._repository.get_session_events(session_id=session_id, limit=limit)
        detail_rows = []
        for event in events:
            detail_rows.append(
                {
                    **event,
                    "human_text": _extract_human_text(event.get("raw_json"), event.get("reasoning_text")),
                }
            )
        return {"session_id": session_id, "rows": detail_rows}

    def session_snapshots(self, limit: int = 200) -> dict:
        rows = self._repository.get_session_snapshots(limit=limit)
        return {"limit": limit, "rows": rows}

    def chat_sessions(self, limit: int = 100, offset: int = 0) -> dict:
        rows = self._repository.get_chat_sessions(limit=limit, offset=offset)
        return {
            "limit": limit,
            "offset": offset,
            "rows": rows,
        }

    def chat_session_messages(self, session_id: str, limit: int = 300, before_id: int | None = None) -> dict:
        return self._repository.get_chat_session_messages(
            session_id=session_id,
            limit=limit,
            before_id=before_id,
        )

    def chat_search(self, query: str, limit: int = 200) -> dict:
        return self._repository.search_chat_messages(query=query, limit=limit)

    def logs_explorer(self, file_limit: int = 12, tail_lines: int = 80) -> dict:
        safe_file_limit = max(1, min(file_limit, 30))
        safe_tail_lines = max(1, min(tail_lines, 300))

        all_files = sorted(glob(self._settings.openclaw_log_glob))
        selected_files = all_files[-safe_file_limit:]
        checkpoints = self._repository.get_checkpoints(limit=1000)
        checkpoint_map = {
            str(row.get("source_key") or ""): row
            for row in checkpoints
        }

        file_rows: list[dict] = []
        for file_name in selected_files:
            path = Path(file_name)
            source_key = f"log:{path.resolve()}"
            checkpoint = checkpoint_map.get(source_key)
            tail = _read_tail_lines(path=path, line_limit=safe_tail_lines)
            stat = path.stat()

            file_rows.append(
                {
                    "path": str(path),
                    "source_key": source_key,
                    "size_bytes": int(stat.st_size),
                    "modified_at": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat(),
                    "checkpoint": checkpoint,
                    "tail_lines": tail,
                }
            )

        data_status = self._repository.get_data_status()
        return {
            "log_glob": self._settings.openclaw_log_glob,
            "matched_files": len(all_files),
            "returned_files": len(file_rows),
            "tail_lines": safe_tail_lines,
            "data_status": data_status,
            "files": file_rows,
        }

    def connection_info(self) -> dict:
        remote_host_raw = (self._settings.remote_ssh_host or "").strip()
        remote_user = None
        remote_host = remote_host_raw
        if "@" in remote_host_raw:
            remote_user, remote_host = remote_host_raw.split("@", 1)

        local_hostname = socket.gethostname()

        return {
            "local": {
                "user": getpass.getuser(),
                "hostname": local_hostname,
                "fqdn": socket.getfqdn(),
                "ip": _resolve_host_ip(local_hostname),
            },
            "remote": {
                "enabled": self._settings.remote_enabled,
                "ingest_mode": self._settings.remote_ingest_mode,
                "ssh_host_raw": remote_host_raw or None,
                "ssh_user": remote_user,
                "ssh_host": remote_host or None,
                "ssh_host_ip": _resolve_host_ip(remote_host) if remote_host else None,
                "session_sync_enabled": self._settings.session_sync_enabled,
            },
            "runtime": {
                "api_host": self._settings.host,
                "api_port": self._settings.port,
                "log_glob": self._settings.openclaw_log_glob,
            },
        }

    def upsert_model_pricing(
        self,
        provider: str,
        model: str,
        input_per_million: float,
        output_per_million: float,
    ) -> dict:
        self._pricing_engine.upsert_model_price(
            provider=provider,
            model=model,
            input_per_million=input_per_million,
            output_per_million=output_per_million,
        )
        if self._settings.pricing_file:
            self._pricing_engine.save_to_file(self._settings.pricing_file)
        return {
            "provider": provider,
            "model": model,
            "input_per_million": input_per_million,
            "output_per_million": output_per_million,
        }


def _extract_human_text(raw_json: object, reasoning_text: object) -> str | None:
    if isinstance(reasoning_text, str) and reasoning_text.strip():
        return reasoning_text.strip()

    if not isinstance(raw_json, str) or not raw_json.strip():
        return None

    payload = None
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        try:
            payload = json.loads(raw_json.replace("'", '"'))
        except Exception:
            payload = None

    if payload is None:
        return None

    found = _find_message_text(payload)
    if isinstance(found, str) and found.strip():
        return found.strip()
    return None


def _read_tail_lines(path: Path, line_limit: int) -> list[str]:
    lines: deque[str] = deque(maxlen=line_limit)
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            cleaned = line.rstrip("\n")
            if cleaned:
                lines.append(redact_raw_json_line(cleaned))
    return list(lines)


def _resolve_host_ip(host: str) -> str | None:
    if not host:
        return None
    try:
        return socket.gethostbyname(host)
    except OSError:
        return None


def _fill_recent_days(rows: list[dict], days: int) -> list[dict[str, int | str]]:
    count_by_day = {
        str(row.get("date") or ""): int(row.get("count") or 0)
        for row in rows
        if row.get("date")
    }

    today = datetime.now(timezone.utc).date()
    result: list[dict[str, int | str]] = []
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        result.append(
            {
                "date": day,
                "count": count_by_day.get(day, 0),
            }
        )
    return result


def _find_message_text(value: object) -> str | None:
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        if trimmed.startswith("{") or trimmed.startswith("["):
            try:
                nested = json.loads(trimmed)
                return _find_message_text(nested)
            except json.JSONDecodeError:
                pass
        return trimmed if len(trimmed.split()) >= 3 else None

    if isinstance(value, dict):
        preferred_keys = [
            "message",
            "content",
            "text",
            "prompt",
            "input",
            "output",
            "assistant",
            "user",
            "reasoning",
            "thinking",
        ]
        for key in preferred_keys:
            if key in value:
                found = _find_message_text(value.get(key))
                if found:
                    return found
        for nested_value in value.values():
            found = _find_message_text(nested_value)
            if found:
                return found
        return None

    if isinstance(value, list):
        for item in value:
            found = _find_message_text(item)
            if found:
                return found
        return None

    return None
