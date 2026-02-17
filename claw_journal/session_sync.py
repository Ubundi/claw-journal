from __future__ import annotations

import logging
import time
from typing import Protocol

from .storage import UsageRepository


logger = logging.getLogger(__name__)
SESSION_SYNC_LAST_SUCCESS_KEY = "session_sync:last_success_ms"


class SessionClient(Protocol):
    def list_sessions(self) -> list[dict]: ...


class SessionSyncLoop:
    def __init__(
        self,
        repository: UsageRepository,
        session_client: SessionClient,
        interval_seconds: float,
    ) -> None:
        self._repository = repository
        self._session_client = session_client
        self._interval_seconds = interval_seconds
        self._running = False

    def run_forever(self) -> None:
        self._running = True
        logger.info("Starting session sync loop")
        while self._running:
            try:
                sessions = self._session_client.list_sessions()
                upserted = self._repository.upsert_session_snapshots(sessions)
                if upserted:
                    self._repository.upsert_checkpoint(
                        SESSION_SYNC_LAST_SUCCESS_KEY,
                        int(time.time() * 1000),
                    )
                    logger.info("Synced %s gateway sessions", upserted)
            except Exception as exc:
                logger.exception("Session sync cycle failed: %s", exc)
            time.sleep(self._interval_seconds)

    def stop(self) -> None:
        self._running = False
