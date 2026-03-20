"""Text resource -- synchronous and asynchronous text generation.

Provides both synchronous (:class:`Text`) and asynchronous (:class:`AsyncText`)
clients for text generation via MiniMax's Anthropic-compatible endpoint
(``POST /anthropic/v1/messages``).
"""

from __future__ import annotations

from typing import Any

from .._base import AsyncResource, SyncResource
from ..types.text import Message

_MESSAGES_PATH = "/anthropic/v1/messages"


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
