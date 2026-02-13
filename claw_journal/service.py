from __future__ import annotations

from .config import Settings
from .pricing import PricingEngine
from .storage import UsageRepository


class UsageService:
    def __init__(
        self,
        repository: UsageRepository,
        settings: Settings,
        pricing_engine: PricingEngine,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._pricing_engine = pricing_engine

    def daily_usage(self, days: int = 30) -> list[dict]:
        return [row.__dict__ for row in self._repository.get_daily_usage(days=days)]

    def session_usage(self, limit: int = 100) -> list[dict]:
        return [row.__dict__ for row in self._repository.get_session_usage(limit=limit)]

    def reasoning_events(self, limit: int = 100) -> list[dict]:
        return self._repository.get_reasoning_events(limit=limit)

    def reconciled_session_usage(self, limit: int = 100) -> list[dict]:
        return self._repository.get_reconciled_session_usage(limit=limit)

    def cost_source_summary(self) -> dict:
        return self._repository.get_cost_source_summary()

    def system_profile(self) -> dict:
        costs = self._repository.get_cost_source_summary()
        data_status = self._repository.get_data_status()

        if self._settings.auth_mode == "auto":
            inferred_auth_mode = "api_key" if costs.get("observed", 0) > 0 else "oauth"
        else:
            inferred_auth_mode = self._settings.auth_mode

        notes: list[str] = []
        if not data_status["log_usage_available"] and data_status["reconciled_available"]:
            notes.append("Session totals are available from gateway reconciliation, but log-derived usage events are absent.")
        if inferred_auth_mode == "oauth" and self._settings.billing_mode == "token":
            notes.append("OAuth mode typically hides direct per-response costs; token-mode costs may require local estimation.")
        if self._settings.billing_mode == "claude_max":
            notes.append("Claude Max billing mode is active; token costs are shown as included in subscription.")

        return {
            "auth_mode": inferred_auth_mode,
            "auth_mode_config": self._settings.auth_mode,
            "billing_mode": self._settings.billing_mode,
            "claude_max_monthly_usd": self._settings.claude_max_monthly_usd,
            "plan_cost": self.plan_cost_summary(),
            "cost_sources": costs,
            "data_status": data_status,
            "notes": notes,
        }

    def plan_cost_summary(self) -> dict:
        if self._settings.billing_mode != "claude_max":
            return {
                "enabled": False,
                "monthly_usd": 0.0,
                "daily_usd": 0.0,
            }

        daily = round(self._settings.claude_max_monthly_usd / 30.4375, 4)
        return {
            "enabled": True,
            "monthly_usd": float(self._settings.claude_max_monthly_usd),
            "daily_usd": daily,
        }

    def pricing_table(self) -> dict:
        return {"rows": self._pricing_engine.table}

    def upsert_model_pricing(
        self,
        provider: str,
        model: str,
        input_per_million: float,
        output_per_million: float,
    ) -> dict:
        self._pricing_engine.upsert_model_price(
            provider=provider,
            model=model,
            input_per_million=input_per_million,
            output_per_million=output_per_million,
        )
        if self._settings.pricing_file:
            self._pricing_engine.save_to_file(self._settings.pricing_file)
        return {
            "provider": provider,
            "model": model,
            "input_per_million": input_per_million,
            "output_per_million": output_per_million,
        }
