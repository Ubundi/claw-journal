from __future__ import annotations

import logging
import os
import shutil
import socket
import time
from threading import Thread
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

from claw_journal.api import create_app
from claw_journal.backfill import SnapshotBackfillLoop
from claw_journal.config import load_settings
from claw_journal.gateway_client import LocalGatewayClient, SshGatewayClient, SshGatewayClientConfig
from claw_journal.ingest import IngestLoop, LogIngestor
from claw_journal.pricing import PricingEngine
from claw_journal.session_sync import SessionSyncLoop
from claw_journal.service import UsageService
from claw_journal.storage import UsageRepository
from claw_journal.transcript_sync import TranscriptSyncLoop
from claw_journal.transcript_ingest import TranscriptIngestLoop, TranscriptIngestor


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


def _bind_open_port(host: str, requested_port: int, search_limit: int) -> socket.socket:
    candidates = [requested_port] if requested_port > 0 else [0]
    if requested_port > 0:
        candidates.extend(range(requested_port + 1, requested_port + search_limit + 1))

    last_error: OSError | None = None
    for port in candidates:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server_socket.bind((host, port))
            return server_socket
        except OSError as exc:
            last_error = exc
            server_socket.close()

    max_port = requested_port + search_limit
    raise RuntimeError(
        f"Unable to bind an open port on {host} in range {requested_port}-{max_port}"
    ) from last_error


def _build_local_url(host: str, port: int) -> str:
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{display_host}:{port}"


def _run_startup_health_check(base_url: str, timeout_seconds: float) -> None:
    endpoints = ["/health", "/api/system/connection"]
    deadline = time.monotonic() + timeout_seconds
    last_error = "no response"

    while time.monotonic() < deadline:
        all_ok = True
        for endpoint in endpoints:
            url = f"{base_url}{endpoint}"
            try:
                with urlopen(url, timeout=2.0) as response:
                    status = int(getattr(response, "status", 200))
                if status >= 400:
                    all_ok = False
                    last_error = f"{endpoint} returned status {status}"
                    break
            except (URLError, OSError) as exc:
                all_ok = False
                last_error = f"{endpoint} unreachable: {exc}"
                break

        if all_ok:
            logging.info("Startup health check passed for %s", ", ".join(endpoints))
            return

        time.sleep(0.5)

    raise RuntimeError(
        "Startup health check failed after "
        f"{timeout_seconds:.1f}s at {base_url}: {last_error}"
    )


def _start_startup_health_probe(base_url: str, timeout_seconds: float) -> None:
    def _probe() -> None:
        try:
            _run_startup_health_check(base_url=base_url, timeout_seconds=timeout_seconds)
        except Exception as exc:
            logging.error("%s", exc)
            os._exit(1)

    Thread(target=_probe, daemon=True, name="startup-health-check").start()


def _warn_if_local_openclaw_missing(remote_enabled: bool) -> None:
    if remote_enabled:
        return
    if shutil.which("openclaw") is not None:
        return

    logging.warning(
        "`openclaw` was not found in PATH for the current user. "
        "Claw Journal can still run from existing logs, but local OpenClaw sync "
        "and live usage capture may be incomplete until `openclaw` is installed "
        "or available on PATH."
    )


def build_runtime() -> tuple[
    object,
    IngestLoop,
    SessionSyncLoop | None,
    TranscriptSyncLoop | None,
    TranscriptIngestLoop | None,
    SnapshotBackfillLoop | None,
    object,
]:
    settings = load_settings()
    _warn_if_local_openclaw_missing(remote_enabled=settings.remote_enabled)
    repository = UsageRepository(settings.db_path)
    pricing_engine = PricingEngine.from_file(settings.pricing_file)

    if settings.openrouter_sync_enabled:
        try:
            imported = pricing_engine.refresh_from_openrouter(
                models_url=settings.openrouter_models_url,
                timeout_seconds=settings.openrouter_timeout_seconds,
            )
            if imported:
                logging.info("Imported %s model pricing rows from OpenRouter", imported)
                if settings.pricing_file:
                    pricing_engine.save_to_file(settings.pricing_file)
            else:
                logging.info("No model pricing rows imported from OpenRouter")
        except Exception as exc:
            logging.warning("OpenRouter pricing sync failed; continuing with local pricing table: %s", exc)

    usage_service = UsageService(repository, settings, pricing_engine)
    app = create_app(usage_service)

    ingestor = LogIngestor(
        repository=repository,
        log_glob=settings.openclaw_log_glob,
        remote_enabled=settings.remote_enabled,
        remote_ssh_host=settings.remote_ssh_host,
        pricing_engine=pricing_engine,
        cost_estimation_enabled=settings.cost_estimation_enabled,
        redaction_enabled=settings.redaction_enabled,
        billing_mode=settings.billing_mode,
    )
    ingest_loop = IngestLoop(ingestor=ingestor, poll_seconds=settings.poll_seconds)

    session_sync_loop = None
    if settings.session_sync_enabled and settings.remote_enabled and settings.remote_ssh_host:
        session_client = SshGatewayClient(
            SshGatewayClientConfig(
                ssh_host=settings.remote_ssh_host,
                openclaw_bin=settings.remote_openclaw_bin,
                path_prefix=settings.remote_path_prefix,
            )
        )
        session_sync_loop = SessionSyncLoop(
            repository=repository,
            session_client=session_client,
            interval_seconds=settings.session_sync_seconds,
        )
    elif settings.session_sync_enabled and not settings.remote_enabled:
        session_client = LocalGatewayClient(
            SshGatewayClientConfig(
                ssh_host="localhost",
                openclaw_bin=settings.remote_openclaw_bin,
                path_prefix=settings.remote_path_prefix,
            )
        )
        session_sync_loop = SessionSyncLoop(
            repository=repository,
            session_client=session_client,
            interval_seconds=settings.session_sync_seconds,
        )

    # Transcript sync loop (dev): syncs raw conversation messages for /chat pages
    transcript_sync_enabled = settings.transcript_sync_enabled
    if settings.remote_enabled and settings.transcript_ingest_enabled and transcript_sync_enabled:
        logging.info(
            "Remote transcript ingest is enabled; disabling transcript sync loop to avoid duplicate transcript ingestion"
        )
        transcript_sync_enabled = False

    transcript_sync_loop = None
    if transcript_sync_enabled:
        transcript_sync_loop = TranscriptSyncLoop(
            repository=repository,
            interval_seconds=settings.transcript_sync_seconds,
            local_transcript_glob=settings.transcript_glob,
            remote_enabled=settings.remote_enabled,
            remote_ssh_host=settings.remote_ssh_host,
            remote_transcript_glob=settings.remote_transcript_glob,
        )

    # Transcript ingest loop (reasoning): parses JSONL into thinking/tool/model tables
    transcript_ingest_loop = None
    if settings.transcript_ingest_enabled:
        transcript_ingestor = TranscriptIngestor(
            repository=repository,
            transcript_glob=settings.transcript_glob,
            remote_enabled=settings.remote_enabled,
            remote_ssh_host=settings.remote_ssh_host,
            remote_transcript_glob=settings.remote_transcript_glob,
        )
        transcript_ingest_loop = TranscriptIngestLoop(
            ingestor=transcript_ingestor,
            poll_seconds=settings.transcript_poll_seconds,
        )

    snapshot_backfill_loop = None
    if settings.snapshot_backfill_enabled:
        snapshot_backfill_loop = SnapshotBackfillLoop(
            repository=repository,
            billing_mode=settings.billing_mode,
            interval_seconds=settings.snapshot_backfill_seconds,
            pricing_engine=pricing_engine,
            cost_estimation_enabled=settings.cost_estimation_enabled,
        )

    return (
        app,
        ingest_loop,
        session_sync_loop,
        transcript_sync_loop,
        transcript_ingest_loop,
        snapshot_backfill_loop,
        settings,
    )


if __name__ == "__main__":
    (
        app,
        ingest_loop,
        session_sync_loop,
        transcript_sync_loop,
        transcript_ingest_loop,
        snapshot_backfill_loop,
        settings,
    ) = build_runtime()

    ingest_thread = Thread(target=ingest_loop.run_forever, daemon=True)
    ingest_thread.start()

    if session_sync_loop:
        session_thread = Thread(target=session_sync_loop.run_forever, daemon=True)
        session_thread.start()

    if transcript_sync_loop:
        transcript_thread = Thread(target=transcript_sync_loop.run_forever, daemon=True)
        transcript_thread.start()

    if transcript_ingest_loop:
        ingest_reasoning_thread = Thread(target=transcript_ingest_loop.run_forever, daemon=True)
        ingest_reasoning_thread.start()

    if snapshot_backfill_loop:
        snapshot_thread = Thread(target=snapshot_backfill_loop.run_forever, daemon=True)
        snapshot_thread.start()

    if settings.auto_port:
        server_socket = _bind_open_port(
            host=settings.host,
            requested_port=settings.port,
            search_limit=settings.port_search_limit,
        )
        resolved_port = int(server_socket.getsockname()[1])
        if settings.port > 0 and resolved_port != settings.port:
            logging.info(
                "CJ_PORT=%s is busy; using open port %s instead",
                settings.port,
                resolved_port,
            )
        local_url = _build_local_url(settings.host, resolved_port)
        logging.info("Dashboard available at %s", local_url)
        if settings.startup_healthcheck_enabled:
            _start_startup_health_probe(
                base_url=local_url,
                timeout_seconds=settings.startup_healthcheck_timeout_seconds,
            )
        else:
            logging.info("Startup health check disabled by CJ_STARTUP_HEALTHCHECK_ENABLED=false")

        config = uvicorn.Config(app=app, host=settings.host, port=resolved_port)
        server = uvicorn.Server(config)
        try:
            server.run(sockets=[server_socket])
        finally:
            server_socket.close()
    else:
        local_url = _build_local_url(settings.host, settings.port)
        logging.info("Dashboard available at %s", local_url)
        if settings.startup_healthcheck_enabled:
            _start_startup_health_probe(
                base_url=local_url,
                timeout_seconds=settings.startup_healthcheck_timeout_seconds,
            )
        else:
            logging.info("Startup health check disabled by CJ_STARTUP_HEALTHCHECK_ENABLED=false")
        uvicorn.run(app, host=settings.host, port=settings.port)
