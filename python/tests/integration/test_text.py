"""Integration tests for MiniMax SDK -- Text module.

Tests text generation via MiniMax's Anthropic-compatible endpoint.

Run with: cd python && uv run pytest tests/integration/test_text.py -v
"""

import pytest

from minimax_sdk import MiniMax, Message, TextBlock


def _extract_text(result: Message) -> str:
    """Extract concatenated text from all TextBlocks in a Message.

    MiniMax models may return ThinkingBlocks before TextBlocks,
    so we search through the content array rather than assuming index 0.
    """
    parts = [block.text for block in result.content if isinstance(block, TextBlock)]
    return "".join(parts)


@pytest.fixture(scope="module")
def client() -> MiniMax:
    return MiniMax()


class TestTextCreate:
    """Basic text generation tests."""

    def test_create_simple(self, client: MiniMax):
        """Simple single-turn text generation."""
        result = client.text.create(
            model="MiniMax-M2.5",
            messages=[{"role": "user", "content": "Say hello in one word."}],
            max_tokens=256,
        )

        assert isinstance(result, Message)
        assert result.id
        assert result.model
        assert result.stop_reason in ("end_turn", "max_tokens")
        assert len(result.content) >= 1
        text = _extract_text(result)
        assert len(text) > 0
        assert result.usage.input_tokens > 0
        assert result.usage.output_tokens > 0

    def test_create_with_system(self, client: MiniMax):
        """Text generation with system prompt."""
        result = client.text.create(
            model="MiniMax-M2.5",
            messages=[{"role": "user", "content": "What is 2+2? Reply with only the number."}],
            max_tokens=256,
            system="You are a math tutor. Answer concisely with just the number.",
        )

        assert isinstance(result, Message)
        text = _extract_text(result)
        assert "4" in text

    def test_create_multi_turn(self, client: MiniMax):
        """Multi-turn conversation."""
        result = client.text.create(
            model="MiniMax-M2.5",
            messages=[
                {"role": "user", "content": "My name is Alice."},
                {"role": "assistant", "content": "Hello Alice!"},
                {"role": "user", "content": "What is my name?"},
            ],
            max_tokens=256,
        )

        assert isinstance(result, Message)
        text = _extract_text(result).lower()
        assert "alice" in text

    def test_create_with_temperature(self, client: MiniMax):
        """Text generation with temperature parameter."""
        result = client.text.create(
            model="MiniMax-M2.5",
            messages=[{"role": "user", "content": "Say yes."}],
            max_tokens=8,
            temperature=0.1,
        )

        assert isinstance(result, Message)
        assert result.stop_reason in ("end_turn", "max_tokens")


class TestTextCreateStream:
    """Streaming text generation tests."""

    def test_create_stream_basic(self, client: MiniMax):
        """Streaming yields events and collects text."""
        collected = ""
        event_types = set()

        for event in client.text.create_stream(
            model="MiniMax-M2.5",
            messages=[{"role": "user", "content": "Say hi in one word."}],
            max_tokens=256,
        ):
            event_types.add(event.type)
            if event.type == "content_block_delta" and event.delta.type == "text_delta":
                collected += event.delta.text

        assert len(collected) > 0
        assert "message_start" in event_types
        assert "message_stop" in event_types
        assert "content_block_delta" in event_types

    def test_create_stream_with_system(self, client: MiniMax):
        """Streaming with system prompt."""
        collected = ""
        for event in client.text.create_stream(
            model="MiniMax-M2.5",
            messages=[{"role": "user", "content": "What is 1+1? Reply with only the number."}],
            max_tokens=256,
            system="Answer with just the number.",
        ):
            if event.type == "content_block_delta" and event.delta.type == "text_delta":
                collected += event.delta.text

        assert "2" in collected
