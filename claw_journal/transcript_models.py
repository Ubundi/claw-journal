from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class ConversationMessage:
    session_id: str
    agent_id: str | None
    turn_index: int
    role: str
    message_ts: str | None
    model: str | None
    text_content: str | None
    has_thinking: bool
    has_tool_use: bool
    has_tool_result: bool
    content_json: str
    raw_json: str
    event_fingerprint: str


@dataclass
class ThinkingBlock:
    session_id: str
    agent_id: str | None
    message_id: int | None
    block_index: int
    thinking_text: str
    thinking_ts: str | None
    model: str | None
    preceding_user_text: str | None


@dataclass
class ToolInvocation:
    session_id: str
    agent_id: str | None
    message_id: int | None
    tool_use_id: str | None
    tool_name: str
    tool_input: str | None
    tool_result: str | None
    result_message_id: int | None
    invocation_ts: str | None
    is_error: bool


def _parse_ts(payload: dict[str, Any]) -> str | None:
    ts_raw = payload.get("timestamp") or payload.get("time") or payload.get("ts")
    if not ts_raw:
        return None
    try:
        dt = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        return dt.isoformat()
    except ValueError:
        return None


def normalize_transcript_turn(
    payload: dict[str, Any],
    raw_json: str,
    session_id: str,
    agent_id: str | None,
    turn_index: int,
) -> ConversationMessage | None:
    role = payload.get("role")
    if role not in ("user", "assistant"):
        return None

    content = payload.get("content", [])
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return None

    text_parts: list[str] = []
    has_thinking = False
    has_tool_use = False
    has_tool_result = False

    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type", "")
        if block_type == "text":
            text = block.get("text", "")
            if text:
                text_parts.append(text)
        elif block_type == "thinking":
            has_thinking = True
        elif block_type == "tool_use":
            has_tool_use = True
        elif block_type == "tool_result":
            has_tool_result = True

    text_content = "\n".join(text_parts).strip() or None
    message_ts = _parse_ts(payload)
    model = payload.get("model")

    return ConversationMessage(
        session_id=session_id,
        agent_id=agent_id,
        turn_index=turn_index,
        role=role,
        message_ts=message_ts,
        model=model,
        text_content=text_content,
        has_thinking=has_thinking,
        has_tool_use=has_tool_use,
        has_tool_result=has_tool_result,
        content_json=json.dumps(content),
        raw_json=raw_json,
        event_fingerprint=hashlib.sha256(raw_json.encode("utf-8")).hexdigest(),
    )


def extract_thinking_blocks(
    msg: ConversationMessage,
    preceding_user_text: str | None,
) -> list[ThinkingBlock]:
    if not msg.has_thinking:
        return []

    content = json.loads(msg.content_json)
    blocks: list[ThinkingBlock] = []

    for i, block in enumerate(content):
        if not isinstance(block, dict):
            continue
        if block.get("type") != "thinking":
            continue
        thinking_text = block.get("thinking", "") or block.get("text", "")
        if not thinking_text.strip():
            continue
        blocks.append(
            ThinkingBlock(
                session_id=msg.session_id,
                agent_id=msg.agent_id,
                message_id=None,
                block_index=i,
                thinking_text=thinking_text,
                thinking_ts=msg.message_ts,
                model=msg.model,
                preceding_user_text=preceding_user_text,
            )
        )

    return blocks


def extract_tool_invocations(msg: ConversationMessage) -> list[ToolInvocation]:
    if not msg.has_tool_use:
        return []

    content = json.loads(msg.content_json)
    invocations: list[ToolInvocation] = []

    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_use":
            continue
        invocations.append(
            ToolInvocation(
                session_id=msg.session_id,
                agent_id=msg.agent_id,
                message_id=None,
                tool_use_id=block.get("id"),
                tool_name=block.get("name", "unknown"),
                tool_input=json.dumps(block.get("input")) if block.get("input") else None,
                tool_result=None,
                result_message_id=None,
                invocation_ts=msg.message_ts,
                is_error=False,
            )
        )

    return invocations
