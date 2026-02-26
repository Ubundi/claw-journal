"""Tests for claw_journal.models — usage/cost log parsing."""

import json

import pytest

from claw_journal.models import (
    NormalizedUsageEvent,
    _to_int,
    _to_float,
    _parse_timestamp,
    normalize_log_event,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_TS = "2025-01-15T10:00:00Z"


def _event(payload: dict) -> NormalizedUsageEvent | None:
    raw = json.dumps(payload)
    return normalize_log_event(payload, raw)


# ===================================================================
# _to_int / _to_float
# ===================================================================


class TestToInt:
    def test_valid_int(self):
        assert _to_int(42) == 42

    def test_valid_string(self):
        assert _to_int("100") == 100

    def test_none(self):
        assert _to_int(None) == 0

    def test_invalid_string(self):
        assert _to_int("abc") == 0

    def test_float_truncated(self):
        assert _to_int(3.9) == 3


class TestToFloat:
    def test_valid_float(self):
        assert _to_float(0.05) == 0.05

    def test_valid_string(self):
        assert _to_float("0.123") == 0.123

    def test_none(self):
        assert _to_float(None) is None

    def test_invalid_string(self):
        assert _to_float("nope") is None


# ===================================================================
# _parse_timestamp
# ===================================================================


class TestParseTimestamp:
    def test_timestamp_field(self):
        result = _parse_timestamp({"timestamp": BASE_TS})
        assert result is not None
        assert result.year == 2025

    def test_time_field(self):
        result = _parse_timestamp({"time": BASE_TS})
        assert result is not None

    def test_meta_date_field(self):
        result = _parse_timestamp({"_meta": {"date": BASE_TS}})
        assert result is not None

    def test_missing_returns_none(self):
        assert _parse_timestamp({}) is None

    def test_invalid_returns_none(self):
        assert _parse_timestamp({"timestamp": "garbage"}) is None


# ===================================================================
# normalize_log_event — Token extraction
# ===================================================================


class TestTokenExtraction:
    def test_camel_case_fields(self):
        event = _event({
            "timestamp": BASE_TS,
            "inputTokens": 500,
            "outputTokens": 200,
            "totalTokens": 700,
        })
        assert event is not None
        assert event.input_tokens == 500
        assert event.output_tokens == 200
        assert event.total_tokens == 700

    def test_snake_case_fields(self):
        event = _event({
            "timestamp": BASE_TS,
            "input_tokens": 300,
            "output_tokens": 150,
        })
        assert event is not None
        assert event.input_tokens == 300
        assert event.output_tokens == 150
        assert event.total_tokens == 450  # computed from input + output

    def test_openclaw_namespaced_fields(self):
        event = _event({
            "timestamp": BASE_TS,
            "openclaw.tokens.input": 1000,
            "openclaw.tokens.output": 500,
            "openclaw.tokens.total": 1500,
            "openclaw.tokens.context": 8000,
        })
        assert event is not None
        assert event.input_tokens == 1000
        assert event.output_tokens == 500
        assert event.total_tokens == 1500
        assert event.context_tokens == 8000

    def test_nested_usage_dict(self):
        event = _event({
            "timestamp": BASE_TS,
            "usage": {
                "inputTokens": 250,
                "outputTokens": 100,
            },
        })
        assert event is not None
        assert event.input_tokens == 250
        assert event.output_tokens == 100

    def test_zero_tokens_non_usage_event_returns_none(self):
        event = _event({
            "timestamp": BASE_TS,
            "event": "some.other.event",
            "inputTokens": 0,
            "outputTokens": 0,
        })
        assert event is None

    def test_zero_tokens_model_usage_event_not_filtered(self):
        event = _event({
            "timestamp": BASE_TS,
            "event": "model.usage",
            "inputTokens": 0,
            "outputTokens": 0,
        })
        assert event is not None


# ===================================================================
# normalize_log_event — Cost extraction
# ===================================================================


class TestCostExtraction:
    def test_cost_present_observed(self):
        event = _event({
            "timestamp": BASE_TS,
            "inputTokens": 100,
            "outputTokens": 50,
            "cost": 0.003,
        })
        assert event is not None
        assert event.cost_usd == 0.003
        assert event.cost_source == "observed"

    def test_no_cost_missing(self):
        event = _event({
            "timestamp": BASE_TS,
            "inputTokens": 100,
            "outputTokens": 50,
        })
        assert event is not None
        assert event.cost_usd is None
        assert event.cost_source == "missing"

    def test_input_output_cost(self):
        event = _event({
            "timestamp": BASE_TS,
            "inputTokens": 100,
            "outputTokens": 50,
            "inputCostUsd": 0.001,
            "outputCostUsd": 0.002,
        })
        assert event is not None
        assert event.input_cost_usd == 0.001
        assert event.output_cost_usd == 0.002

    def test_costUsd_alias(self):
        event = _event({
            "timestamp": BASE_TS,
            "inputTokens": 100,
            "outputTokens": 50,
            "costUsd": 0.005,
        })
        assert event is not None
        assert event.cost_usd == 0.005
        assert event.cost_source == "observed"


# ===================================================================
# normalize_log_event — Metadata
# ===================================================================


class TestEventMetadata:
    def test_missing_timestamp_returns_none(self):
        assert _event({"inputTokens": 100, "outputTokens": 50}) is None

    def test_session_and_model(self):
        event = _event({
            "timestamp": BASE_TS,
            "inputTokens": 100,
            "outputTokens": 50,
            "sessionId": "sess-abc",
            "provider": "anthropic",
            "model": "claude-opus-4-6",
        })
        assert event is not None
        assert event.session_id == "sess-abc"
        assert event.provider == "anthropic"
        assert event.model == "claude-opus-4-6"

    def test_duration_ms(self):
        event = _event({
            "timestamp": BASE_TS,
            "inputTokens": 100,
            "outputTokens": 50,
            "durationMs": 1500,
        })
        assert event is not None
        assert event.duration_ms == 1500

    def test_reasoning_text(self):
        event = _event({
            "timestamp": BASE_TS,
            "inputTokens": 100,
            "outputTokens": 50,
            "reasoning": "I considered option A and B...",
        })
        assert event is not None
        assert event.reasoning_text == "I considered option A and B..."

    def test_event_fingerprint_is_sha256(self):
        event = _event({
            "timestamp": BASE_TS,
            "inputTokens": 100,
            "outputTokens": 50,
        })
        assert event is not None
        assert len(event.event_fingerprint) == 64

    def test_event_name_extraction(self):
        event = _event({
            "timestamp": BASE_TS,
            "event": "model.usage",
            "inputTokens": 0,
            "outputTokens": 0,
        })
        assert event is not None
        assert event.event_type == "model.usage"
