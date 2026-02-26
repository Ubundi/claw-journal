"""Tests for claw_journal.transcript_models — log parsing & extraction."""

import json

import pytest

from claw_journal.transcript_models import (
    ConversationMessage,
    ModelChangeEvent,
    ThinkingBlock,
    ToolInvocation,
    _parse_ts,
    extract_thinking_blocks,
    extract_tool_invocations,
    normalize_transcript_turn,
    parse_model_change,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SID = "test-session-001"
AID = "agent-a"


def _turn(payload: dict, *, turn_index: int = 0) -> ConversationMessage | None:
    raw = json.dumps(payload)
    return normalize_transcript_turn(payload, raw, SID, AID, turn_index)


# ===================================================================
# _parse_ts
# ===================================================================


class TestParseTs:
    def test_iso_with_z_suffix(self):
        result = _parse_ts({"timestamp": "2025-01-15T10:30:00Z"})
        assert result is not None
        assert "2025-01-15" in result

    def test_iso_with_offset(self):
        result = _parse_ts({"timestamp": "2025-01-15T10:30:00+00:00"})
        assert result is not None
        assert "2025-01-15" in result

    def test_time_field(self):
        result = _parse_ts({"time": "2025-01-15T10:30:00Z"})
        assert result is not None

    def test_ts_field(self):
        result = _parse_ts({"ts": "2025-01-15T10:30:00Z"})
        assert result is not None

    def test_missing_fields(self):
        assert _parse_ts({}) is None
        assert _parse_ts({"foo": "bar"}) is None

    def test_invalid_string(self):
        assert _parse_ts({"timestamp": "not-a-date"}) is None


# ===================================================================
# normalize_transcript_turn — Direct format
# ===================================================================


class TestDirectFormat:
    def test_user_message_with_text(self):
        payload = {
            "role": "user",
            "content": [{"type": "text", "text": "Hello, Rune!"}],
            "timestamp": "2025-01-15T10:00:00Z",
        }
        msg = _turn(payload)
        assert msg is not None
        assert msg.role == "user"
        assert msg.text_content == "Hello, Rune!"
        assert msg.has_thinking is False
        assert msg.has_tool_use is False
        assert msg.has_tool_result is False
        assert msg.session_id == SID
        assert msg.agent_id == AID

    def test_assistant_with_thinking_and_tool_use(self):
        payload = {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "Let me read the file..."},
                {"type": "text", "text": "I'll check that for you."},
                {"type": "tool_use", "id": "tu_1", "name": "Read", "input": {"path": "/tmp/f"}},
            ],
            "model": "claude-opus-4-6",
        }
        msg = _turn(payload)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.has_thinking is True
        assert msg.has_tool_use is True
        assert msg.has_tool_result is False
        assert msg.text_content == "I'll check that for you."
        assert msg.model == "claude-opus-4-6"

    def test_string_content_wrapped(self):
        payload = {"role": "user", "content": "Plain string message"}
        msg = _turn(payload)
        assert msg is not None
        assert msg.text_content == "Plain string message"

    def test_non_message_payload_returns_none(self):
        assert _turn({"type": "session", "id": "s1"}) is None
        assert _turn({"type": "thinking_level_change"}) is None
        assert _turn({}) is None

    def test_tool_result_blocks_detected(self):
        payload = {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "tu_1", "content": [{"type": "text", "text": "OK"}]},
            ],
        }
        msg = _turn(payload)
        assert msg is not None
        assert msg.has_tool_result is True

    def test_turn_index_preserved(self):
        payload = {"role": "user", "content": "Hi"}
        msg = _turn(payload, turn_index=42)
        assert msg is not None
        assert msg.turn_index == 42

    def test_event_fingerprint_is_sha256(self):
        payload = {"role": "user", "content": "Hello"}
        msg = _turn(payload)
        assert msg is not None
        assert len(msg.event_fingerprint) == 64  # SHA-256 hex digest


# ===================================================================
# normalize_transcript_turn — Rune envelope format
# ===================================================================


class TestRuneEnvelopeFormat:
    def test_rune_user_message(self):
        payload = {
            "type": "message",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "What time is it?"}],
            },
            "timestamp": "2025-01-15T11:00:00Z",
        }
        msg = _turn(payload)
        assert msg is not None
        assert msg.role == "user"
        assert msg.text_content == "What time is it?"

    def test_rune_assistant_message(self):
        payload = {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "It's 11 AM."}],
            },
            "model": "claude-sonnet-4-5-20250929",
        }
        msg = _turn(payload)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.model == "claude-sonnet-4-5-20250929"

    def test_rune_tool_result(self):
        payload = {
            "type": "message",
            "message": {
                "role": "toolResult",
                "toolCallId": "tc_123",
                "toolName": "Bash",
                "content": [{"type": "text", "text": "exit code 0"}],
            },
            "timestamp": "2025-01-15T11:01:00Z",
        }
        msg = _turn(payload)
        assert msg is not None
        assert msg.role == "user"  # toolResult normalized to user role
        assert msg.has_tool_result is True
        assert msg.text_content == "exit code 0"
        # content_json should contain normalized tool_result block
        content = json.loads(msg.content_json)
        assert content[0]["type"] == "tool_result"
        assert content[0]["tool_use_id"] == "tc_123"
        assert content[0]["tool_name"] == "Bash"

    def test_rune_tool_result_string_content(self):
        payload = {
            "type": "message",
            "message": {
                "role": "toolResult",
                "toolCallId": "tc_456",
                "toolName": "Read",
                "content": "file contents here",
            },
        }
        msg = _turn(payload)
        assert msg is not None
        assert msg.has_tool_result is True
        assert msg.text_content == "file contents here"

    def test_rune_invalid_message_object(self):
        assert _turn({"type": "message", "message": "not a dict"}) is None
        assert _turn({"type": "message"}) is None

    def test_rune_unknown_role_returns_none(self):
        payload = {
            "type": "message",
            "message": {"role": "system", "content": [{"type": "text", "text": "hi"}]},
        }
        assert _turn(payload) is None


# ===================================================================
# parse_model_change
# ===================================================================


class TestParseModelChange:
    def test_valid_model_change(self):
        payload = {
            "type": "model_change",
            "id": "mc_1",
            "provider": "anthropic",
            "modelId": "claude-opus-4-6",
            "timestamp": "2025-01-15T12:00:00Z",
        }
        raw = json.dumps(payload)
        result = parse_model_change(payload, raw, SID, AID)
        assert result is not None
        assert isinstance(result, ModelChangeEvent)
        assert result.provider == "anthropic"
        assert result.model_id == "claude-opus-4-6"
        assert result.session_id == SID

    def test_non_model_change_returns_none(self):
        payload = {"type": "message", "role": "user"}
        assert parse_model_change(payload, json.dumps(payload), SID, AID) is None

    def test_missing_type_returns_none(self):
        payload = {"provider": "anthropic"}
        assert parse_model_change(payload, json.dumps(payload), SID, AID) is None


# ===================================================================
# extract_thinking_blocks
# ===================================================================


class TestExtractThinkingBlocks:
    def test_single_thinking_with_following_tool(self):
        content = [
            {"type": "thinking", "thinking": "I should read the file first."},
            {"type": "tool_use", "id": "tu_1", "name": "Read", "input": {}},
        ]
        msg = ConversationMessage(
            session_id=SID, agent_id=AID, turn_index=0, role="assistant",
            message_ts=None, model="claude-opus-4-6",
            text_content=None, has_thinking=True, has_tool_use=True,
            has_tool_result=False, content_json=json.dumps(content),
            raw_json="{}", event_fingerprint="abc",
        )
        blocks = extract_thinking_blocks(msg, "What's in the file?")
        assert len(blocks) == 1
        assert blocks[0].thinking_text == "I should read the file first."
        assert blocks[0].preceding_user_text == "What's in the file?"
        tools = json.loads(blocks[0].following_tool_names)
        assert tools == ["Read"]

    def test_two_thinking_blocks(self):
        content = [
            {"type": "thinking", "thinking": "First thought."},
            {"type": "tool_use", "id": "tu_1", "name": "Read", "input": {}},
            {"type": "thinking", "thinking": "Second thought."},
            {"type": "tool_use", "id": "tu_2", "name": "Write", "input": {}},
        ]
        msg = ConversationMessage(
            session_id=SID, agent_id=AID, turn_index=0, role="assistant",
            message_ts=None, model=None, text_content=None,
            has_thinking=True, has_tool_use=True, has_tool_result=False,
            content_json=json.dumps(content), raw_json="{}",
            event_fingerprint="abc",
        )
        blocks = extract_thinking_blocks(msg, None)
        assert len(blocks) == 2
        assert blocks[0].thinking_text == "First thought."
        # First thinking's following tools stops at the next thinking block
        tools_0 = json.loads(blocks[0].following_tool_names)
        assert tools_0 == ["Read"]
        tools_1 = json.loads(blocks[1].following_tool_names)
        assert tools_1 == ["Write"]

    def test_no_thinking_returns_empty(self):
        msg = ConversationMessage(
            session_id=SID, agent_id=AID, turn_index=0, role="assistant",
            message_ts=None, model=None, text_content="Just text",
            has_thinking=False, has_tool_use=False, has_tool_result=False,
            content_json=json.dumps([{"type": "text", "text": "Just text"}]),
            raw_json="{}", event_fingerprint="abc",
        )
        assert extract_thinking_blocks(msg, None) == []

    def test_empty_thinking_text_skipped(self):
        content = [
            {"type": "thinking", "thinking": "   "},
            {"type": "thinking", "thinking": "Real thought."},
        ]
        msg = ConversationMessage(
            session_id=SID, agent_id=AID, turn_index=0, role="assistant",
            message_ts=None, model=None, text_content=None,
            has_thinking=True, has_tool_use=False, has_tool_result=False,
            content_json=json.dumps(content), raw_json="{}",
            event_fingerprint="abc",
        )
        blocks = extract_thinking_blocks(msg, None)
        assert len(blocks) == 1
        assert blocks[0].thinking_text == "Real thought."

    def test_rune_toolcall_format_detected(self):
        content = [
            {"type": "thinking", "thinking": "Planning..."},
            {"type": "toolCall", "toolCallId": "tc_1", "toolName": "Bash"},
        ]
        msg = ConversationMessage(
            session_id=SID, agent_id=AID, turn_index=0, role="assistant",
            message_ts=None, model=None, text_content=None,
            has_thinking=True, has_tool_use=True, has_tool_result=False,
            content_json=json.dumps(content), raw_json="{}",
            event_fingerprint="abc",
        )
        blocks = extract_thinking_blocks(msg, None)
        assert len(blocks) == 1
        tools = json.loads(blocks[0].following_tool_names)
        assert tools == ["Bash"]


# ===================================================================
# extract_tool_invocations
# ===================================================================


class TestExtractToolInvocations:
    def test_standard_tool_use(self):
        content = [
            {"type": "tool_use", "id": "tu_1", "name": "Read", "input": {"path": "/tmp/file"}},
        ]
        msg = ConversationMessage(
            session_id=SID, agent_id=AID, turn_index=0, role="assistant",
            message_ts="2025-01-15T10:00:00+00:00", model=None,
            text_content=None, has_thinking=False, has_tool_use=True,
            has_tool_result=False, content_json=json.dumps(content),
            raw_json="{}", event_fingerprint="abc",
        )
        invocations = extract_tool_invocations(msg)
        assert len(invocations) == 1
        inv = invocations[0]
        assert inv.tool_name == "Read"
        assert inv.tool_use_id == "tu_1"
        assert inv.is_subagent is False
        assert inv.invocation_ts == "2025-01-15T10:00:00+00:00"
        assert json.loads(inv.tool_input) == {"path": "/tmp/file"}

    def test_rune_toolcall_format(self):
        content = [
            {"type": "toolCall", "toolCallId": "tc_99", "toolName": "Bash"},
        ]
        msg = ConversationMessage(
            session_id=SID, agent_id=AID, turn_index=0, role="assistant",
            message_ts=None, model=None, text_content=None,
            has_thinking=False, has_tool_use=True, has_tool_result=False,
            content_json=json.dumps(content), raw_json="{}",
            event_fingerprint="abc",
        )
        invocations = extract_tool_invocations(msg)
        assert len(invocations) == 1
        assert invocations[0].tool_name == "Bash"
        assert invocations[0].tool_use_id == "tc_99"

    def test_subagent_tool_detected(self):
        content = [
            {"type": "tool_use", "id": "tu_2", "name": "Task", "input": {"prompt": "do stuff"}},
        ]
        msg = ConversationMessage(
            session_id=SID, agent_id=AID, turn_index=0, role="assistant",
            message_ts=None, model=None, text_content=None,
            has_thinking=False, has_tool_use=True, has_tool_result=False,
            content_json=json.dumps(content), raw_json="{}",
            event_fingerprint="abc",
        )
        invocations = extract_tool_invocations(msg)
        assert len(invocations) == 1
        assert invocations[0].is_subagent is True

    def test_no_tool_use_returns_empty(self):
        msg = ConversationMessage(
            session_id=SID, agent_id=AID, turn_index=0, role="assistant",
            message_ts=None, model=None, text_content="Just text",
            has_thinking=False, has_tool_use=False, has_tool_result=False,
            content_json=json.dumps([{"type": "text", "text": "Just text"}]),
            raw_json="{}", event_fingerprint="abc",
        )
        assert extract_tool_invocations(msg) == []

    def test_multiple_tools(self):
        content = [
            {"type": "tool_use", "id": "tu_1", "name": "Read", "input": {}},
            {"type": "text", "text": "Then..."},
            {"type": "tool_use", "id": "tu_2", "name": "Write", "input": {}},
        ]
        msg = ConversationMessage(
            session_id=SID, agent_id=AID, turn_index=0, role="assistant",
            message_ts=None, model=None, text_content=None,
            has_thinking=False, has_tool_use=True, has_tool_result=False,
            content_json=json.dumps(content), raw_json="{}",
            event_fingerprint="abc",
        )
        invocations = extract_tool_invocations(msg)
        assert len(invocations) == 2
        assert invocations[0].tool_name == "Read"
        assert invocations[1].tool_name == "Write"
