from __future__ import annotations

import logging
import time

from .pricing import PricingEngine
from .storage import UsageRepository


logger = logging.getLogger(__name__)


class SnapshotBackfillLoop:
    def __init__(
        self,
        repository: UsageRepository,
        billing_mode: str,
        interval_seconds: float,
        pricing_engine: PricingEngine | None = None,
        cost_estimation_enabled: bool = True,
    ) -> None:
        self._repository = repository
        self._billing_mode = billing_mode
        self._interval_seconds = interval_seconds
        self._pricing_engine = pricing_engine
        self._cost_estimation_enabled = cost_estimation_enabled
        self._running = False

    def run_forever(self) -> None:
        self._running = True
        logger.info("Starting snapshot backfill loop")
        while self._running:
            try:
                estimator = None
                if (
                    self._billing_mode == "token"
                    and self._cost_estimation_enabled
                    and self._pricing_engine is not None
                ):
                    estimator = self._estimate_cost

                inserted = self._repository.backfill_snapshot_deltas(
                    self._billing_mode,
                    cost_estimator=estimator,
                )
                if inserted:
                    logger.info("Backfilled %s snapshot delta events", inserted)
            except Exception as exc:
                logger.exception("Snapshot backfill failed: %s", exc)
            time.sleep(self._interval_seconds)

    def stop(self) -> None:
        self._running = False

    def _estimate_cost(
        self,
        provider: str | None,
        model: str | None,
        input_tokens: int,
        output_tokens: int,
    ) -> tuple[float, float, float] | None:
        if self._pricing_engine is None:
            return None
        breakdown = self._pricing_engine.estimate_cost_breakdown(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        if breakdown is None:
            return None
        return (
            breakdown.total_cost_usd,
            breakdown.input_cost_usd,
            breakdown.output_cost_usd,
        )
