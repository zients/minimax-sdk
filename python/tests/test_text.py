"""Tests for the Text resource and text types."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from minimax_sdk.exceptions import MiniMaxError
from minimax_sdk.resources.text import (
    AsyncText,
    Text,
    _build_messages_body,
    _parse_message,
    _parse_sse_events,
    _parse_sse_events_async,
)
from minimax_sdk.types.text import (
    ContentBlockDeltaEvent,
    ContentBlockStartEvent,
    ContentBlockStopEvent,
    InputJsonDelta,
    Message,
    MessageDeltaEvent,
    MessageStartEvent,
    MessageStopEvent,
    SignatureDelta,
    TextBlock,
    TextDelta,
    ThinkingBlock,
    ThinkingDelta,
    ToolUseBlock,
    Usage,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


def _anthropic_resp(
    content: list[dict[str, Any]],
    *,
    stop_reason: str = "end_turn",
    model: str = "MiniMax-M2.7",
    input_tokens: int = 10,
    output_tokens: int = 20,
) -> dict[str, Any]:
    """Build a mock Anthropic Messages API response."""
    return {
        "id": "msg_test_001",
        "type": "message",
        "role": "assistant",
        "content": content,
        "model": model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
    }


def _make_text_resource() -> tuple[Text, MagicMock]:
    """Create a Text resource with mocked _http."""
    mock_http = MagicMock()
    mock_client = MagicMock()
    text = Text(mock_http, client=mock_client)
    return text, mock_http


def _make_async_text_resource() -> tuple[AsyncText, AsyncMock]:
    """Create an AsyncText resource with mocked _http."""
    mock_http = AsyncMock()
    mock_client = AsyncMock()
    text = AsyncText(mock_http, client=mock_client)
    return text, mock_http


# ── _build_messages_body tests ──────────────────────────────────────────────


class TestBuildMessagesBody:
    """Test the request body builder."""

    def test_required_params_only(self):
        body = _build_messages_body(
            "MiniMax-M2.7",
            [{"role": "user", "content": "Hello"}],
            1024,
            system=None,
            temperature=None,
            top_p=None,
            tools=None,
            tool_choice=None,
            thinking=None,
            metadata=None,
        )
        assert body == {
            "model": "MiniMax-M2.7",
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 1024,
        }

    def test_all_optional_params(self):
        tools = [{"name": "get_weather", "description": "...", "input_schema": {}}]
        body = _build_messages_body(
            "MiniMax-M2.5",
            [{"role": "user", "content": "Hi"}],
            2048,
            system="You are helpful.",
            temperature=0.7,
            top_p=0.9,
            tools=tools,
            tool_choice={"type": "auto"},
            thinking={"type": "enabled", "budget_tokens": 5000},
            metadata={"user_id": "user123"},
        )
        assert body["model"] == "MiniMax-M2.5"
        assert body["max_tokens"] == 2048
        assert body["system"] == "You are helpful."
        assert body["temperature"] == 0.7
        assert body["top_p"] == 0.9
        assert body["tools"] == tools
        assert body["tool_choice"] == {"type": "auto"}
        assert body["thinking"] == {"type": "enabled", "budget_tokens": 5000}
        assert body["metadata"] == {"user_id": "user123"}

    def test_system_as_list(self):
        body = _build_messages_body(
            "MiniMax-M2.7",
            [{"role": "user", "content": "Hi"}],
            1024,
            system=[{"type": "text", "text": "Be concise."}],
            temperature=None,
            top_p=None,
            tools=None,
            tool_choice=None,
            thinking=None,
            metadata=None,
        )
        assert body["system"] == [{"type": "text", "text": "Be concise."}]

    def test_none_values_excluded(self):
        body = _build_messages_body(
            "MiniMax-M2.7",
            [{"role": "user", "content": "Hi"}],
            1024,
            system=None,
            temperature=None,
            top_p=None,
            tools=None,
            tool_choice=None,
            thinking=None,
            metadata=None,
        )
        assert "system" not in body
        assert "temperature" not in body
        assert "top_p" not in body
        assert "tools" not in body
        assert "tool_choice" not in body
        assert "thinking" not in body
        assert "metadata" not in body


# ── _parse_message tests ────────────────────────────────────────────────────


class TestParseMessage:
    """Test Anthropic response parsing into Message model."""

    def test_parse_text_response(self):
        resp = _anthropic_resp([{"type": "text", "text": "Hello!"}])
        msg = _parse_message(resp)

        assert isinstance(msg, Message)
        assert msg.id == "msg_test_001"
        assert msg.type == "message"
        assert msg.role == "assistant"
        assert msg.model == "MiniMax-M2.7"
        assert msg.stop_reason == "end_turn"
        assert msg.stop_sequence is None
        assert isinstance(msg.usage, Usage)
        assert msg.usage.input_tokens == 10
        assert msg.usage.output_tokens == 20
        assert len(msg.content) == 1
        assert isinstance(msg.content[0], TextBlock)
        assert msg.content[0].text == "Hello!"

    def test_parse_tool_use_response(self):
        resp = _anthropic_resp(
            [
                {"type": "text", "text": "Let me check."},
                {
                    "type": "tool_use",
                    "id": "toolu_01",
                    "name": "get_weather",
                    "input": {"location": "San Francisco"},
                },
            ],
            stop_reason="tool_use",
        )
        msg = _parse_message(resp)

        assert len(msg.content) == 2
        assert isinstance(msg.content[0], TextBlock)
        assert msg.content[0].text == "Let me check."
        assert isinstance(msg.content[1], ToolUseBlock)
        assert msg.content[1].id == "toolu_01"
        assert msg.content[1].name == "get_weather"
        assert msg.content[1].input == {"location": "San Francisco"}
        assert msg.stop_reason == "tool_use"

    def test_parse_thinking_response(self):
        resp = _anthropic_resp(
            [
                {
                    "type": "thinking",
                    "thinking": "Let me reason step by step...",
                    "signature": "sig_abc123",
                },
                {"type": "text", "text": "The answer is 42."},
            ],
        )
        msg = _parse_message(resp)

        assert len(msg.content) == 2
        assert isinstance(msg.content[0], ThinkingBlock)
        assert msg.content[0].thinking == "Let me reason step by step..."
        assert msg.content[0].signature == "sig_abc123"
        assert isinstance(msg.content[1], TextBlock)
        assert msg.content[1].text == "The answer is 42."

    def test_parse_multiple_tool_calls(self):
        resp = _anthropic_resp(
            [
                {"type": "text", "text": "Checking both."},
                {
                    "type": "tool_use",
                    "id": "toolu_01",
                    "name": "get_weather",
                    "input": {"location": "SF"},
                },
                {
                    "type": "tool_use",
                    "id": "toolu_02",
                    "name": "get_weather",
                    "input": {"location": "NYC"},
                },
            ],
            stop_reason="tool_use",
        )
        msg = _parse_message(resp)

        assert len(msg.content) == 3
        assert isinstance(msg.content[1], ToolUseBlock)
        assert isinstance(msg.content[2], ToolUseBlock)
        assert msg.content[1].input["location"] == "SF"
        assert msg.content[2].input["location"] == "NYC"

    def test_parse_max_tokens_stop(self):
        resp = _anthropic_resp(
            [{"type": "text", "text": "Partial response..."}],
            stop_reason="max_tokens",
        )
        msg = _parse_message(resp)
        assert msg.stop_reason == "max_tokens"


# ── Sync Text.create() tests ───────────────────────────────────────────────


class TestTextCreate:
    """Tests for sync Text.create()."""

    def test_create_basic(self):
        text, mock_http = _make_text_resource()
        mock_http.request_anthropic.return_value = _anthropic_resp(
            [{"type": "text", "text": "Hi there!"}]
        )

        result = text.create(
            model="MiniMax-M2.7",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=1024,
        )

        assert isinstance(result, Message)
        assert result.content[0].text == "Hi there!"

        mock_http.request_anthropic.assert_called_once()
        call_args = mock_http.request_anthropic.call_args
        assert call_args[0] == ("POST", "/anthropic/v1/messages")
        body = call_args[1]["json"]
        assert body["model"] == "MiniMax-M2.7"
        assert body["messages"] == [{"role": "user", "content": "Hello"}]
        assert body["max_tokens"] == 1024

    def test_create_with_system(self):
        text, mock_http = _make_text_resource()
        mock_http.request_anthropic.return_value = _anthropic_resp(
            [{"type": "text", "text": "I am helpful."}]
        )

        text.create(
            model="MiniMax-M2.7",
            messages=[{"role": "user", "content": "Who are you?"}],
            max_tokens=1024,
            system="You are a helpful assistant.",
        )

        body = mock_http.request_anthropic.call_args[1]["json"]
        assert body["system"] == "You are a helpful assistant."

    def test_create_with_tools(self):
        text, mock_http = _make_text_resource()
        mock_http.request_anthropic.return_value = _anthropic_resp(
            [
                {
                    "type": "tool_use",
                    "id": "toolu_01",
                    "name": "get_weather",
                    "input": {"location": "Tokyo"},
                }
            ],
            stop_reason="tool_use",
        )

        tools = [
            {
                "name": "get_weather",
                "description": "Get weather",
                "input_schema": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            }
        ]

        result = text.create(
            model="MiniMax-M2.7",
            messages=[{"role": "user", "content": "Weather in Tokyo?"}],
            max_tokens=1024,
            tools=tools,
            tool_choice={"type": "auto"},
        )

        assert result.stop_reason == "tool_use"
        assert isinstance(result.content[0], ToolUseBlock)

        body = mock_http.request_anthropic.call_args[1]["json"]
        assert body["tools"] == tools
        assert body["tool_choice"] == {"type": "auto"}

    def test_create_with_thinking(self):
        text, mock_http = _make_text_resource()
        mock_http.request_anthropic.return_value = _anthropic_resp(
            [
                {
                    "type": "thinking",
                    "thinking": "Step 1...",
                    "signature": "sig_xyz",
                },
                {"type": "text", "text": "Answer."},
            ],
        )

        result = text.create(
            model="MiniMax-M2.7",
            messages=[{"role": "user", "content": "Think about this."}],
            max_tokens=16000,
            thinking={"type": "enabled", "budget_tokens": 10000},
        )

        assert isinstance(result.content[0], ThinkingBlock)
        body = mock_http.request_anthropic.call_args[1]["json"]
        assert body["thinking"] == {"type": "enabled", "budget_tokens": 10000}

    def test_create_with_all_params(self):
        text, mock_http = _make_text_resource()
        mock_http.request_anthropic.return_value = _anthropic_resp(
            [{"type": "text", "text": "OK"}]
        )

        text.create(
            model="MiniMax-M2.5",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=512,
            system="Be brief.",
            temperature=0.5,
            top_p=0.8,
            tools=[{"name": "t", "description": "d", "input_schema": {}}],
            tool_choice={"type": "any"},
            thinking={"type": "enabled", "budget_tokens": 2000},
            metadata={"user_id": "u1"},
        )

        body = mock_http.request_anthropic.call_args[1]["json"]
        assert body["model"] == "MiniMax-M2.5"
        assert body["max_tokens"] == 512
        assert body["system"] == "Be brief."
        assert body["temperature"] == 0.5
        assert body["top_p"] == 0.8
        assert body["metadata"] == {"user_id": "u1"}

    def test_create_multi_turn(self):
        text, mock_http = _make_text_resource()
        mock_http.request_anthropic.return_value = _anthropic_resp(
            [{"type": "text", "text": "I said hello earlier."}]
        )

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "What did you say?"},
        ]

        text.create(
            model="MiniMax-M2.7",
            messages=messages,
            max_tokens=1024,
        )

        body = mock_http.request_anthropic.call_args[1]["json"]
        assert len(body["messages"]) == 3


# ── Async Text.create() tests ──────────────────────────────────────────────


class TestAsyncTextCreate:
    """Tests for async AsyncText.create()."""

    @pytest.mark.asyncio
    async def test_create_basic(self):
        text, mock_http = _make_async_text_resource()
        mock_http.request_anthropic.return_value = _anthropic_resp(
            [{"type": "text", "text": "Async hello!"}]
        )

        result = await text.create(
            model="MiniMax-M2.7",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=1024,
        )

        assert isinstance(result, Message)
        assert result.content[0].text == "Async hello!"

        mock_http.request_anthropic.assert_awaited_once()
        call_args = mock_http.request_anthropic.call_args
        assert call_args[0] == ("POST", "/anthropic/v1/messages")

    @pytest.mark.asyncio
    async def test_create_with_all_params(self):
        text, mock_http = _make_async_text_resource()
        mock_http.request_anthropic.return_value = _anthropic_resp(
            [{"type": "text", "text": "OK"}]
        )

        await text.create(
            model="MiniMax-M2.5",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=512,
            system="Be brief.",
            temperature=0.5,
            top_p=0.8,
            tools=[{"name": "t", "description": "d", "input_schema": {}}],
            tool_choice={"type": "auto"},
            thinking={"type": "enabled", "budget_tokens": 2000},
            metadata={"user_id": "u1"},
        )

        body = mock_http.request_anthropic.call_args[1]["json"]
        assert body["model"] == "MiniMax-M2.5"
        assert body["system"] == "Be brief."
        assert body["temperature"] == 0.5

    @pytest.mark.asyncio
    async def test_create_tool_use(self):
        text, mock_http = _make_async_text_resource()
        mock_http.request_anthropic.return_value = _anthropic_resp(
            [
                {
                    "type": "tool_use",
                    "id": "toolu_async",
                    "name": "search",
                    "input": {"query": "test"},
                }
            ],
            stop_reason="tool_use",
        )

        result = await text.create(
            model="MiniMax-M2.7",
            messages=[{"role": "user", "content": "Search for test"}],
            max_tokens=1024,
            tools=[{"name": "search", "description": "Search", "input_schema": {}}],
        )

        assert result.stop_reason == "tool_use"
        assert isinstance(result.content[0], ToolUseBlock)
        assert result.content[0].name == "search"


# ── SSE parser tests ────────────────────────────────────────────────────────


def _sse_line(event_type: str, data: dict[str, Any]) -> list[str]:
    """Build SSE lines for a single event (event: + data: + blank)."""
    return [f"event: {event_type}", f"data: {json.dumps(data)}", ""]


def _simple_text_stream_lines() -> list[str]:
    """Build a minimal SSE stream: message_start → text block → message_stop."""
    lines: list[str] = []
    lines.extend(_sse_line("message_start", {
        "type": "message_start",
        "message": {
            "id": "msg_stream_001",
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": "MiniMax-M2.7",
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 1},
        },
    }))
    lines.extend(_sse_line("content_block_start", {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "text", "text": ""},
    }))
    lines.extend(_sse_line("content_block_delta", {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "text_delta", "text": "Hello"},
    }))
    lines.extend(_sse_line("content_block_delta", {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "text_delta", "text": " world!"},
    }))
    lines.extend(_sse_line("content_block_stop", {
        "type": "content_block_stop",
        "index": 0,
    }))
    lines.extend(_sse_line("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"output_tokens": 5},
    }))
    lines.extend(_sse_line("message_stop", {"type": "message_stop"}))
    return lines


class TestParseSSEEvents:
    """Tests for the SSE event parser."""

    def test_simple_text_stream(self):
        lines = _simple_text_stream_lines()
        events = list(_parse_sse_events(iter(lines)))

        assert len(events) == 7
        assert isinstance(events[0], MessageStartEvent)
        assert events[0].message.id == "msg_stream_001"
        assert isinstance(events[1], ContentBlockStartEvent)
        assert events[1].index == 0
        assert isinstance(events[1].content_block, TextBlock)
        assert isinstance(events[2], ContentBlockDeltaEvent)
        assert isinstance(events[2].delta, TextDelta)
        assert events[2].delta.text == "Hello"
        assert isinstance(events[3], ContentBlockDeltaEvent)
        assert events[3].delta.text == " world!"
        assert isinstance(events[4], ContentBlockStopEvent)
        assert events[4].index == 0
        assert isinstance(events[5], MessageDeltaEvent)
        assert events[5].delta.stop_reason == "end_turn"
        assert events[5].usage.output_tokens == 5
        assert isinstance(events[6], MessageStopEvent)

    def test_tool_use_stream(self):
        lines: list[str] = []
        lines.extend(_sse_line("message_start", {
            "type": "message_start",
            "message": {
                "id": "msg_tool", "type": "message", "role": "assistant",
                "content": [], "model": "MiniMax-M2.7",
                "stop_reason": None, "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 1},
            },
        }))
        lines.extend(_sse_line("content_block_start", {
            "type": "content_block_start",
            "index": 0,
            "content_block": {
                "type": "tool_use", "id": "toolu_01", "name": "get_weather", "input": {},
            },
        }))
        lines.extend(_sse_line("content_block_delta", {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '{"loc'},
        }))
        lines.extend(_sse_line("content_block_delta", {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": 'ation": "SF"}'},
        }))
        lines.extend(_sse_line("content_block_stop", {
            "type": "content_block_stop", "index": 0,
        }))
        lines.extend(_sse_line("message_delta", {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use"},
            "usage": {"output_tokens": 10},
        }))
        lines.extend(_sse_line("message_stop", {"type": "message_stop"}))

        events = list(_parse_sse_events(iter(lines)))

        assert isinstance(events[1].content_block, ToolUseBlock)
        assert events[1].content_block.name == "get_weather"
        assert isinstance(events[2].delta, InputJsonDelta)
        assert events[2].delta.partial_json == '{"loc'
        assert isinstance(events[3].delta, InputJsonDelta)
        assert events[5].delta.stop_reason == "tool_use"

    def test_thinking_stream(self):
        lines: list[str] = []
        lines.extend(_sse_line("message_start", {
            "type": "message_start",
            "message": {
                "id": "msg_think", "type": "message", "role": "assistant",
                "content": [], "model": "MiniMax-M2.7",
                "stop_reason": None, "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 1},
            },
        }))
        lines.extend(_sse_line("content_block_start", {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "thinking", "thinking": "", "signature": ""},
        }))
        lines.extend(_sse_line("content_block_delta", {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "Step 1..."},
        }))
        lines.extend(_sse_line("content_block_delta", {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "signature_delta", "signature": "sig_abc"},
        }))
        lines.extend(_sse_line("content_block_stop", {
            "type": "content_block_stop", "index": 0,
        }))
        lines.extend(_sse_line("message_delta", {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 20},
        }))
        lines.extend(_sse_line("message_stop", {"type": "message_stop"}))

        events = list(_parse_sse_events(iter(lines)))

        assert isinstance(events[1].content_block, ThinkingBlock)
        assert isinstance(events[2].delta, ThinkingDelta)
        assert events[2].delta.thinking == "Step 1..."
        assert isinstance(events[3].delta, SignatureDelta)
        assert events[3].delta.signature == "sig_abc"

    def test_ping_events_skipped(self):
        lines: list[str] = []
        lines.extend(_sse_line("message_start", {
            "type": "message_start",
            "message": {
                "id": "msg_ping", "type": "message", "role": "assistant",
                "content": [], "model": "MiniMax-M2.7",
                "stop_reason": None, "stop_sequence": None,
                "usage": {"input_tokens": 5, "output_tokens": 1},
            },
        }))
        lines.extend(_sse_line("ping", {"type": "ping"}))
        lines.extend(_sse_line("message_stop", {"type": "message_stop"}))

        events = list(_parse_sse_events(iter(lines)))
        assert len(events) == 2  # ping skipped
        assert isinstance(events[0], MessageStartEvent)
        assert isinstance(events[1], MessageStopEvent)

    def test_error_event_raises(self):
        lines: list[str] = []
        lines.extend(_sse_line("error", {
            "type": "error",
            "error": {"type": "overloaded_error", "message": "Overloaded"},
        }))

        with pytest.raises(MiniMaxError, match="Overloaded"):
            list(_parse_sse_events(iter(lines)))

    def test_unknown_event_skipped(self):
        lines: list[str] = []
        lines.extend(_sse_line("message_start", {
            "type": "message_start",
            "message": {
                "id": "msg_unk", "type": "message", "role": "assistant",
                "content": [], "model": "MiniMax-M2.7",
                "stop_reason": None, "stop_sequence": None,
                "usage": {"input_tokens": 5, "output_tokens": 1},
            },
        }))
        lines.extend(_sse_line("unknown_future_event", {
            "type": "unknown_future_event", "data": "something",
        }))
        lines.extend(_sse_line("message_stop", {"type": "message_stop"}))

        events = list(_parse_sse_events(iter(lines)))
        assert len(events) == 2  # unknown skipped

    def test_trailing_event_without_empty_line(self):
        """Last event without trailing blank line should still be parsed."""
        lines = [
            "event: message_stop",
            f"data: {json.dumps({'type': 'message_stop'})}",
            # No trailing empty line
        ]
        events = list(_parse_sse_events(iter(lines)))
        assert len(events) == 1
        assert isinstance(events[0], MessageStopEvent)

    def test_trailing_error_without_empty_line(self):
        """Error event at end without trailing blank line should raise."""
        lines = [
            "event: error",
            f"data: {json.dumps({'type': 'error', 'error': {'type': 'api_error', 'message': 'Boom'}})}",
        ]
        with pytest.raises(MiniMaxError, match="Boom"):
            list(_parse_sse_events(iter(lines)))

    def test_trailing_unknown_event_skipped(self):
        """Unknown event at end without trailing blank line should be skipped."""
        lines = [
            "event: future_event",
            f"data: {json.dumps({'type': 'future_event', 'x': 1})}",
        ]
        events = list(_parse_sse_events(iter(lines)))
        assert len(events) == 0


# ── Async SSE parser tests ──────────────────────────────────────────────────


class TestParseSSEEventsAsync:
    """Tests for the async SSE event parser."""

    @pytest.mark.asyncio
    async def test_simple_text_stream(self):
        lines = _simple_text_stream_lines()

        async def _async_iter():
            for line in lines:
                yield line

        events = [event async for event in _parse_sse_events_async(_async_iter())]
        assert len(events) == 7
        assert isinstance(events[0], MessageStartEvent)
        assert isinstance(events[2], ContentBlockDeltaEvent)
        assert isinstance(events[2].delta, TextDelta)
        assert events[2].delta.text == "Hello"

    @pytest.mark.asyncio
    async def test_error_event_raises(self):
        lines = _sse_line("error", {
            "type": "error",
            "error": {"type": "api_error", "message": "Internal"},
        })

        async def _async_iter():
            for line in lines:
                yield line

        with pytest.raises(MiniMaxError, match="Internal"):
            async for _ in _parse_sse_events_async(_async_iter()):
                pass

    @pytest.mark.asyncio
    async def test_ping_skipped(self):
        lines = _sse_line("ping", {"type": "ping"}) + _sse_line(
            "message_stop", {"type": "message_stop"}
        )

        async def _async_iter():
            for line in lines:
                yield line

        events = [event async for event in _parse_sse_events_async(_async_iter())]
        assert len(events) == 1
        assert isinstance(events[0], MessageStopEvent)

    @pytest.mark.asyncio
    async def test_unknown_event_mid_stream_skipped(self):
        """Unknown event between valid events should be skipped (lines 155-156)."""
        lines = (
            _sse_line("message_start", {
                "type": "message_start",
                "message": {
                    "id": "msg_unk2", "type": "message", "role": "assistant",
                    "content": [], "model": "MiniMax-M2.7",
                    "stop_reason": None, "stop_sequence": None,
                    "usage": {"input_tokens": 5, "output_tokens": 1},
                },
            })
            + _sse_line("unknown_future_event", {
                "type": "unknown_future_event", "data": "something",
            })
            + _sse_line("message_stop", {"type": "message_stop"})
        )

        async def _async_iter():
            for line in lines:
                yield line

        events = [event async for event in _parse_sse_events_async(_async_iter())]
        assert len(events) == 2  # unknown skipped
        assert isinstance(events[0], MessageStartEvent)
        assert isinstance(events[1], MessageStopEvent)

    @pytest.mark.asyncio
    async def test_trailing_error_raises(self):
        lines = [
            "event: error",
            f"data: {json.dumps({'type': 'error', 'error': {'message': 'Fail'}})}",
        ]

        async def _async_iter():
            for line in lines:
                yield line

        with pytest.raises(MiniMaxError, match="Fail"):
            async for _ in _parse_sse_events_async(_async_iter()):
                pass

    @pytest.mark.asyncio
    async def test_trailing_unknown_skipped(self):
        lines = [
            "event: x",
            f"data: {json.dumps({'type': 'x'})}",
        ]

        async def _async_iter():
            for line in lines:
                yield line

        events = [event async for event in _parse_sse_events_async(_async_iter())]
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_trailing_event_without_empty_line(self):
        lines = [
            "event: message_stop",
            f"data: {json.dumps({'type': 'message_stop'})}",
        ]

        async def _async_iter():
            for line in lines:
                yield line

        events = [event async for event in _parse_sse_events_async(_async_iter())]
        assert len(events) == 1
        assert isinstance(events[0], MessageStopEvent)


# ── Text.create_stream() tests ──────────────────────────────────────────────


class TestTextCreateStream:
    """Tests for sync Text.create_stream()."""

    def test_create_stream_basic(self):
        text, mock_http = _make_text_resource()
        mock_http.stream_request_anthropic.return_value = iter(
            _simple_text_stream_lines()
        )

        events = list(text.create_stream(
            model="MiniMax-M2.7",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=1024,
        ))

        assert len(events) == 7
        assert isinstance(events[0], MessageStartEvent)

        # Verify stream=True was set
        call_args = mock_http.stream_request_anthropic.call_args
        assert call_args[0] == ("POST", "/anthropic/v1/messages")
        body = call_args[1]["json"]
        assert body["stream"] is True
        assert body["model"] == "MiniMax-M2.7"

    def test_create_stream_collects_text(self):
        text, mock_http = _make_text_resource()
        mock_http.stream_request_anthropic.return_value = iter(
            _simple_text_stream_lines()
        )

        collected = ""
        for event in text.create_stream(
            model="MiniMax-M2.7",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=1024,
        ):
            if event.type == "content_block_delta" and event.delta.type == "text_delta":
                collected += event.delta.text

        assert collected == "Hello world!"

    def test_create_stream_with_all_params(self):
        text, mock_http = _make_text_resource()
        mock_http.stream_request_anthropic.return_value = iter(
            _simple_text_stream_lines()
        )

        list(text.create_stream(
            model="MiniMax-M2.5",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=512,
            system="Be brief.",
            temperature=0.5,
            top_p=0.8,
            tools=[{"name": "t", "description": "d", "input_schema": {}}],
            tool_choice={"type": "auto"},
            thinking={"type": "enabled", "budget_tokens": 2000},
            metadata={"user_id": "u1"},
        ))

        body = mock_http.stream_request_anthropic.call_args[1]["json"]
        assert body["stream"] is True
        assert body["system"] == "Be brief."
        assert body["temperature"] == 0.5


# ── AsyncText.create_stream() tests ─────────────────────────────────────────


class TestAsyncTextCreateStream:
    """Tests for async AsyncText.create_stream()."""

    @pytest.mark.asyncio
    async def test_create_stream_basic(self):
        text, mock_http = _make_async_text_resource()
        lines = _simple_text_stream_lines()

        async def _async_iter():
            for line in lines:
                yield line

        # Async generator returns AsyncIterator directly (no await), so use MagicMock
        mock_http.stream_request_anthropic = MagicMock(return_value=_async_iter())

        events = [event async for event in text.create_stream(
            model="MiniMax-M2.7",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=1024,
        )]

        assert len(events) == 7
        assert isinstance(events[0], MessageStartEvent)

        call_args = mock_http.stream_request_anthropic.call_args
        body = call_args[1]["json"]
        assert body["stream"] is True

    @pytest.mark.asyncio
    async def test_create_stream_collects_text(self):
        text, mock_http = _make_async_text_resource()
        lines = _simple_text_stream_lines()

        async def _async_iter():
            for line in lines:
                yield line

        mock_http.stream_request_anthropic = MagicMock(return_value=_async_iter())

        collected = ""
        async for event in text.create_stream(
            model="MiniMax-M2.7",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=1024,
        ):
            if event.type == "content_block_delta" and event.delta.type == "text_delta":
                collected += event.delta.text

        assert collected == "Hello world!"
