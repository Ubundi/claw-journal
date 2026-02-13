from __future__ import annotations

import json
from dataclasses import dataclass
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

    @property
    def table(self) -> dict[str, dict[str, float]]:
        return self._table

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
