from __future__ import annotations

import json
from pathlib import Path


DEFAULT_PRICING: dict[str, dict[str, float]] = {
    "anthropic/claude-opus-4-5": {"input_per_million": 15.0, "output_per_million": 75.0},
    "anthropic/claude-sonnet-4-5": {"input_per_million": 3.0, "output_per_million": 15.0},
}


class PricingEngine:
    def __init__(self, table: dict[str, dict[str, float]]) -> None:
        self._table = table

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

    def estimate_cost(
        self,
        provider: str | None,
        model: str | None,
        input_tokens: int,
        output_tokens: int,
    ) -> float | None:
        if not provider or not model:
            return None

        key = f"{provider}/{model}".strip().lower()
        price = self._table.get(key)
        if not price:
            return None

        in_rate = float(price.get("input_per_million", 0.0))
        out_rate = float(price.get("output_per_million", 0.0))

        if in_rate <= 0 and out_rate <= 0:
            return None

        value = (max(input_tokens, 0) / 1_000_000.0) * in_rate + (max(output_tokens, 0) / 1_000_000.0) * out_rate
        return round(value, 8)
