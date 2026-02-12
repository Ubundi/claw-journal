from __future__ import annotations

import logging
from threading import Thread

import uvicorn

from claw_journal.api import create_app
from claw_journal.config import load_settings
from claw_journal.ingest import IngestLoop, LogIngestor
from claw_journal.service import UsageService
from claw_journal.storage import UsageRepository


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


def build_runtime() -> tuple[object, IngestLoop, object]:
    settings = load_settings()
    repository = UsageRepository(settings.db_path)
    usage_service = UsageService(repository)
    app = create_app(usage_service)

    ingestor = LogIngestor(repository=repository, log_glob=settings.openclaw_log_glob)
    ingest_loop = IngestLoop(ingestor=ingestor, poll_seconds=settings.poll_seconds)

    return app, ingest_loop, settings


if __name__ == "__main__":
    app, ingest_loop, settings = build_runtime()

    ingest_thread = Thread(target=ingest_loop.run_forever, daemon=True)
    ingest_thread.start()

    uvicorn.run(app, host=settings.host, port=settings.port)
