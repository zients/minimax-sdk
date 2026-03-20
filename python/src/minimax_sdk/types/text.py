"""Type definitions for the Text resource (Anthropic Messages format)."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    """A text content block in the response."""

    type: Literal["text"] = "text"
    text: str


class ToolUseBlock(BaseModel):
    """A tool use content block in the response."""

    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any]


class ThinkingBlock(BaseModel):
    """A thinking/reasoning content block in the response."""

    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: str


ContentBlock = Annotated[
    Union[TextBlock, ToolUseBlock, ThinkingBlock],
    Field(discriminator="type"),
]


class Usage(BaseModel):
    """Token usage statistics."""

    input_tokens: int = 0
    output_tokens: int = 0


class Message(BaseModel):
    """A complete message response from the text generation API."""

    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    content: list[ContentBlock]
    model: str
    stop_reason: str | None = None
    stop_sequence: str | None = None
    usage: Usage
