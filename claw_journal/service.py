from __future__ import annotations

import getpass
import json
import os
import socket
import subprocess
from collections import deque
from datetime import datetime, timedelta, timezone
from glob import glob
from pathlib import Path

from .config import Settings
from .pricing import PricingEngine
from .redaction import redact_raw_json_line
from .session_sync import SESSION_SYNC_LAST_SUCCESS_KEY
from .storage import UsageRepository


REMOTE_WORKSPACE_DIR = "~/.openclaw/workspace"
REMOTE_MEMORY_DIR = "~/.openclaw/workspace/memory"
MAX_MEMORY_FILE_READ_BYTES = 1_000_000


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

    def usage_forecast(self, lookback_days: int = 7) -> dict:
        """Project monthly spend based on average daily cost over recent days."""
        rows = self._repository.get_daily_usage(days=lookback_days)
        now = datetime.now(timezone.utc)
        days_in_month = (
            (now.replace(month=now.month % 12 + 1, day=1) - timedelta(days=1)).day
            if now.month < 12
            else 31
        )
        day_of_month = now.day

        daily_costs = [row.cost_usd for row in rows if row.cost_usd > 0]
        if not daily_costs:
            return {
                "avg_daily_cost_usd": 0.0,
                "days_with_data": 0,
                "lookback_days": lookback_days,
                "day_of_month": day_of_month,
                "days_in_month": days_in_month,
                "month_to_date_usd": 0.0,
                "projected_monthly_usd": 0.0,
            }

        month_rows = self._repository.get_daily_usage(days=day_of_month)
        month_to_date = sum(row.cost_usd for row in month_rows)

        avg_daily = sum(daily_costs) / len(daily_costs)
        remaining_days = days_in_month - day_of_month
        projected = month_to_date + (avg_daily * remaining_days)

        return {
            "avg_daily_cost_usd": round(avg_daily, 6),
            "days_with_data": len(daily_costs),
            "lookback_days": lookback_days,
            "day_of_month": day_of_month,
            "days_in_month": days_in_month,
            "month_to_date_usd": round(month_to_date, 6),
            "projected_monthly_usd": round(projected, 6),
        }

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

    def memory_files(self) -> dict:
        payload = self._list_memory_files()
        return {
            "rows": payload,
            "remote_enabled": self._settings.remote_enabled,
            "remote_ssh_host": self._settings.remote_ssh_host,
            "workspace_dir": REMOTE_WORKSPACE_DIR,
            "memory_dir": REMOTE_MEMORY_DIR,
        }

    def memory_file(self, path: str) -> dict:
        safe_path = str(path or "").strip()
        if not safe_path:
            return {"path": safe_path, "content": "", "exists": False}

        if not self._is_allowed_memory_path(safe_path):
            return {
                "path": safe_path,
                "content": "",
                "exists": False,
                "error": "Path is not in allowed memory explorer scope.",
            }

        content = self._read_remote_or_local_file(path=safe_path)
        if content is None:
            return {"path": safe_path, "content": "", "exists": False}
        return {"path": safe_path, "content": content, "exists": True}

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

    # ── Conversation logs (from reasoning) ─────────────────────────────

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

    def tootoo_reviews(self, limit: int = 1000) -> list[dict]:
        return self._repository.get_tootoo_reviews(limit)

    # ── Thinking blocks (from reasoning) ───────────────────────────────

    def thinking_blocks(self, session_id: str | None = None, limit: int = 100) -> list[dict]:
        return self._repository.get_thinking_blocks(session_id, limit)

    def session_thinking(self, session_id: str, limit: int = 100) -> list[dict]:
        return self._repository.get_session_thinking(session_id, limit)

    def annotated_thinking(self, session_id: str | None = None, limit: int = 100) -> list[dict]:
        return self._repository.get_annotated_thinking(session_id, limit)

    # ── Tool invocations (from reasoning) ──────────────────────────────

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

    # ── Model changes (from reasoning) ─────────────────────────────────

    def model_changes(self, session_id: str | None = None, limit: int = 100) -> list[dict]:
        return self._repository.get_model_changes(session_id, limit)

    def session_model_timeline(self, session_id: str) -> list[dict]:
        return self._repository.get_session_model_timeline(session_id)

    # ── Private helpers ────────────────────────────────────────────────

    def _list_memory_files(self) -> list[dict[str, str]]:
        workspace_dir = REMOTE_WORKSPACE_DIR
        memory_dir = REMOTE_MEMORY_DIR
        if self._settings.remote_enabled and self._settings.remote_ssh_host:
            return self._remote_list_memory_files(workspace_dir=workspace_dir, memory_dir=memory_dir)
        return self._local_list_memory_files(workspace_dir=workspace_dir, memory_dir=memory_dir)

    def _local_list_memory_files(self, workspace_dir: str, memory_dir: str) -> list[dict[str, str]]:
        workspace_root = Path(workspace_dir).expanduser()
        memory_root = Path(memory_dir).expanduser()
        rows: list[dict[str, str]] = []

        if workspace_root.exists() and workspace_root.is_dir():
            for file_path in sorted(workspace_root.rglob("*")):
                if not file_path.is_file():
                    continue

                try:
                    relative_name = str(file_path.relative_to(workspace_root))
                except ValueError:
                    relative_name = file_path.name

                group = "memory" if _is_path_within(file_path, memory_root) else "workspace"
                rows.append(
                    {
                        "path": str(file_path),
                        "name": relative_name,
                        "group": group,
                    }
                )

        rows.sort(key=lambda row: (0 if row.get("group") == "memory" else 1, str(row.get("name") or "").lower()))

        return rows

    def _remote_list_memory_files(self, workspace_dir: str, memory_dir: str) -> list[dict[str, str]]:
        script = """
import json
import os

rows = []
workspace_dir = os.path.expanduser(__WORKSPACE_DIR__)
memory_dir = os.path.expanduser(__MEMORY_DIR__)
if os.path.isdir(workspace_dir):
    for root, _, files in os.walk(workspace_dir, followlinks=False):
        for name in files:
            path = os.path.join(root, name)
            rel = os.path.relpath(path, workspace_dir)
            normalized_path = os.path.realpath(path)
            group = "memory" if os.path.commonpath([normalized_path, os.path.realpath(memory_dir)]) == os.path.realpath(memory_dir) else "workspace"
            rows.append({"path": path, "name": rel, "group": group})

rows.sort(key=lambda row: (0 if row.get("group") == "memory" else 1, str(row.get("name") or "").lower()))

print(json.dumps(rows))
""".replace("__WORKSPACE_DIR__", json.dumps(workspace_dir)).replace("__MEMORY_DIR__", json.dumps(memory_dir))

        output = self._run_remote_python(script)
        if not output:
            return []
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []

        rows: list[dict[str, str]] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            path = str(row.get("path") or "").strip()
            name = str(row.get("name") or "").strip()
            group = str(row.get("group") or "memory").strip() or "memory"
            if not path or not name:
                continue
            rows.append({"path": path, "name": name, "group": group})
        return rows

    def _is_allowed_memory_path(self, path: str) -> bool:
        workspace_dir = REMOTE_WORKSPACE_DIR

        if self._settings.remote_enabled and self._settings.remote_ssh_host:
            script = """
import json
import os

path = os.path.expanduser(__PATH__)
workspace = os.path.realpath(os.path.expanduser(__WORKSPACE_DIR__))

if not os.path.isfile(path):
    print(json.dumps({"allowed": False}))
elif os.path.commonpath([os.path.realpath(path), workspace]) != workspace:
    print(json.dumps({"allowed": False}))
else:
    print(json.dumps({"allowed": True}))
""".replace("__PATH__", json.dumps(path)).replace("__WORKSPACE_DIR__", json.dumps(workspace_dir))
            output = self._run_remote_python(script)
            if not output:
                return False
            try:
                payload = json.loads(output)
            except json.JSONDecodeError:
                return False
            return bool(payload.get("allowed"))

        local_path = Path(path).expanduser()
        workspace_root = Path(workspace_dir).expanduser()
        return local_path.exists() and local_path.is_file() and _is_path_within(local_path, workspace_root)

    def _read_remote_or_local_file(self, path: str) -> str | None:
        if self._settings.remote_enabled and self._settings.remote_ssh_host:
            script = """
import os
import sys

path = os.path.expanduser(__PATH__)
if not os.path.isfile(path):
    sys.exit(0)

with open(path, 'r', encoding='utf-8', errors='replace') as handle:
    payload = handle.read(__MAX_BYTES__ + 1)

if len(payload) > __MAX_BYTES__:
    payload = payload[:__MAX_BYTES__] + "\n\n[Truncated to __MAX_BYTES__ bytes for Memory Explorer.]"

sys.stdout.write(payload)
""".replace("__PATH__", json.dumps(path)).replace("__MAX_BYTES__", str(MAX_MEMORY_FILE_READ_BYTES))
            return self._run_remote_python(script)

        local_path = Path(path).expanduser()
        if not local_path.exists() or not local_path.is_file():
            return None
        content = local_path.read_text(encoding="utf-8", errors="replace")
        if len(content.encode("utf-8")) <= MAX_MEMORY_FILE_READ_BYTES:
            return content
        trimmed = content.encode("utf-8")[:MAX_MEMORY_FILE_READ_BYTES].decode("utf-8", errors="replace")
        return trimmed + f"\n\n[Truncated to {MAX_MEMORY_FILE_READ_BYTES} bytes for Memory Explorer.]"

    def _run_remote_python(self, script: str) -> str | None:
        if not self._settings.remote_ssh_host:
            return None

        command = [
            "ssh",
            "-o",
            "BatchMode=yes",
            self._settings.remote_ssh_host,
            "python3 -",
        ]

        result = subprocess.run(
            command,
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout

    def connection_info(self) -> dict:
        remote_host_raw = (self._settings.remote_ssh_host or "").strip()
        remote_user = None
        remote_host = remote_host_raw
        if "@" in remote_host_raw:
            remote_user, remote_host = remote_host_raw.split("@", 1)

        local_hostname = socket.gethostname()
        session_sync_last_success_ms = self._repository.get_checkpoint(SESSION_SYNC_LAST_SUCCESS_KEY)
        sync_log_path = Path.home() / "claw-journal-sync.log"
        sync_last_run_at, sync_last_run_message = _read_last_sync_log_entry(sync_log_path)
        sync_lock_age_seconds = _lock_age_seconds(Path("/tmp/claw-journal-sync.lock"))

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
                "session_sync_last_success_ms": session_sync_last_success_ms or 0,
                "session_sync_last_success_iso": _epoch_ms_to_iso(session_sync_last_success_ms),
                "sync_log_path": str(sync_log_path),
                "sync_last_run_at": sync_last_run_at,
                "sync_last_run_message": sync_last_run_message,
                "sync_lock_active": sync_lock_age_seconds is not None,
                "sync_lock_age_seconds": sync_lock_age_seconds,
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


def _epoch_ms_to_iso(value: int | None) -> str | None:
    if not value:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return datetime.fromtimestamp(number / 1000, tz=timezone.utc).isoformat()


def _read_last_sync_log_entry(path: Path) -> tuple[str | None, str | None]:
    if not path.exists() or not path.is_file():
        return None, None

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None, None

    for line in reversed(lines):
        text = line.strip()
        if not text:
            continue

        if len(text) >= 20 and text[4] == "-" and text[7] == "-" and text[10] == " ":
            stamp = text[:19]
            message = text[20:].strip() if len(text) > 20 else ""
            try:
                parsed = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
                iso = parsed.replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                iso = None
            return iso, message or text

        return None, text

    return None, None


def _lock_age_seconds(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        mtime = float(path.stat().st_mtime)
    except OSError:
        return None
    now = datetime.now(tz=timezone.utc).timestamp()
    age = int(now - mtime)
    return max(age, 0)


def _is_path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


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
