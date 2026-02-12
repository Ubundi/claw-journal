from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class GatewayClientConfig:
    url: str
    token: str


class GatewayClient:
    def __init__(self, config: GatewayClientConfig) -> None:
        self._config = config

    def list_sessions(self) -> list[dict]:
        command = [
            "openclaw",
            "gateway",
            "call",
            "sessions.list",
            "--params",
            "{}",
            "--url",
            self._config.url,
            "--token",
            self._config.token,
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "failed to call OpenClaw gateway")

        payload = json.loads(result.stdout or "{}")
        if isinstance(payload, dict) and isinstance(payload.get("result"), list):
            return payload["result"]
        if isinstance(payload, list):
            return payload
        return []
