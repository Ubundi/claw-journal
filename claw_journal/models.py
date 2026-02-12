from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
import json


@dataclass
class NormalizedUsageEvent:
    event_ts: datetime
    event_type: str
    session_id: str | None
    session_key: str | None
    provider: str | None
    model: str | None
    channel: str | None
    account_id: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    context_tokens: int
    cost_usd: float | None
    duration_ms: int | None
    reasoning_text: str | None
    raw_json: str


@dataclass
class DailyUsageRow:
    usage_date: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float


@dataclass
class SessionUsageRow:
    session_id: str
    provider: str | None
    model: str | None
    total_tokens: int
    cost_usd: float
    last_event_ts: str



def _to_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0



def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_timestamp(payload: dict[str, Any]) -> datetime | None:
    meta = payload.get("_meta") if isinstance(payload.get("_meta"), dict) else {}
    timestamp_raw = payload.get("timestamp") or payload.get("time") or meta.get("date")
    if not timestamp_raw:
        return None

    try:
        return datetime.fromisoformat(str(timestamp_raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_module(payload: dict[str, Any]) -> str | None:
    head = payload.get("0")
    if isinstance(head, str):
        try:
            parsed = json.loads(head)
            if isinstance(parsed, dict):
                return parsed.get("module") or parsed.get("subsystem")
        except json.JSONDecodeError:
            return None
    return None


def _extract_event_name(payload: dict[str, Any]) -> str:
    meta = payload.get("_meta") if isinstance(payload.get("_meta"), dict) else {}
    event_name = payload.get("event") or payload.get("name") or meta.get("name")
    module_name = _extract_module(payload)

    if isinstance(event_name, str) and event_name.strip():
        return event_name
    if isinstance(module_name, str) and module_name.strip():
        return module_name
    return "unknown"


def _build_attrs(payload: dict[str, Any]) -> dict[str, Any]:
    attrs: dict[str, Any] = {}

    envelope_payload = payload.get("1")
    if isinstance(envelope_payload, dict):
        attrs.update(envelope_payload)

    usage_payload = payload.get("usage")
    if isinstance(usage_payload, dict):
        attrs.update(usage_payload)

    explicit_attrs = payload.get("attributes")
    if isinstance(explicit_attrs, dict):
        attrs.update(explicit_attrs)

    attrs.update(payload)
    return attrs


def _pick_first(containers: list[dict[str, Any]], keys: list[str]) -> Any:
    for key in keys:
        for container in containers:
            if key in container and container.get(key) is not None:
                return container.get(key)
    return None



def normalize_log_event(payload: dict[str, Any], raw_json: str) -> NormalizedUsageEvent | None:
    event_name = _extract_event_name(payload)
    event_ts = _parse_timestamp(payload)
    if not event_ts:
        return None

    attrs = _build_attrs(payload)
    containers = [
        attrs,
        payload,
        attrs.get("usage") if isinstance(attrs.get("usage"), dict) else {},
        payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
    ]

    input_tokens = _to_int(
        _pick_first(
            containers,
            [
                "inputTokens",
                "input_tokens",
                "openclaw.tokens.input",
                "token_input",
                "prompt_tokens",
            ],
        )
    )
    output_tokens = _to_int(
        _pick_first(
            containers,
            [
                "outputTokens",
                "output_tokens",
                "openclaw.tokens.output",
                "token_output",
                "completion_tokens",
            ],
        )
    )
    total_tokens = _to_int(
        _pick_first(
            containers,
            [
                "totalTokens",
                "total_tokens",
                "openclaw.tokens.total",
                "total",
            ],
        )
        or input_tokens + output_tokens
    )
    context_tokens = _to_int(
        _pick_first(
            containers,
            [
                "contextTokens",
                "context_tokens",
                "openclaw.tokens.context",
            ],
        )
    )

    if event_name != "model.usage" and total_tokens <= 0 and input_tokens <= 0 and output_tokens <= 0:
        return None

    cost_usd = _to_float(
        _pick_first(containers, ["cost", "costUsd", "openclaw.cost.usd", "usdCost"])
    )
    duration_ms = _to_int(
        _pick_first(containers, ["durationMs", "duration_ms", "latencyMs", "responseMs"])
    ) or None

    reasoning_text = None
    if isinstance(attrs.get("reasoning"), str):
        reasoning_text = attrs["reasoning"]
    elif isinstance(attrs.get("thinking"), str):
        reasoning_text = attrs["thinking"]
    elif isinstance(attrs.get("message"), dict):
        maybe_reasoning = attrs["message"].get("reasoning")
        if isinstance(maybe_reasoning, str):
            reasoning_text = maybe_reasoning
    elif isinstance(payload.get("message"), dict):
        maybe_reasoning = payload["message"].get("reasoning")
        if isinstance(maybe_reasoning, str):
            reasoning_text = maybe_reasoning

    return NormalizedUsageEvent(
        event_ts=event_ts,
        event_type=str(event_name),
        session_id=_pick_first(containers, ["sessionId", "openclaw.sessionId"]),
        session_key=_pick_first(containers, ["sessionKey", "openclaw.sessionKey"]),
        provider=_pick_first(containers, ["provider", "openclaw.provider"]),
        model=_pick_first(containers, ["model", "openclaw.model"]),
        channel=_pick_first(containers, ["channel", "openclaw.channel"]),
        account_id=_pick_first(containers, ["accountId", "openclaw.accountId"]),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        context_tokens=context_tokens,
        cost_usd=cost_usd,
        duration_ms=duration_ms,
        reasoning_text=reasoning_text,
        raw_json=raw_json,
    )
