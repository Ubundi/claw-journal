from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


TRUE_VALUES = {"1", "true", "yes", "on"}
INGEST_MODES = {"rpc", "file", "hybrid"}


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    openclaw_log_glob: str
    poll_seconds: float
    remote_enabled: bool
    remote_gateway_url: str | None
    remote_gateway_token: str | None
    remote_gateway_agent_id: str | None
    remote_ingest_mode: str
    db_path: Path


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def load_settings() -> Settings:
    host = os.getenv("CJ_HOST", "127.0.0.1")
    port = int(os.getenv("CJ_PORT", "3000"))
    openclaw_log_glob = os.getenv("CJ_OPENCLAW_LOG_GLOB", "/tmp/openclaw/openclaw-*.log")
    poll_seconds = float(os.getenv("CJ_POLL_SECONDS", "1.0"))
    remote_enabled = _parse_bool(os.getenv("CJ_REMOTE_ENABLED"), True)
    remote_gateway_url = os.getenv("CJ_REMOTE_GATEWAY_URL") or None
    remote_gateway_token = os.getenv("CJ_REMOTE_GATEWAY_TOKEN") or None
    remote_gateway_agent_id = os.getenv("CJ_REMOTE_GATEWAY_AGENT_ID") or None
    remote_ingest_mode = os.getenv("CJ_REMOTE_INGEST_MODE", "hybrid").strip().lower()
    db_path = Path(os.getenv("CJ_DB_PATH", "./data/claw_journal.db")).expanduser()

    if remote_ingest_mode not in INGEST_MODES:
        raise ValueError(f"CJ_REMOTE_INGEST_MODE must be one of: {sorted(INGEST_MODES)}")

    if remote_enabled and remote_ingest_mode in {"rpc", "hybrid"}:
        missing = []
        if not remote_gateway_url:
            missing.append("CJ_REMOTE_GATEWAY_URL")
        if not remote_gateway_token:
            missing.append("CJ_REMOTE_GATEWAY_TOKEN")
        if not remote_gateway_agent_id:
            missing.append("CJ_REMOTE_GATEWAY_AGENT_ID")
        if missing:
            raise ValueError(
                "Remote ingest mode requires gateway config: " + ", ".join(missing)
            )

    if poll_seconds <= 0:
        raise ValueError("CJ_POLL_SECONDS must be > 0")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    return Settings(
        host=host,
        port=port,
        openclaw_log_glob=openclaw_log_glob,
        poll_seconds=poll_seconds,
        remote_enabled=remote_enabled,
        remote_gateway_url=remote_gateway_url,
        remote_gateway_token=remote_gateway_token,
        remote_gateway_agent_id=remote_gateway_agent_id,
        remote_ingest_mode=remote_ingest_mode,
        db_path=db_path,
    )
