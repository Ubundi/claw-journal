from __future__ import annotations

import logging
import socket
from threading import Thread

import uvicorn

from claw_journal.api import create_app
from claw_journal.backfill import SnapshotBackfillLoop
from claw_journal.config import load_settings
from claw_journal.gateway_client import SshGatewayClient, SshGatewayClientConfig
from claw_journal.ingest import IngestLoop, LogIngestor
from claw_journal.pricing import PricingEngine
from claw_journal.session_sync import SessionSyncLoop
from claw_journal.service import UsageService
from claw_journal.storage import UsageRepository


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


def build_runtime() -> tuple[object, IngestLoop, SessionSyncLoop | None, SnapshotBackfillLoop | None, object]:
    settings = load_settings()
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

    snapshot_backfill_loop = None
    if settings.snapshot_backfill_enabled:
        snapshot_backfill_loop = SnapshotBackfillLoop(
            repository=repository,
            billing_mode=settings.billing_mode,
            interval_seconds=settings.snapshot_backfill_seconds,
            pricing_engine=pricing_engine,
            cost_estimation_enabled=settings.cost_estimation_enabled,
        )

    return app, ingest_loop, session_sync_loop, snapshot_backfill_loop, settings


if __name__ == "__main__":
    app, ingest_loop, session_sync_loop, snapshot_backfill_loop, settings = build_runtime()

    ingest_thread = Thread(target=ingest_loop.run_forever, daemon=True)
    ingest_thread.start()

    if session_sync_loop:
        session_thread = Thread(target=session_sync_loop.run_forever, daemon=True)
        session_thread.start()

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
        logging.info("Dashboard available at %s", _build_local_url(settings.host, resolved_port))

        config = uvicorn.Config(app=app, host=settings.host, port=resolved_port)
        server = uvicorn.Server(config)
        try:
            server.run(sockets=[server_socket])
        finally:
            server_socket.close()
    else:
        logging.info("Dashboard available at %s", _build_local_url(settings.host, settings.port))
        uvicorn.run(app, host=settings.host, port=settings.port)
