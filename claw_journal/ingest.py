from __future__ import annotations

import json
import logging
import time
from glob import glob
from pathlib import Path

from .models import normalize_log_event
from .storage import UsageRepository


logger = logging.getLogger(__name__)


class LogIngestor:
    def __init__(self, repository: UsageRepository, log_glob: str) -> None:
        self._repository = repository
        self._log_glob = log_glob

    def poll_once(self) -> int:
        files = sorted(glob(self._log_glob))
        inserted_total = 0

        for file_name in files:
            path = Path(file_name)
            source_key = f"log:{path.resolve()}"
            offset = self._repository.get_checkpoint(source_key)

            if not path.exists():
                continue

            file_size = path.stat().st_size
            if offset > file_size:
                offset = 0

            with path.open("r", encoding="utf-8") as handle:
                handle.seek(offset)
                events = []
                while True:
                    line = handle.readline()
                    if not line:
                        break
                    if not line.strip():
                        continue

                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug("Skipping invalid JSON line in %s", file_name)
                        continue

                    normalized = normalize_log_event(payload, line.strip())
                    if normalized:
                        events.append(normalized)

                new_offset = handle.tell()

            inserted_count = self._repository.insert_usage_events(events)
            inserted_total += inserted_count
            self._repository.upsert_checkpoint(source_key, new_offset)

        return inserted_total


class IngestLoop:
    def __init__(self, ingestor: LogIngestor, poll_seconds: float) -> None:
        self._ingestor = ingestor
        self._poll_seconds = poll_seconds
        self._running = False

    def run_forever(self) -> None:
        self._running = True
        logger.info("Starting ingest loop")
        while self._running:
            try:
                inserted = self._ingestor.poll_once()
                if inserted:
                    logger.info("Ingested %s usage events", inserted)
            except Exception as exc:
                logger.exception("Ingest cycle failed: %s", exc)
            time.sleep(self._poll_seconds)

    def stop(self) -> None:
        self._running = False
