"""Tests for the Text resource and text types."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from minimax_sdk.resources.text import AsyncText, Text, _build_messages_body, _parse_message
from minimax_sdk.types.text import (
    Message,
    TextBlock,
    ThinkingBlock,
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
