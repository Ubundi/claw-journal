from __future__ import annotations

import json
import logging
import subprocess
import time
from glob import glob
from pathlib import Path

from .storage import UsageRepository
from .transcript_models import (
    ConversationMessage,
    extract_thinking_blocks,
    extract_tool_invocations,
    normalize_transcript_turn,
    parse_model_change,
)

logger = logging.getLogger(__name__)


class TranscriptIngestor:
    def __init__(
        self,
        repository: UsageRepository,
        transcript_glob: str,
        remote_enabled: bool = False,
        remote_ssh_host: str | None = None,
        remote_transcript_glob: str | None = None,
    ) -> None:
        self._repository = repository
        self._transcript_glob = transcript_glob
        self._remote_enabled = remote_enabled
        self._remote_ssh_host = remote_ssh_host
        self._remote_transcript_glob = remote_transcript_glob or transcript_glob

    def poll_once(self) -> int:
        if self._remote_enabled and self._remote_ssh_host:
            return self._poll_remote()

        return self._poll_local()

    def _poll_local(self) -> int:
        expanded = str(Path(self._transcript_glob).expanduser())
        files = sorted(glob(expanded))
        inserted_total = 0

        for file_name in files:
            path = Path(file_name)
            source_key = f"transcript:{path.resolve()}"
            offset = self._repository.get_checkpoint(source_key)

            if not path.exists():
                continue

            file_size = path.stat().st_size
            if offset > file_size:
                offset = 0

            # Derive session_id and agent_id from path
            session_id = path.stem
            agent_id = None
            parts = path.parts
            try:
                sessions_idx = parts.index("sessions")
                if sessions_idx >= 2 and parts[sessions_idx - 2] == "agents":
                    agent_id = parts[sessions_idx - 1]
            except ValueError:
                pass

            existing_count = self._repository.get_message_count_for_session(session_id)

            with path.open("r", encoding="utf-8") as handle:
                handle.seek(offset)
                messages: list[tuple[ConversationMessage, str | None]] = []
                model_changes = []
                turn_index = existing_count
                last_user_text: str | None = None

                while True:
                    line = handle.readline()
                    if not line:
                        break
                    if not line.strip():
                        continue

                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug("Skipping invalid JSON in transcript %s", file_name)
                        continue

                    # Check for model_change events before message normalization
                    mc = parse_model_change(payload, line.strip(), session_id, agent_id)
                    if mc:
                        model_changes.append(mc)
                        continue

                    msg = normalize_transcript_turn(
                        payload, line.strip(), session_id, agent_id, turn_index
                    )
                    if msg:
                        messages.append((msg, last_user_text))
                        if msg.role == "user" and msg.text_content:
                            last_user_text = msg.text_content[:500]
                        turn_index += 1

                new_offset = handle.tell()

            # Insert model change events
            if model_changes:
                self._repository.insert_model_change_events(model_changes)

            if messages:
                inserted_ids = self._repository.insert_conversation_messages(
                    [m for m, _ in messages]
                )

                all_thinking = []
                all_tools = []
                tool_results: list[tuple[str, str, int, bool]] = []

                for (msg, user_text), msg_id in zip(messages, inserted_ids):
                    if msg_id is None:
                        continue

                    for tb in extract_thinking_blocks(msg, user_text):
                        tb.message_id = msg_id
                        all_thinking.append(tb)

                    for ti in extract_tool_invocations(msg):
                        ti.message_id = msg_id
                        all_tools.append(ti)

                    if msg.has_tool_result:
                        content = json.loads(msg.content_json)
                        for block in content:
                            if not isinstance(block, dict):
                                continue
                            if block.get("type") not in ("tool_result", "toolResult"):
                                continue
                            # Handle both formats: tool_use_id (standard) and toolCallId (Rune)
                            use_id = (
                                block.get("tool_use_id")
                                or block.get("toolCallId")
                            )
                            result_content = block.get("content", "")
                            if isinstance(result_content, list):
                                result_content = json.dumps(result_content)
                            is_err = block.get("is_error", False)
                            if use_id:
                                tool_results.append(
                                    (use_id, str(result_content)[:10000], msg_id, bool(is_err))
                                )

                if all_thinking:
                    self._repository.insert_thinking_blocks(all_thinking)
                if all_tools:
                    self._repository.insert_tool_invocations(all_tools)

                # Match tool results after invocations are inserted
                for use_id, result, result_msg_id, is_err in tool_results:
                    self._repository.update_tool_result(use_id, result, result_msg_id, is_err)

                inserted_total += sum(1 for i in inserted_ids if i is not None)

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

            source_key = f"transcript_ingest:{self._remote_ssh_host}:{source_path}"
            offset = self._repository.get_checkpoint(source_key)
            if offset > file_size:
                offset = 0
            if file_size <= offset:
                continue

            content = self._remote_read_from_offset(path=source_path, offset=offset)
            if content is None:
                continue

            session_id = Path(source_path).stem
            agent_id = None
            parts = Path(source_path).parts
            try:
                sessions_idx = parts.index("sessions")
                if sessions_idx >= 2 and parts[sessions_idx - 2] == "agents":
                    agent_id = parts[sessions_idx - 1]
            except ValueError:
                pass

            existing_count = self._repository.get_message_count_for_session(session_id)
            lines = [line for line in content.splitlines() if line.strip()]

            messages: list[tuple[ConversationMessage, str | None]] = []
            model_changes = []
            turn_index = existing_count
            last_user_text: str | None = None

            for line in lines:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("Skipping invalid JSON in remote transcript %s", source_path)
                    continue

                mc = parse_model_change(payload, line.strip(), session_id, agent_id)
                if mc:
                    model_changes.append(mc)
                    continue

                msg = normalize_transcript_turn(
                    payload, line.strip(), session_id, agent_id, turn_index
                )
                if msg:
                    messages.append((msg, last_user_text))
                    if msg.role == "user" and msg.text_content:
                        last_user_text = msg.text_content[:500]
                    turn_index += 1

            if model_changes:
                self._repository.insert_model_change_events(model_changes)

            if messages:
                inserted_ids = self._repository.insert_conversation_messages(
                    [m for m, _ in messages]
                )

                all_thinking = []
                all_tools = []
                tool_results: list[tuple[str, str, int, bool]] = []

                for (msg, user_text), msg_id in zip(messages, inserted_ids):
                    if msg_id is None:
                        continue

                    for tb in extract_thinking_blocks(msg, user_text):
                        tb.message_id = msg_id
                        all_thinking.append(tb)

                    for ti in extract_tool_invocations(msg):
                        ti.message_id = msg_id
                        all_tools.append(ti)

                    if msg.has_tool_result:
                        content_blocks = json.loads(msg.content_json)
                        for block in content_blocks:
                            if not isinstance(block, dict):
                                continue
                            if block.get("type") not in ("tool_result", "toolResult"):
                                continue
                            use_id = block.get("tool_use_id") or block.get("toolCallId")
                            result_content = block.get("content", "")
                            if isinstance(result_content, list):
                                result_content = json.dumps(result_content)
                            is_err = block.get("is_error", False)
                            if use_id:
                                tool_results.append(
                                    (use_id, str(result_content)[:10000], msg_id, bool(is_err))
                                )

                if all_thinking:
                    self._repository.insert_thinking_blocks(all_thinking)
                if all_tools:
                    self._repository.insert_tool_invocations(all_tools)

                for use_id, result, result_msg_id, is_err in tool_results:
                    self._repository.update_tool_result(use_id, result, result_msg_id, is_err)

                inserted_total += sum(1 for message_id in inserted_ids if message_id is not None)

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
    rows.append({"path": path, "size": int(stat.st_size)})
print(json.dumps(rows))
""".replace("__PATTERN__", json.dumps(self._remote_transcript_glob))

        output = self._run_remote_python(script)
        if not output:
            return []

        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            logger.warning("Failed to parse remote transcript ingest listing output")
            return []

        if not isinstance(payload, list):
            return []

        rows: list[dict] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            rows.append(
                {
                    "path": row.get("path"),
                    "size": int(row.get("size") or 0),
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
                logger.warning("Remote transcript ingest command failed: %s", stderr)
            return None
        return result.stdout


class TranscriptIngestLoop:
    def __init__(self, ingestor: TranscriptIngestor, poll_seconds: float) -> None:
        self._ingestor = ingestor
        self._poll_seconds = poll_seconds
        self._running = False

    def run_forever(self) -> None:
        self._running = True
        logger.info("Starting transcript ingest loop")
        while self._running:
            try:
                inserted = self._ingestor.poll_once()
                if inserted:
                    logger.info("Ingested %s transcript messages", inserted)
            except Exception as exc:
                logger.exception("Transcript ingest cycle failed: %s", exc)
            time.sleep(self._poll_seconds)

    def stop(self) -> None:
        self._running = False
