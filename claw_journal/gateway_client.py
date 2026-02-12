from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class GatewayClientConfig:
    url: str
    token: str


@dataclass(frozen=True)
class SshGatewayClientConfig:
    ssh_host: str
    openclaw_bin: str = "/opt/homebrew/bin/openclaw"
    path_prefix: str = "/opt/homebrew/bin"


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
        if isinstance(payload, dict) and isinstance(payload.get("sessions"), list):
            return payload["sessions"]
        if isinstance(payload, list):
            return payload
        return []


class SshGatewayClient:
    def __init__(self, config: SshGatewayClientConfig) -> None:
        self._config = config

    def list_sessions(self) -> list[dict]:
        remote_command = (
            f"export PATH={self._config.path_prefix}:$PATH && "
            f"{self._config.openclaw_bin} gateway call sessions.list --params '{{}}'"
        )
        command = [
            "ssh",
            "-o",
            "BatchMode=yes",
            self._config.ssh_host,
            remote_command,
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "failed to call remote OpenClaw gateway")

        output = result.stdout or ""
        start = output.find("{")
        if start == -1:
            return []

        payload = json.loads(output[start:])
        if isinstance(payload, dict) and isinstance(payload.get("sessions"), list):
            return payload["sessions"]
        if isinstance(payload, dict) and isinstance(payload.get("result"), list):
            return payload["result"]
        if isinstance(payload, list):
            return payload
        return []
