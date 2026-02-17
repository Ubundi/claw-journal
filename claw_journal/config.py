from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


TRUE_VALUES = {"1", "true", "yes", "on"}
INGEST_MODES = {"rpc", "file", "hybrid"}
AUTH_MODES = {"auto", "oauth", "api_key"}
BILLING_MODES = {"token", "claude_max"}


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    auto_port: bool
    port_search_limit: int
    openclaw_log_glob: str
    poll_seconds: float
    remote_enabled: bool
    remote_gateway_url: str | None
    remote_gateway_token: str | None
    remote_gateway_agent_id: str | None
    remote_ingest_mode: str
    remote_ssh_host: str | None
    remote_openclaw_bin: str
    remote_path_prefix: str
    session_sync_enabled: bool
    session_sync_seconds: float
    transcript_sync_enabled: bool
    transcript_sync_seconds: float
    transcript_glob: str
    remote_transcript_glob: str
    snapshot_backfill_enabled: bool
    snapshot_backfill_seconds: float
    cost_estimation_enabled: bool
    pricing_file: Path | None
    openrouter_models_url: str
    openrouter_sync_enabled: bool
    openrouter_timeout_seconds: float
    redaction_enabled: bool
    auth_mode: str
    billing_mode: str
    claude_max_monthly_usd: float
    startup_healthcheck_enabled: bool
    startup_healthcheck_timeout_seconds: float
    db_path: Path


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def _load_dotenv_file(dotenv_path: str = ".env") -> None:
    path = Path(dotenv_path)
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_settings() -> Settings:
    _load_dotenv_file(".env")

    host = os.getenv("CJ_HOST", "127.0.0.1")
    port = int(os.getenv("CJ_PORT", "3000"))
    auto_port = _parse_bool(os.getenv("CJ_AUTO_PORT"), True)
    port_search_limit = int(os.getenv("CJ_PORT_SEARCH_LIMIT", "50"))
    openclaw_log_glob = os.getenv("CJ_OPENCLAW_LOG_GLOB", "/tmp/openclaw/openclaw-*.log")
    poll_seconds = float(os.getenv("CJ_POLL_SECONDS", "1.0"))
    remote_enabled = _parse_bool(os.getenv("CJ_REMOTE_ENABLED"), False)
    remote_gateway_url = os.getenv("CJ_REMOTE_GATEWAY_URL") or None
    remote_gateway_token = os.getenv("CJ_REMOTE_GATEWAY_TOKEN") or None
    remote_gateway_agent_id = os.getenv("CJ_REMOTE_GATEWAY_AGENT_ID") or None
    remote_ingest_mode = os.getenv("CJ_REMOTE_INGEST_MODE", "file").strip().lower()
    remote_ssh_host = os.getenv("CJ_REMOTE_SSH_HOST") or None
    remote_openclaw_bin = os.getenv("CJ_REMOTE_OPENCLAW_BIN", "/opt/homebrew/bin/openclaw")
    remote_path_prefix = os.getenv("CJ_REMOTE_PATH_PREFIX", "/opt/homebrew/bin")
    session_sync_enabled = _parse_bool(os.getenv("CJ_SESSION_SYNC_ENABLED"), True)
    session_sync_seconds = float(os.getenv("CJ_SESSION_SYNC_SECONDS", "30.0"))
    transcript_sync_enabled = _parse_bool(os.getenv("CJ_TRANSCRIPT_SYNC_ENABLED"), True)
    transcript_sync_seconds = float(os.getenv("CJ_TRANSCRIPT_SYNC_SECONDS", "45.0"))
    transcript_glob = os.getenv("CJ_TRANSCRIPT_GLOB", "~/.openclaw/agents/*/sessions/*.jsonl")
    remote_transcript_glob = os.getenv("CJ_REMOTE_TRANSCRIPT_GLOB", "~/.openclaw/agents/*/sessions/*.jsonl")
    snapshot_backfill_enabled = _parse_bool(os.getenv("CJ_SNAPSHOT_BACKFILL_ENABLED"), True)
    snapshot_backfill_seconds = float(os.getenv("CJ_SNAPSHOT_BACKFILL_SECONDS", "10.0"))
    cost_estimation_enabled = _parse_bool(os.getenv("CJ_COST_ESTIMATION_ENABLED"), True)
    pricing_file_raw = os.getenv("CJ_PRICING_FILE") or "./pricing.json"
    pricing_file = Path(pricing_file_raw).expanduser() if pricing_file_raw else None
    openrouter_models_url = os.getenv("CJ_OPENROUTER_MODELS_URL", "https://openrouter.ai/api/v1/models")
    openrouter_sync_enabled = _parse_bool(os.getenv("CJ_OPENROUTER_SYNC_ENABLED"), True)
    openrouter_timeout_seconds = float(os.getenv("CJ_OPENROUTER_TIMEOUT_SECONDS", "8.0"))
    redaction_enabled = _parse_bool(os.getenv("CJ_REDACTION_ENABLED"), True)
    auth_mode = os.getenv("CJ_AUTH_MODE", "auto").strip().lower()
    billing_mode = os.getenv("CJ_BILLING_MODE", "token").strip().lower()
    claude_max_monthly_usd = float(os.getenv("CJ_CLAUDE_MAX_MONTHLY_USD", "200.0"))
    startup_healthcheck_enabled = _parse_bool(os.getenv("CJ_STARTUP_HEALTHCHECK_ENABLED"), True)
    startup_healthcheck_timeout_seconds = float(os.getenv("CJ_STARTUP_HEALTHCHECK_TIMEOUT_SECONDS", "20.0"))
    db_path = Path(os.getenv("CJ_DB_PATH", "./data/claw_journal.db")).expanduser()

    if remote_ingest_mode not in INGEST_MODES:
        raise ValueError(f"CJ_REMOTE_INGEST_MODE must be one of: {sorted(INGEST_MODES)}")

    if auth_mode not in AUTH_MODES:
        raise ValueError(f"CJ_AUTH_MODE must be one of: {sorted(AUTH_MODES)}")

    if billing_mode not in BILLING_MODES:
        raise ValueError(f"CJ_BILLING_MODE must be one of: {sorted(BILLING_MODES)}")

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

    if port < 0 or port > 65535:
        raise ValueError("CJ_PORT must be between 0 and 65535")

    if port_search_limit <= 0:
        raise ValueError("CJ_PORT_SEARCH_LIMIT must be > 0")

    if session_sync_seconds <= 0:
        raise ValueError("CJ_SESSION_SYNC_SECONDS must be > 0")

    if snapshot_backfill_seconds <= 0:
        raise ValueError("CJ_SNAPSHOT_BACKFILL_SECONDS must be > 0")

    if transcript_sync_seconds <= 0:
        raise ValueError("CJ_TRANSCRIPT_SYNC_SECONDS must be > 0")

    if openrouter_timeout_seconds <= 0:
        raise ValueError("CJ_OPENROUTER_TIMEOUT_SECONDS must be > 0")

    if claude_max_monthly_usd < 0:
        raise ValueError("CJ_CLAUDE_MAX_MONTHLY_USD must be >= 0")

    if startup_healthcheck_timeout_seconds <= 0:
        raise ValueError("CJ_STARTUP_HEALTHCHECK_TIMEOUT_SECONDS must be > 0")

    if session_sync_enabled and remote_enabled and not remote_ssh_host:
        raise ValueError("CJ_REMOTE_SSH_HOST is required when remote sync is enabled")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    return Settings(
        host=host,
        port=port,
        auto_port=auto_port,
        port_search_limit=port_search_limit,
        openclaw_log_glob=openclaw_log_glob,
        poll_seconds=poll_seconds,
        remote_enabled=remote_enabled,
        remote_gateway_url=remote_gateway_url,
        remote_gateway_token=remote_gateway_token,
        remote_gateway_agent_id=remote_gateway_agent_id,
        remote_ingest_mode=remote_ingest_mode,
        remote_ssh_host=remote_ssh_host,
        remote_openclaw_bin=remote_openclaw_bin,
        remote_path_prefix=remote_path_prefix,
        session_sync_enabled=session_sync_enabled,
        session_sync_seconds=session_sync_seconds,
        transcript_sync_enabled=transcript_sync_enabled,
        transcript_sync_seconds=transcript_sync_seconds,
        transcript_glob=transcript_glob,
        remote_transcript_glob=remote_transcript_glob,
        snapshot_backfill_enabled=snapshot_backfill_enabled,
        snapshot_backfill_seconds=snapshot_backfill_seconds,
        cost_estimation_enabled=cost_estimation_enabled,
        pricing_file=pricing_file,
        openrouter_models_url=openrouter_models_url,
        openrouter_sync_enabled=openrouter_sync_enabled,
        openrouter_timeout_seconds=openrouter_timeout_seconds,
        redaction_enabled=redaction_enabled,
        auth_mode=auth_mode,
        billing_mode=billing_mode,
        claude_max_monthly_usd=claude_max_monthly_usd,
        startup_healthcheck_enabled=startup_healthcheck_enabled,
        startup_healthcheck_timeout_seconds=startup_healthcheck_timeout_seconds,
        db_path=db_path,
    )
