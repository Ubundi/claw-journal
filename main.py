from __future__ import annotations

import logging
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


def build_runtime() -> tuple[object, IngestLoop, SessionSyncLoop | None, SnapshotBackfillLoop | None, object]:
    settings = load_settings()
    repository = UsageRepository(settings.db_path)
    pricing_engine = PricingEngine.from_file(settings.pricing_file)
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

    uvicorn.run(app, host=settings.host, port=settings.port)
