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
    line_type = payload.get("type")

    # Rune format: messages are wrapped in {"type": "message", "message": {...}}
    if line_type == "message":
        msg_obj = payload.get("message")
        if not isinstance(msg_obj, dict):
            return None
        role = msg_obj.get("role")
        content = msg_obj.get("content", [])
        model = payload.get("model") or msg_obj.get("model")
        message_ts = _parse_ts(payload)

        # Rune uses "toolResult" as a role for tool results
        if role == "toolResult":
            tool_call_id = msg_obj.get("toolCallId")
            tool_name = msg_obj.get("toolName", "")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            # Normalize to standard format for storage
            normalized_content = [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "tool_name": tool_name,
                    "content": content,
                }
            ]
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            return ConversationMessage(
                session_id=session_id,
                agent_id=agent_id,
                turn_index=turn_index,
                role="user",
                message_ts=message_ts,
                model=model,
                text_content="\n".join(text_parts).strip() or None,
                has_thinking=False,
                has_tool_use=False,
                has_tool_result=True,
                content_json=json.dumps(normalized_content),
                raw_json=raw_json,
                event_fingerprint=hashlib.sha256(raw_json.encode("utf-8")).hexdigest(),
            )

        if role not in ("user", "assistant"):
            return None

    # Fallback: direct format (role/content at top level)
    elif payload.get("role") in ("user", "assistant"):
        role = payload["role"]
        content = payload.get("content", [])
        model = payload.get("model")
        message_ts = _parse_ts(payload)
    else:
        # Skip non-message lines (session, model_change, thinking_level_change, custom, etc.)
        return None

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
        elif block_type in ("tool_use", "toolCall"):
            has_tool_use = True
        elif block_type in ("tool_result", "toolResult"):
            has_tool_result = True

    text_content = "\n".join(text_parts).strip() or None
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
        block_type = block.get("type", "")
        if block_type == "tool_use":
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
        elif block_type == "toolCall":
            # Rune format: toolCall with toolCallId and toolName
            invocations.append(
                ToolInvocation(
                    session_id=msg.session_id,
                    agent_id=msg.agent_id,
                    message_id=None,
                    tool_use_id=block.get("toolCallId") or block.get("id"),
                    tool_name=block.get("toolName") or block.get("name", "unknown"),
                    tool_input=json.dumps(block.get("input")) if block.get("input") else None,
                    tool_result=None,
                    result_message_id=None,
                    invocation_ts=msg.message_ts,
                    is_error=False,
                )
            )

    return invocations
