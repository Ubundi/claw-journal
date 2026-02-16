from __future__ import annotations

import json
import logging
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
    def __init__(self, repository: UsageRepository, transcript_glob: str) -> None:
        self._repository = repository
        self._transcript_glob = transcript_glob

    def poll_once(self) -> int:
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
