"""Text resource -- synchronous and asynchronous text generation.

Provides both synchronous (:class:`Text`) and asynchronous (:class:`AsyncText`)
clients for text generation via MiniMax's Anthropic-compatible endpoint
(``POST /anthropic/v1/messages``).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Iterator
from typing import Any

from pydantic import TypeAdapter

from .._base import AsyncResource, SyncResource
from ..exceptions import MiniMaxError
from ..types.text import Message, StreamEvent

logger = logging.getLogger("minimax_sdk")

_MESSAGES_PATH = "/anthropic/v1/messages"

_stream_event_adapter: TypeAdapter[StreamEvent] = TypeAdapter(StreamEvent)


def _build_messages_body(
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    *,
    system: str | list[dict[str, Any]] | None,
    temperature: float | None,
    top_p: float | None,
    tools: list[dict[str, Any]] | None,
    tool_choice: dict[str, Any] | None,
    thinking: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the JSON request body for the Anthropic Messages endpoint."""
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }

    if system is not None:
        body["system"] = system
    if temperature is not None:
        body["temperature"] = temperature
    if top_p is not None:
        body["top_p"] = top_p
    if tools is not None:
        body["tools"] = tools
    if tool_choice is not None:
        body["tool_choice"] = tool_choice
    if thinking is not None:
        body["thinking"] = thinking
    if metadata is not None:
        body["metadata"] = metadata

    return body


def _parse_message(resp: dict[str, Any]) -> Message:
    """Parse an Anthropic Messages API response into a :class:`Message`."""
    return Message.model_validate(resp)


def _parse_sse_events(lines: Iterator[str]) -> Iterator[StreamEvent]:
    """Parse Anthropic SSE lines into typed :class:`StreamEvent` objects.

    SSE format::

        event: message_start
        data: {"type": "message_start", ...}
                                            ← empty line = event boundary

    The ``event:`` line is ignored because the ``type`` field inside the
    JSON ``data:`` payload already identifies the event.  ``ping`` events
    and unknown event types are silently skipped.
    """
    data_buf = ""

    for line in lines:
        if line.startswith("data: "):
            data_buf = data_buf + "\n" + line[6:] if data_buf else line[6:]
        elif line == "":
            if data_buf:
                payload = json.loads(data_buf)
                data_buf = ""
                event_type = payload.get("type", "")

                if event_type == "ping":
                    continue
                if event_type == "error":
                    error = payload.get("error", {})
                    raise MiniMaxError(
                        error.get("message", "Stream error"),
                        code=0,
                        trace_id="",
                    )

                try:
                    yield _stream_event_adapter.validate_python(payload)
                except Exception:
                    logger.debug("Skipping unknown stream event: %s", event_type)

    # Handle trailing event without final empty line
    if data_buf:
        payload = json.loads(data_buf)
        event_type = payload.get("type", "")
        if event_type == "error":
            error = payload.get("error", {})
            raise MiniMaxError(
                error.get("message", "Stream error"),
                code=0,
                trace_id="",
            )
        if event_type != "ping":
            try:
                yield _stream_event_adapter.validate_python(payload)
            except Exception:
                logger.debug("Skipping unknown stream event: %s", event_type)


async def _parse_sse_events_async(
    lines: AsyncIterator[str],
) -> AsyncIterator[StreamEvent]:
    """Async version of :func:`_parse_sse_events`."""
    data_buf = ""

    async for line in lines:
        if line.startswith("data: "):
            data_buf = data_buf + "\n" + line[6:] if data_buf else line[6:]
        elif line == "":
            if data_buf:
                payload = json.loads(data_buf)
                data_buf = ""
                event_type = payload.get("type", "")

                if event_type == "ping":
                    continue
                if event_type == "error":
                    error = payload.get("error", {})
                    raise MiniMaxError(
                        error.get("message", "Stream error"),
                        code=0,
                        trace_id="",
                    )

                try:
                    yield _stream_event_adapter.validate_python(payload)
                except Exception:
                    logger.debug("Skipping unknown stream event: %s", event_type)

    if data_buf:
        payload = json.loads(data_buf)
        event_type = payload.get("type", "")
        if event_type == "error":
            error = payload.get("error", {})
            raise MiniMaxError(
                error.get("message", "Stream error"),
                code=0,
                trace_id="",
            )
        if event_type != "ping":
            try:
                yield _stream_event_adapter.validate_python(payload)
            except Exception:
                logger.debug("Skipping unknown stream event: %s", event_type)


# -- Sync ---------------------------------------------------------------------


class Text(SyncResource):
    """Synchronous text generation resource.

    Uses MiniMax's Anthropic-compatible endpoint to generate text responses.
    Supports multi-turn conversations, tool use, and extended thinking.
    """

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        system: str | list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        thinking: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        """Create a text generation (chat completion) request.

        Args:
            model: Model ID (e.g. ``"MiniMax-M2.7"``, ``"MiniMax-M2.5"``).
            messages: Conversation history as a list of message dicts with
                ``role`` (``"user"`` or ``"assistant"``) and ``content``.
            max_tokens: Maximum number of tokens to generate.
            system: System prompt — either a plain string or a list of
                text block dicts.
            temperature: Sampling temperature in range (0, 1].
            top_p: Nucleus sampling threshold in range (0, 1].
            tools: Tool definitions for function calling.
            tool_choice: Tool selection strategy (``auto``, ``any``, ``tool``,
                or ``none``).
            thinking: Extended thinking configuration, e.g.
                ``{"type": "enabled", "budget_tokens": 10000}``.
            metadata: Request metadata (e.g. ``{"user_id": "..."}``.

        Returns:
            A :class:`Message` with the model's response content, usage
            statistics, and stop reason.
        """
        body = _build_messages_body(
            model,
            messages,
            max_tokens,
            system=system,
            temperature=temperature,
            top_p=top_p,
            tools=tools,
            tool_choice=tool_choice,
            thinking=thinking,
            metadata=metadata,
        )

        resp = self._http.request_anthropic("POST", _MESSAGES_PATH, json=body)
        return _parse_message(resp)

    def create_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        system: str | list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        thinking: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[StreamEvent]:
        """Create a streaming text generation request.

        Yields :class:`StreamEvent` objects as the model generates content.
        Events follow the Anthropic SSE format::

            message_start → content_block_start → content_block_delta* →
            content_block_stop → ... → message_delta → message_stop

        Example::

            for event in client.text.create_stream(
                model="MiniMax-M2.7",
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=1024,
            ):
                if event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        print(event.delta.text, end="", flush=True)

        Args:
            model: Model ID (e.g. ``"MiniMax-M2.7"``).
            messages: Conversation history.
            max_tokens: Maximum number of tokens to generate.
            system: System prompt.
            temperature: Sampling temperature in range (0, 1].
            top_p: Nucleus sampling threshold in range (0, 1].
            tools: Tool definitions for function calling.
            tool_choice: Tool selection strategy.
            thinking: Extended thinking configuration.
            metadata: Request metadata.

        Yields:
            :class:`StreamEvent` — one of ``MessageStartEvent``,
            ``ContentBlockStartEvent``, ``ContentBlockDeltaEvent``,
            ``ContentBlockStopEvent``, ``MessageDeltaEvent``, or
            ``MessageStopEvent``.
        """
        body = _build_messages_body(
            model,
            messages,
            max_tokens,
            system=system,
            temperature=temperature,
            top_p=top_p,
            tools=tools,
            tool_choice=tool_choice,
            thinking=thinking,
            metadata=metadata,
        )
        body["stream"] = True

        raw_lines = self._http.stream_request_anthropic("POST", _MESSAGES_PATH, json=body)
        yield from _parse_sse_events(raw_lines)


# -- Async --------------------------------------------------------------------


class AsyncText(AsyncResource):
    """Asynchronous text generation resource.

    Uses MiniMax's Anthropic-compatible endpoint to generate text responses.
    Supports multi-turn conversations, tool use, and extended thinking.
    """

    async def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        system: str | list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        thinking: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        """Create a text generation (chat completion) request.

        Args:
            model: Model ID (e.g. ``"MiniMax-M2.7"``, ``"MiniMax-M2.5"``).
            messages: Conversation history as a list of message dicts with
                ``role`` (``"user"`` or ``"assistant"``) and ``content``.
            max_tokens: Maximum number of tokens to generate.
            system: System prompt — either a plain string or a list of
                text block dicts.
            temperature: Sampling temperature in range (0, 1].
            top_p: Nucleus sampling threshold in range (0, 1].
            tools: Tool definitions for function calling.
            tool_choice: Tool selection strategy (``auto``, ``any``, ``tool``,
                or ``none``).
            thinking: Extended thinking configuration, e.g.
                ``{"type": "enabled", "budget_tokens": 10000}``.
            metadata: Request metadata (e.g. ``{"user_id": "..."}``.

        Returns:
            A :class:`Message` with the model's response content, usage
            statistics, and stop reason.
        """
        body = _build_messages_body(
            model,
            messages,
            max_tokens,
            system=system,
            temperature=temperature,
            top_p=top_p,
            tools=tools,
            tool_choice=tool_choice,
            thinking=thinking,
            metadata=metadata,
        )

        resp = await self._http.request_anthropic("POST", _MESSAGES_PATH, json=body)
        return _parse_message(resp)

    async def create_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        system: str | list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        thinking: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Create a streaming text generation request (async).

        Yields :class:`StreamEvent` objects as the model generates content.

        Example::

            async for event in client.text.create_stream(
                model="MiniMax-M2.7",
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=1024,
            ):
                if event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        print(event.delta.text, end="", flush=True)

        Args:
            model: Model ID.
            messages: Conversation history.
            max_tokens: Maximum number of tokens to generate.
            system: System prompt.
            temperature: Sampling temperature in range (0, 1].
            top_p: Nucleus sampling threshold in range (0, 1].
            tools: Tool definitions for function calling.
            tool_choice: Tool selection strategy.
            thinking: Extended thinking configuration.
            metadata: Request metadata.

        Yields:
            :class:`StreamEvent` objects.
        """
        body = _build_messages_body(
            model,
            messages,
            max_tokens,
            system=system,
            temperature=temperature,
            top_p=top_p,
            tools=tools,
            tool_choice=tool_choice,
            thinking=thinking,
            metadata=metadata,
        )
        body["stream"] = True

        raw_lines = self._http.stream_request_anthropic("POST", _MESSAGES_PATH, json=body)
        async for event in _parse_sse_events_async(raw_lines):
            yield event
