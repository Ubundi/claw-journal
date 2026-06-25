from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


def _detect_openclaw_bin() -> str:
    """Resolve the openclaw CLI without hardcoding one machine's install path.

    Order: CJ_OPENCLAW_BIN override -> PATH lookup -> bare "openclaw".
    (Previously hardcoded to the macOS Homebrew path, which broke on Linux hosts.)
    """
    return os.environ.get("CJ_OPENCLAW_BIN") or shutil.which("openclaw") or "openclaw"


def _detect_path_prefix() -> str:
    parent = str(Path(_detect_openclaw_bin()).parent)
    return parent if parent and parent != "." else "/usr/bin"


@dataclass(frozen=True)
class GatewayClientConfig:
    url: str
    token: str


@dataclass(frozen=True)
class SshGatewayClientConfig:
    ssh_host: str
    openclaw_bin: str = field(default_factory=_detect_openclaw_bin)
    path_prefix: str = field(default_factory=_detect_path_prefix)


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


class LocalGatewayClient:
    """Calls the OpenClaw gateway on the local machine (no SSH)."""

    def __init__(self, config: SshGatewayClientConfig) -> None:
        self._config = config

    def list_sessions(self) -> list[dict]:
        command = [
            self._config.openclaw_bin,
            "gateway",
            "call",
            "sessions.list",
            "--params",
            "{}",
        ]
        env = {**os.environ, "PATH": f"{self._config.path_prefix}:{os.environ.get('PATH', '')}"}
        result = subprocess.run(command, capture_output=True, text=True, check=False, env=env)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "failed to call local OpenClaw gateway")

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
