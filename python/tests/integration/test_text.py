"""Integration tests for MiniMax SDK -- Text module.

Tests text generation via MiniMax's Anthropic-compatible endpoint.

Run with: cd python && uv run pytest tests/integration/test_text.py -v
"""

import pytest

from minimax_sdk import MiniMax, Message, TextBlock


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
            max_tokens=32,
        )

        assert isinstance(result, Message)
        assert result.id
        assert result.model
        assert result.stop_reason in ("end_turn", "max_tokens")
        assert len(result.content) >= 1
        assert isinstance(result.content[0], TextBlock)
        assert len(result.content[0].text) > 0
        assert result.usage.input_tokens > 0
        assert result.usage.output_tokens > 0

    def test_create_with_system(self, client: MiniMax):
        """Text generation with system prompt."""
        result = client.text.create(
            model="MiniMax-M2.5",
            messages=[{"role": "user", "content": "What is 2+2?"}],
            max_tokens=32,
            system="You are a math tutor. Answer concisely.",
        )

        assert isinstance(result, Message)
        assert len(result.content) >= 1
        text = result.content[0].text
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
            max_tokens=32,
        )

        assert isinstance(result, Message)
        text = result.content[0].text.lower()
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
