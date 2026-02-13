from __future__ import annotations

import json
import re
from typing import Any


SENSITIVE_KEY_RE = re.compile(
    r"(token|secret|password|api[_-]?key|authorization|cookie|session|refresh|access)",
    re.IGNORECASE,
)

BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE)
LONG_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_\-]{24,}\b")


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if SENSITIVE_KEY_RE.search(str(key)) else _redact_value(sub_value)
            for key, sub_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        masked = BEARER_RE.sub("Bearer [REDACTED]", value)
        masked = LONG_TOKEN_RE.sub(lambda m: "[REDACTED]" if _looks_sensitive(m.group(0)) else m.group(0), masked)
        return masked
    return value


def _looks_sensitive(value: str) -> bool:
    lower = value.lower()
    if any(marker in lower for marker in ["sk-", "ghp_", "eyj", "token", "secret", "passwd"]):
        return True
    digit_count = sum(ch.isdigit() for ch in value)
    alpha_count = sum(ch.isalpha() for ch in value)
    return len(value) >= 32 and digit_count > 0 and alpha_count > 0


def redact_raw_json_line(raw_line: str) -> str:
    line = raw_line.strip()
    if not line:
        return line

    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return BEARER_RE.sub("Bearer [REDACTED]", line)

    redacted = _redact_value(payload)
    return json.dumps(redacted, separators=(",", ":"), ensure_ascii=False)
