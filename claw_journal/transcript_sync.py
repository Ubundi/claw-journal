from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import time
from datetime import datetime, timezone
from glob import glob
from pathlib import Path

from .storage import UsageRepository


logger = logging.getLogger(__name__)


class TranscriptSyncLoop:
    def __init__(
        self,
        repository: UsageRepository,
        interval_seconds: float,
        local_transcript_glob: str,
        remote_enabled: bool,
        remote_ssh_host: str | None,
        remote_transcript_glob: str,
    ) -> None:
        self._repository = repository
        self._interval_seconds = interval_seconds
        self._local_transcript_glob = local_transcript_glob
        self._remote_enabled = remote_enabled
        self._remote_ssh_host = remote_ssh_host
        self._remote_transcript_glob = remote_transcript_glob
        self._running = False

    def run_forever(self) -> None:
        self._running = True
        logger.info("Starting transcript sync loop")
        while self._running:
            try:
                inserted = self.poll_once()
                if inserted:
                    logger.info("Ingested %s transcript messages", inserted)
            except Exception as exc:
                logger.exception("Transcript sync cycle failed: %s", exc)
            time.sleep(self._interval_seconds)

    def stop(self) -> None:
        self._running = False

    def poll_once(self) -> int:
        if self._remote_enabled and self._remote_ssh_host:
            return self._poll_remote()
        return self._poll_local()

    def _poll_local(self) -> int:
        inserted_total = 0
        file_paths = sorted(glob(self._local_transcript_glob))

        for file_name in file_paths:
            path = Path(file_name)
            source_key = f"transcript:{path.resolve()}"
            offset = self._repository.get_checkpoint(source_key)
            if not path.exists():
                continue

            file_size = path.stat().st_size
            if offset > file_size:
                offset = 0

            with path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(offset)
                lines = handle.readlines()
                new_offset = handle.tell()

            fallback_ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
            messages = _parse_lines(lines=lines, source_path=str(path), fallback_ts=fallback_ts)
            inserted_total += self._repository.insert_conversation_messages(messages)
            self._repository.upsert_checkpoint(source_key, new_offset)

        return inserted_total

    def _poll_remote(self) -> int:
        if not self._remote_ssh_host:
            return 0

        inserted_total = 0
        listed = self._remote_list_files()

        for row in listed:
            source_path = str(row.get("path") or "")
            file_size = int(row.get("size") or 0)
            modified_at = str(row.get("modified_at") or "")
            if not source_path:
                continue

            source_key = f"transcript:{self._remote_ssh_host}:{source_path}"
            offset = self._repository.get_checkpoint(source_key)
            if offset > file_size:
                offset = 0
            if file_size <= offset:
                continue

            content = self._remote_read_from_offset(path=source_path, offset=offset)
            if content is None:
                continue

            lines = content.splitlines()
            fallback_ts = modified_at or datetime.now(timezone.utc).isoformat()
            messages = _parse_lines(lines=lines, source_path=source_path, fallback_ts=fallback_ts)
            inserted_total += self._repository.insert_conversation_messages(messages)
            self._repository.upsert_checkpoint(source_key, file_size)

        return inserted_total

    def _remote_list_files(self) -> list[dict]:
        script = """
import glob
import json
import os

pattern = os.path.expanduser(__PATTERN__)
rows = []
for path in sorted(glob.glob(pattern)):
    try:
        stat = os.stat(path)
    except OSError:
        continue
    rows.append({"path": path, "size": int(stat.st_size), "modified_at": int(stat.st_mtime)})
print(json.dumps(rows))
""".replace("__PATTERN__", json.dumps(self._remote_transcript_glob))

        output = self._run_remote_python(script)
        if not output:
            return []

        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            logger.warning("Failed to parse remote transcript listing output")
            return []

        if not isinstance(payload, list):
            return []

        rows: list[dict] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            modified_raw = row.get("modified_at")
            modified_ts = None
            if isinstance(modified_raw, (int, float)):
                modified_ts = datetime.fromtimestamp(float(modified_raw), tz=timezone.utc).isoformat()
            rows.append(
                {
                    "path": row.get("path"),
                    "size": int(row.get("size") or 0),
                    "modified_at": modified_ts,
                }
            )
        return rows

    def _remote_read_from_offset(self, path: str, offset: int) -> str | None:
        script = """
import os
import sys

path = __PATH__
offset = __OFFSET__
if not os.path.exists(path):
    sys.exit(0)

with open(path, "rb") as handle:
    handle.seek(offset)
    data = handle.read()

sys.stdout.write(data.decode("utf-8", errors="replace"))
""".replace("__PATH__", json.dumps(path)).replace("__OFFSET__", str(int(offset)))

        return self._run_remote_python(script)

    def _run_remote_python(self, script: str) -> str | None:
        if not self._remote_ssh_host:
            return None

        command = [
            "ssh",
            "-o",
            "BatchMode=yes",
            self._remote_ssh_host,
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
            stderr = (result.stderr or "").strip()
            if stderr:
                logger.warning("Remote transcript sync command failed: %s", stderr)
            return None
        return result.stdout


def _parse_lines(lines: list[str], source_path: str, fallback_ts: str) -> list[dict]:
    messages: list[dict] = []
    session_id_from_path = _extract_session_id_from_path(source_path)

    for index, line in enumerate(lines, start=1):
        raw_line = line.strip()
        if not raw_line:
            continue

        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        if not isinstance(payload, dict):
            continue

        role = _extract_role(payload)
        text_value = _extract_text(payload)
        event_ts = _extract_timestamp(payload, fallback_ts=fallback_ts)
        session_id = session_id_from_path or _extract_session_id(payload)
        message_type = _extract_message_type(payload)
        provider, model = _extract_provider_model(payload)

        if not session_id:
            session_id = "unknown"

        fingerprint_src = f"{session_id}|{event_ts}|{role}|{raw_line}|{index}|{source_path}"
        fingerprint = hashlib.sha256(fingerprint_src.encode("utf-8")).hexdigest()

        messages.append(
            {
                "session_id": session_id,
                "event_ts": event_ts,
                "role": role,
                "content_text": text_value,
                "message_type": message_type,
                "provider": provider,
                "model": model,
                "source": "transcript",
                "source_path": source_path,
                "raw_json": raw_line,
                "message_fingerprint": fingerprint,
            }
        )

    return messages


def _extract_session_id(payload: dict) -> str | None:
    for key in ["sessionId", "session_id", "session"]:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    for key in ["sessionId", "session_id", "session"]:
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def _extract_provider_model(payload: dict) -> tuple[str | None, str | None]:
    provider = None
    model = None

    for key in ["provider", "modelProvider"]:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            provider = value.strip()
            break

    for key in ["model", "modelId"]:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            model = value.strip()
            break

    message = payload.get("message")
    if isinstance(message, dict):
        if not provider:
            value = message.get("provider")
            if isinstance(value, str) and value.strip():
                provider = value.strip()
        if not model:
            value = message.get("model") or message.get("modelId")
            if isinstance(value, str) and value.strip():
                model = value.strip()

    return provider, model


def _extract_timestamp(payload: dict, fallback_ts: str) -> str:
    candidates = [
        payload.get("event_ts"),
        payload.get("timestamp"),
        payload.get("time"),
        payload.get("createdAt"),
        payload.get("updatedAt"),
        payload.get("ts"),
    ]

    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    candidates.extend([meta.get("timestamp"), meta.get("time"), meta.get("createdAt")])

    for value in candidates:
        parsed = _to_iso_timestamp(value)
        if parsed:
            return parsed

    return fallback_ts


def _to_iso_timestamp(value: object) -> str | None:
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 1_000_000_000_000:
            number = number / 1000.0
        try:
            return datetime.fromtimestamp(number, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            return _to_iso_timestamp(int(raw))
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return None

    return None


def _extract_role(payload: dict) -> str:
    candidates = [
        payload.get("role"),
        payload.get("sender"),
        payload.get("author"),
        payload.get("actor"),
        payload.get("type"),
    ]

    message = payload.get("message")
    if isinstance(message, dict):
        candidates.extend([message.get("role"), message.get("sender")])

    for value in candidates:
        if not isinstance(value, str):
            continue
        normalized = value.strip().lower()
        if normalized in {"user", "assistant", "system", "tool"}:
            return normalized
        if normalized in {"human", "customer"}:
            return "user"
        if normalized in {"ai", "model", "bot"}:
            return "assistant"

    if payload.get("toolName") or payload.get("tool_name"):
        return "tool"

    return "unknown"


def _extract_text(payload: dict) -> str | None:
    direct_keys = ["content", "text", "message", "output", "input", "value"]
    for key in direct_keys:
        if key not in payload:
            continue
        value = payload.get(key)
        extracted = _flatten_text(value)
        if extracted:
            return extracted

    message = payload.get("message")
    if isinstance(message, dict):
        for key in ["content", "text", "output", "input", "reasoning"]:
            extracted = _flatten_text(message.get(key))
            if extracted:
                return extracted

    if payload.get("toolName") or payload.get("tool_name"):
        tool = payload.get("toolName") or payload.get("tool_name")
        args_text = _flatten_text(payload.get("toolArgs") or payload.get("tool_args"))
        if args_text:
            return f"{tool}: {args_text}"
        return str(tool)

    return None


def _flatten_text(value: object) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None

    if isinstance(value, (int, float, bool)):
        return str(value)

    if isinstance(value, list):
        parts = []
        for item in value:
            part = _flatten_text(item)
            if part:
                parts.append(part)
        if parts:
            return "\n".join(parts)
        return None

    if isinstance(value, dict):
        for key in ["text", "content", "value", "output", "input", "reasoning"]:
            if key in value:
                part = _flatten_text(value.get(key))
                if part:
                    return part
        return json.dumps(value, ensure_ascii=False)

    return None


def _extract_message_type(payload: dict) -> str | None:
    for key in ["type", "event", "kind", "messageType"]:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_session_id_from_path(source_path: str) -> str | None:
    if not source_path:
        return None

    path = Path(source_path)
    name = path.name
    if name.endswith(".jsonl"):
        return name[:-6]
    return None
