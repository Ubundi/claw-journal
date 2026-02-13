from __future__ import annotations

import json
import logging
import time
from glob import glob
from pathlib import Path

from .models import normalize_log_event
from .pricing import PricingEngine
from .redaction import redact_raw_json_line
from .storage import UsageRepository


logger = logging.getLogger(__name__)


class LogIngestor:
    def __init__(
        self,
        repository: UsageRepository,
        log_glob: str,
        pricing_engine: PricingEngine | None = None,
        cost_estimation_enabled: bool = True,
        redaction_enabled: bool = True,
        billing_mode: str = "token",
    ) -> None:
        self._repository = repository
        self._log_glob = log_glob
        self._pricing_engine = pricing_engine
        self._cost_estimation_enabled = cost_estimation_enabled
        self._redaction_enabled = redaction_enabled
        self._billing_mode = billing_mode

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

                    raw_json = line.strip()
                    safe_raw_json = redact_raw_json_line(raw_json) if self._redaction_enabled else raw_json

                    normalized = normalize_log_event(payload, safe_raw_json)
                    if normalized:
                        normalized.billing_mode = self._billing_mode

                        if self._billing_mode == "claude_max":
                            normalized.cost_usd = 0.0
                            normalized.input_cost_usd = 0.0
                            normalized.output_cost_usd = 0.0
                            normalized.cost_source = "subscription"

                        if (
                            self._billing_mode == "token"
                            and self._cost_estimation_enabled
                            and normalized.cost_usd is None
                            and self._pricing_engine is not None
                        ):
                            breakdown = self._pricing_engine.estimate_cost_breakdown(
                                provider=normalized.provider,
                                model=normalized.model,
                                input_tokens=normalized.input_tokens,
                                output_tokens=normalized.output_tokens,
                            )
                            if breakdown is not None:
                                normalized.cost_usd = breakdown.total_cost_usd
                                normalized.input_cost_usd = breakdown.input_cost_usd
                                normalized.output_cost_usd = breakdown.output_cost_usd
                                normalized.cost_source = "estimated"

                        if normalized.cost_usd is not None:
                            if normalized.input_cost_usd is None:
                                normalized.input_cost_usd = 0.0
                            if normalized.output_cost_usd is None:
                                normalized.output_cost_usd = 0.0

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
