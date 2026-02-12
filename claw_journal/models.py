from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
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


@dataclass(slots=True)
class DailyUsageRow:
    usage_date: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float


@dataclass(slots=True)
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



def normalize_log_event(payload: dict[str, Any], raw_json: str) -> NormalizedUsageEvent | None:
    event_name = payload.get("event") or payload.get("name")
    timestamp_raw = payload.get("timestamp") or payload.get("time")
    attrs = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else payload

    if not event_name or not timestamp_raw:
        return None

    try:
        event_ts = datetime.fromisoformat(str(timestamp_raw).replace("Z", "+00:00"))
    except ValueError:
        return None

    input_tokens = _to_int(
        attrs.get("inputTokens")
        or attrs.get("openclaw.tokens.input")
        or attrs.get("token_input")
    )
    output_tokens = _to_int(
        attrs.get("outputTokens")
        or attrs.get("openclaw.tokens.output")
        or attrs.get("token_output")
    )
    total_tokens = _to_int(
        attrs.get("totalTokens")
        or attrs.get("openclaw.tokens.total")
        or input_tokens + output_tokens
    )
    context_tokens = _to_int(
        attrs.get("contextTokens")
        or attrs.get("openclaw.tokens.context")
        or attrs.get("context_tokens")
    )

    if event_name != "model.usage" and total_tokens <= 0 and input_tokens <= 0 and output_tokens <= 0:
        return None

    cost_usd = _to_float(attrs.get("cost") or attrs.get("costUsd") or attrs.get("openclaw.cost.usd"))
    duration_ms = _to_int(attrs.get("durationMs") or attrs.get("duration_ms")) or None

    reasoning_text = None
    if isinstance(attrs.get("reasoning"), str):
        reasoning_text = attrs["reasoning"]
    elif isinstance(attrs.get("thinking"), str):
        reasoning_text = attrs["thinking"]
    elif isinstance(payload.get("message"), dict):
        maybe_reasoning = payload["message"].get("reasoning")
        if isinstance(maybe_reasoning, str):
            reasoning_text = maybe_reasoning

    return NormalizedUsageEvent(
        event_ts=event_ts,
        event_type=str(event_name),
        session_id=attrs.get("sessionId") or attrs.get("openclaw.sessionId"),
        session_key=attrs.get("sessionKey") or attrs.get("openclaw.sessionKey"),
        provider=attrs.get("provider") or attrs.get("openclaw.provider"),
        model=attrs.get("model") or attrs.get("openclaw.model"),
        channel=attrs.get("channel") or attrs.get("openclaw.channel"),
        account_id=attrs.get("accountId") or attrs.get("openclaw.accountId"),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        context_tokens=context_tokens,
        cost_usd=cost_usd,
        duration_ms=duration_ms,
        reasoning_text=reasoning_text,
        raw_json=raw_json,
    )
