from __future__ import annotations

import logging
import time

from .storage import UsageRepository


logger = logging.getLogger(__name__)


class SnapshotBackfillLoop:
    def __init__(
        self,
        repository: UsageRepository,
        billing_mode: str,
        interval_seconds: float,
    ) -> None:
        self._repository = repository
        self._billing_mode = billing_mode
        self._interval_seconds = interval_seconds
        self._running = False

    def run_forever(self) -> None:
        self._running = True
        logger.info("Starting snapshot backfill loop")
        while self._running:
            try:
                inserted = self._repository.backfill_snapshot_deltas(self._billing_mode)
                if inserted:
                    logger.info("Backfilled %s snapshot delta events", inserted)
            except Exception as exc:
                logger.exception("Snapshot backfill failed: %s", exc)
            time.sleep(self._interval_seconds)

    def stop(self) -> None:
        self._running = False
