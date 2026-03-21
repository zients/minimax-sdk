"""Type definitions for the Text resource (Anthropic Messages format)."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


# ── Content block types (used in both non-streaming and streaming) ───────────


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


# ── Streaming delta types ───────────────────────────────────────────────────


class TextDelta(BaseModel):
    """Incremental text content."""

    type: Literal["text_delta"] = "text_delta"
    text: str


class InputJsonDelta(BaseModel):
    """Incremental tool input JSON fragment (must be accumulated)."""

    type: Literal["input_json_delta"] = "input_json_delta"
    partial_json: str


class ThinkingDelta(BaseModel):
    """Incremental thinking/reasoning text."""

    type: Literal["thinking_delta"] = "thinking_delta"
    thinking: str


class SignatureDelta(BaseModel):
    """Thinking block signature (sent at the end of a thinking block)."""

    type: Literal["signature_delta"] = "signature_delta"
    signature: str


Delta = Annotated[
    Union[TextDelta, InputJsonDelta, ThinkingDelta, SignatureDelta],
    Field(discriminator="type"),
]


class MessageDelta(BaseModel):
    """Message-level updates (stop reason, delivered at end of stream)."""

    stop_reason: str | None = None
    stop_sequence: str | None = None


# ── Streaming event types ───────────────────────────────────────────────────


class MessageStartEvent(BaseModel):
    """First event in a stream — contains the Message shell with empty content."""

    type: Literal["message_start"] = "message_start"
    message: Message


class ContentBlockStartEvent(BaseModel):
    """Signals the start of a new content block."""

    type: Literal["content_block_start"] = "content_block_start"
    index: int
    content_block: ContentBlock


class ContentBlockDeltaEvent(BaseModel):
    """Incremental update to a content block."""

    type: Literal["content_block_delta"] = "content_block_delta"
    index: int
    delta: Delta


class ContentBlockStopEvent(BaseModel):
    """Signals the end of a content block."""

    type: Literal["content_block_stop"] = "content_block_stop"
    index: int


class MessageDeltaEvent(BaseModel):
    """Message-level changes (stop_reason, usage) at end of stream."""

    type: Literal["message_delta"] = "message_delta"
    delta: MessageDelta
    usage: Usage


class MessageStopEvent(BaseModel):
    """Final event — stream is complete."""

    type: Literal["message_stop"] = "message_stop"


StreamEvent = Annotated[
    Union[
        MessageStartEvent,
        ContentBlockStartEvent,
        ContentBlockDeltaEvent,
        ContentBlockStopEvent,
        MessageDeltaEvent,
        MessageStopEvent,
    ],
    Field(discriminator="type"),
]
