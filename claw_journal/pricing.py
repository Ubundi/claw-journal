from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)


DEFAULT_PRICING: dict[str, dict[str, float]] = {
    "anthropic/claude-opus-4-5": {"input_per_million": 15.0, "output_per_million": 75.0},
    "anthropic/claude-sonnet-4-5": {"input_per_million": 3.0, "output_per_million": 15.0},
}


class PricingEngine:
    def __init__(self, table: dict[str, dict[str, float]]) -> None:
        self._table = table
        self._available_models: list[dict[str, object]] = []

    @classmethod
    def from_file(cls, pricing_file: Path | None) -> "PricingEngine":
        merged = dict(DEFAULT_PRICING)

        if pricing_file and pricing_file.exists() and pricing_file.is_file():
            parsed = json.loads(pricing_file.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                for key, value in parsed.items():
                    if isinstance(value, dict):
                        merged[str(key).strip().lower()] = {
                            "input_per_million": float(value.get("input_per_million", 0.0)),
                            "output_per_million": float(value.get("output_per_million", 0.0)),
                        }

        normalized = {
            key.strip().lower(): {
                "input_per_million": float(value.get("input_per_million", 0.0)),
                "output_per_million": float(value.get("output_per_million", 0.0)),
            }
            for key, value in merged.items()
        }
        return cls(normalized)

    @property
    def table(self) -> dict[str, dict[str, float]]:
        return self._table

    @property
    def available_models(self) -> list[dict[str, object]]:
        return self._available_models

    def _set_available_models(self, models: list[dict[str, object]]) -> None:
        self._available_models = models

    def refresh_from_openrouter(self, models_url: str, timeout_seconds: float = 8.0) -> int:
        request = Request(
            models_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "claw-journal/0.1",
            },
        )

        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            logger.warning("OpenRouter models payload missing list data")
            return 0

        imported = 0
        available_models: list[dict[str, object]] = []

        for item in data:
            if not isinstance(item, dict):
                continue

            model_id = str(item.get("id") or "").strip().lower()
            if not model_id:
                continue

            model_name = str(item.get("name") or model_id)
            pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
            top_provider = item.get("top_provider") if isinstance(item.get("top_provider"), dict) else {}

            prompt_rate = _parse_openrouter_price(pricing.get("prompt"))
            completion_rate = _parse_openrouter_price(pricing.get("completion"))
            cache_rate = _parse_openrouter_cache_price(pricing)
            cache_window_tokens = _extract_cache_window_tokens(item=item, top_provider=top_provider)
            if prompt_rate is not None or completion_rate is not None:
                self._table[model_id] = {
                    "input_per_million": float(prompt_rate or 0.0),
                    "output_per_million": float(completion_rate or 0.0),
                }
                imported += 1

                provider, model = _split_model_id(model_id)
                if provider and model:
                    provider_key = f"{provider}/{model}"
                    self._table[provider_key] = {
                        "input_per_million": float(prompt_rate or 0.0),
                        "output_per_million": float(completion_rate or 0.0),
                    }

            provider, model = _split_model_id(model_id)
            available_models.append(
                {
                    "id": model_id,
                    "name": model_name,
                    "provider": provider,
                    "model": model,
                    "input_per_million": float(prompt_rate or 0.0),
                    "output_per_million": float(completion_rate or 0.0),
                    "cache_per_million": float(cache_rate or 0.0),
                    "cache_window_tokens": int(cache_window_tokens or 0),
                    "context_length": int(item.get("context_length") or 0),
                }
            )

        self._set_available_models(available_models)
        return imported

    def save_to_file(self, pricing_file: Path) -> None:
        pricing_file.parent.mkdir(parents=True, exist_ok=True)
        serialized = {
            key: {
                "input_per_million": float(value.get("input_per_million", 0.0)),
                "output_per_million": float(value.get("output_per_million", 0.0)),
            }
            for key, value in sorted(self._table.items())
        }
        pricing_file.write_text(json.dumps(serialized, indent=2), encoding="utf-8")

    def upsert_model_price(
        self,
        provider: str,
        model: str,
        input_per_million: float,
        output_per_million: float,
    ) -> None:
        key = f"{provider}/{model}".strip().lower()
        self._table[key] = {
            "input_per_million": float(input_per_million),
            "output_per_million": float(output_per_million),
        }

    def estimate_cost_breakdown(
        self,
        provider: str | None,
        model: str | None,
        input_tokens: int,
        output_tokens: int,
    ) -> "CostBreakdown" | None:
        if not provider or not model:
            return None

        key = f"{provider}/{model}".strip().lower()
        price = self._table.get(key)
        if not price:
            price = self._table.get(str(model).strip().lower())

        if not price:
            model_key = str(model).strip().lower()
            for table_key, table_value in self._table.items():
                if table_key.endswith(f"/{model_key}"):
                    price = table_value
                    break

        if not price:
            return None

        in_rate = float(price.get("input_per_million", 0.0))
        out_rate = float(price.get("output_per_million", 0.0))

        if in_rate <= 0 and out_rate <= 0:
            return None

        input_cost = (max(input_tokens, 0) / 1_000_000.0) * in_rate
        output_cost = (max(output_tokens, 0) / 1_000_000.0) * out_rate
        total = input_cost + output_cost
        return CostBreakdown(
            total_cost_usd=round(total, 8),
            input_cost_usd=round(input_cost, 8),
            output_cost_usd=round(output_cost, 8),
        )

    def estimate_cost(
        self,
        provider: str | None,
        model: str | None,
        input_tokens: int,
        output_tokens: int,
    ) -> float | None:
        breakdown = self.estimate_cost_breakdown(provider, model, input_tokens, output_tokens)
        if breakdown is None:
            return None
        return breakdown.total_cost_usd


@dataclass(frozen=True)
class CostBreakdown:
    total_cost_usd: float
    input_cost_usd: float
    output_cost_usd: float


def _parse_openrouter_price(value: object) -> float | None:
    if value is None:
        return None
    try:
        per_token = float(str(value))
    except (TypeError, ValueError):
        return None

    if per_token <= 0:
        return 0.0
    return per_token * 1_000_000.0


def _split_model_id(model_id: str) -> tuple[str | None, str | None]:
    parts = model_id.split("/", 1)
    if len(parts) != 2:
        return None, model_id
    return parts[0].strip().lower() or None, parts[1].strip().lower() or None


def _parse_openrouter_cache_price(pricing: dict[str, object]) -> float | None:
    for key in [
        "prompt_cache",
        "cached_prompt",
        "cache_read",
        "cache",
        "input_cache",
    ]:
        value = _parse_openrouter_price(pricing.get(key))
        if value is not None:
            return value
    return None


def _extract_cache_window_tokens(item: dict[str, object], top_provider: dict[str, object]) -> int:
    for source in (item, top_provider):
        for key in [
            "cache_window_tokens",
            "cache_window",
            "cache_context_length",
            "prompt_cache_window",
            "prompt_cache_limit",
            "cached_context_length",
        ]:
            value = _to_int_or_none(source.get(key))
            if value and value > 0:
                return value
    return 0


def _to_int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed
