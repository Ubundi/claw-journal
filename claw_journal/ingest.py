from __future__ import annotations

import json
import logging
import subprocess
import time
from datetime import datetime, timezone
from glob import glob
from pathlib import Path

from .models import normalize_log_event
from .pricing import PricingEngine
from .redaction import redact_raw_json_line
from .storage import UsageRepository


logger = logging.getLogger(__name__)


class LogIngestor:
    def __init__(
        self,
        repository: UsageRepository,
        log_glob: str,
        remote_enabled: bool = False,
        remote_ssh_host: str | None = None,
        pricing_engine: PricingEngine | None = None,
        cost_estimation_enabled: bool = True,
        redaction_enabled: bool = True,
        billing_mode: str = "token",
    ) -> None:
        self._repository = repository
        self._log_glob = log_glob
        self._remote_enabled = remote_enabled
        self._remote_ssh_host = remote_ssh_host
        self._pricing_engine = pricing_engine
        self._cost_estimation_enabled = cost_estimation_enabled
        self._redaction_enabled = redaction_enabled
        self._billing_mode = billing_mode

    def poll_once(self) -> int:
        if self._remote_enabled and self._remote_ssh_host:
            return self._poll_remote()

        return self._poll_local()

    def _poll_local(self) -> int:
        files = sorted(glob(self._log_glob))
        inserted_total = 0

        for file_name in files:
            path = Path(file_name)
            source_key = f"log:{path.resolve()}"
            offset = self._repository.get_checkpoint(source_key)

            if not path.exists():
                continue

            file_size = path.stat().st_size
            if offset > file_size:
                offset = 0

            with path.open("r", encoding="utf-8") as handle:
                handle.seek(offset)
                events = []
                while True:
                    line = handle.readline()
                    if not line:
                        break
                    if not line.strip():
                        continue

                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug("Skipping invalid JSON line in %s", file_name)
                        continue

                    raw_json = line.strip()
                    safe_raw_json = redact_raw_json_line(raw_json) if self._redaction_enabled else raw_json

                    normalized = normalize_log_event(payload, safe_raw_json)
                    if normalized:
                        normalized.billing_mode = self._billing_mode

                        if self._billing_mode == "claude_max":
                            normalized.cost_usd = 0.0
                            normalized.input_cost_usd = 0.0
                            normalized.output_cost_usd = 0.0
                            normalized.cost_source = "subscription"

                        if (
                            self._billing_mode == "token"
                            and self._cost_estimation_enabled
                            and normalized.cost_usd is None
                            and self._pricing_engine is not None
                        ):
                            breakdown = self._pricing_engine.estimate_cost_breakdown(
                                provider=normalized.provider,
                                model=normalized.model,
                                input_tokens=normalized.input_tokens,
                                output_tokens=normalized.output_tokens,
                            )
                            if breakdown is not None:
                                normalized.cost_usd = breakdown.total_cost_usd
                                normalized.input_cost_usd = breakdown.input_cost_usd
                                normalized.output_cost_usd = breakdown.output_cost_usd
                                normalized.cost_source = "estimated"

                        if normalized.cost_usd is not None:
                            if normalized.input_cost_usd is None:
                                normalized.input_cost_usd = 0.0
                            if normalized.output_cost_usd is None:
                                normalized.output_cost_usd = 0.0

                        events.append(normalized)

                new_offset = handle.tell()

            inserted_count = self._repository.insert_usage_events(events)
            inserted_total += inserted_count
            self._repository.upsert_checkpoint(source_key, new_offset)

        return inserted_total

    def _poll_remote(self) -> int:
        if not self._remote_ssh_host:
            return 0

        inserted_total = 0
        listed = self._remote_list_files()

        for row in listed:
            source_path = str(row.get("path") or "")
            file_size = int(row.get("size") or 0)
            if not source_path:
                continue

            source_key = f"log:{self._remote_ssh_host}:{source_path}"
            offset = self._repository.get_checkpoint(source_key)
            if offset > file_size:
                offset = 0
            if file_size <= offset:
                continue

            content = self._remote_read_from_offset(path=source_path, offset=offset)
            if content is None:
                continue

            events = []
            for line in content.splitlines():
                if not line.strip():
                    continue

                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("Skipping invalid JSON line in remote log %s", source_path)
                    continue

                raw_json = line.strip()
                safe_raw_json = redact_raw_json_line(raw_json) if self._redaction_enabled else raw_json

                normalized = normalize_log_event(payload, safe_raw_json)
                if normalized:
                    normalized.billing_mode = self._billing_mode

                    if self._billing_mode == "claude_max":
                        normalized.cost_usd = 0.0
                        normalized.input_cost_usd = 0.0
                        normalized.output_cost_usd = 0.0
                        normalized.cost_source = "subscription"

                    if (
                        self._billing_mode == "token"
                        and self._cost_estimation_enabled
                        and normalized.cost_usd is None
                        and self._pricing_engine is not None
                    ):
                        breakdown = self._pricing_engine.estimate_cost_breakdown(
                            provider=normalized.provider,
                            model=normalized.model,
                            input_tokens=normalized.input_tokens,
                            output_tokens=normalized.output_tokens,
                        )
                        if breakdown is not None:
                            normalized.cost_usd = breakdown.total_cost_usd
                            normalized.input_cost_usd = breakdown.input_cost_usd
                            normalized.output_cost_usd = breakdown.output_cost_usd
                            normalized.cost_source = "estimated"

                    if normalized.cost_usd is not None:
                        if normalized.input_cost_usd is None:
                            normalized.input_cost_usd = 0.0
                        if normalized.output_cost_usd is None:
                            normalized.output_cost_usd = 0.0

                    events.append(normalized)

            inserted_count = self._repository.insert_usage_events(events)
            inserted_total += inserted_count
            self._repository.upsert_checkpoint(source_key, file_size)

        return inserted_total

    def _remote_list_files(self) -> list[dict]:
        script = """
import glob
import json
import os

pattern = os.path.expanduser(__PATTERN__)
rows = []
for path in sorted(glob.glob(pattern)):
    try:
        stat = os.stat(path)
    except OSError:
        continue
    rows.append({"path": path, "size": int(stat.st_size), "modified_at": int(stat.st_mtime)})
print(json.dumps(rows))
""".replace("__PATTERN__", json.dumps(self._log_glob))

        output = self._run_remote_python(script)
        if not output:
            return []

        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            logger.warning("Failed to parse remote log listing output")
            return []

        if not isinstance(payload, list):
            return []

        rows: list[dict] = []
        for row in payload:
            if not isinstance(row, dict):
                continue

            modified_raw = row.get("modified_at")
            modified_ts = None
            if isinstance(modified_raw, (int, float)):
                modified_ts = datetime.fromtimestamp(float(modified_raw), tz=timezone.utc).isoformat()

            rows.append(
                {
                    "path": row.get("path"),
                    "size": int(row.get("size") or 0),
                    "modified_at": modified_ts,
                }
            )

        return rows

    def _remote_read_from_offset(self, path: str, offset: int) -> str | None:
        script = """
import os
import sys

path = __PATH__
offset = __OFFSET__
if not os.path.exists(path):
    sys.exit(0)

with open(path, "rb") as handle:
    handle.seek(offset)
    data = handle.read()

sys.stdout.write(data.decode("utf-8", errors="replace"))
""".replace("__PATH__", json.dumps(path)).replace("__OFFSET__", str(int(offset)))

        return self._run_remote_python(script)

    def _run_remote_python(self, script: str) -> str | None:
        if not self._remote_ssh_host:
            return None

        command = [
            "ssh",
            "-o",
            "BatchMode=yes",
            self._remote_ssh_host,
            "python3 -",
        ]

        result = subprocess.run(
            command,
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            if stderr:
                logger.warning("Remote log ingest command failed: %s", stderr)
            return None
        return result.stdout


class IngestLoop:
    def __init__(self, ingestor: LogIngestor, poll_seconds: float) -> None:
        self._ingestor = ingestor
        self._poll_seconds = poll_seconds
        self._running = False

    def run_forever(self) -> None:
        self._running = True
        logger.info("Starting ingest loop")
        while self._running:
            try:
                inserted = self._ingestor.poll_once()
                if inserted:
                    logger.info("Ingested %s usage events", inserted)
            except Exception as exc:
                logger.exception("Ingest cycle failed: %s", exc)
            time.sleep(self._poll_seconds)

    def stop(self) -> None:
        self._running = False
