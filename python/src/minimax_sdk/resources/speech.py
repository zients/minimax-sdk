"""Speech resource — synchronous TTS, streaming TTS, WebSocket TTS, and async long-text TTS.

Provides ``Speech`` (sync) and ``AsyncSpeech`` resource classes plus
``SpeechConnection`` and ``AsyncSpeechConnection`` for WebSocket-based
real-time speech synthesis.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Iterator
from urllib.parse import urlparse

import websockets
import websockets.asyncio.client
import websockets.sync.client

from .._audio import AudioResponse, build_audio_response, decode_hex_audio
from .._base import AsyncResource, SyncResource
from .._http import _raise_for_status
from .._polling import async_poll_task, poll_task
from ..exceptions import MiniMaxError
from ..types.speech import TaskResult

logger = logging.getLogger("minimax_sdk")

# ── Constants ────────────────────────────────────────────────────────────────

_T2A_PATH = "/v1/t2a_v2"
_T2A_ASYNC_PATH = "/v1/t2a_async_v2"
_T2A_ASYNC_QUERY_PATH = "/v1/query/t2a_async_query_v2"
_WS_T2A_PATH = "/ws/v1/t2a_v2"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_tts_body(
    text: str,
    model: str,
    *,
    stream: bool = False,
    voice_setting: dict[str, Any] | None = None,
    audio_setting: dict[str, Any] | None = None,
    language_boost: str | None = None,
    voice_modify: dict[str, Any] | None = None,
    pronunciation_dict: dict[str, Any] | None = None,
    timbre_weights: list[Any] | None = None,
    subtitle_enable: bool = False,
    output_format: str = "hex",
) -> dict[str, Any]:
    """Assemble the JSON request body for ``POST /v1/t2a_v2``."""
    body: dict[str, Any] = {
        "model": model,
        "text": text,
        "stream": stream,
        "output_format": output_format,
    }
    if voice_setting is not None:
        body["voice_setting"] = voice_setting
    if audio_setting is not None:
        body["audio_setting"] = audio_setting
    if language_boost is not None:
        body["language_boost"] = language_boost
    if voice_modify is not None:
        body["voice_modify"] = voice_modify
    if pronunciation_dict is not None:
        body["pronunciation_dict"] = pronunciation_dict
    if timbre_weights is not None:
        body["timbre_weights"] = timbre_weights
    if subtitle_enable:
        body["subtitle_enable"] = True
    return body


def _build_async_body(
    *,
    text: str | None = None,
    model: str = "speech-2.8-hd",
    text_file_id: int | None = None,
    voice_setting: dict[str, Any],
    audio_setting: dict[str, Any] | None = None,
    language_boost: str | None = None,
    voice_modify: dict[str, Any] | None = None,
    pronunciation_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the JSON request body for ``POST /v1/t2a_async_v2``."""
    body: dict[str, Any] = {
        "model": model,
        "voice_setting": voice_setting,
    }
    if text is not None:
        body["text"] = text
    if text_file_id is not None:
        body["text_file_id"] = text_file_id
    if audio_setting is not None:
        body["audio_setting"] = audio_setting
    if language_boost is not None:
        body["language_boost"] = language_boost
    if voice_modify is not None:
        body["voice_modify"] = voice_modify
    if pronunciation_dict is not None:
        body["pronunciation_dict"] = pronunciation_dict
    return body


def _ws_url(base_url: str) -> str:
    """Derive the WebSocket URL from the HTTP base URL.

    Converts ``https://api.minimax.io`` → ``wss://api.minimax.io``.
    """
    parsed = urlparse(base_url)
    host = parsed.hostname or "api.minimax.io"
    port_suffix = f":{parsed.port}" if parsed.port else ""
    return f"wss://{host}{port_suffix}{_WS_T2A_PATH}"


def _build_ws_config(
    model: str,
    *,
    voice_setting: dict[str, Any],
    audio_setting: dict[str, Any] | None = None,
    language_boost: str | None = None,
    voice_modify: dict[str, Any] | None = None,
    pronunciation_dict: dict[str, Any] | None = None,
    timbre_weights: list[Any] | None = None,
) -> dict[str, Any]:
    """Build the shared config dict used in WebSocket ``task_start`` messages."""
    config: dict[str, Any] = {
        "model": model,
        "voice_setting": voice_setting,
    }
    if audio_setting is not None:
        config["audio_setting"] = audio_setting
    if language_boost is not None:
        config["language_boost"] = language_boost
    if voice_modify is not None:
        config["voice_modify"] = voice_modify
    if pronunciation_dict is not None:
        config["pronunciation_dict"] = pronunciation_dict
    if timbre_weights is not None:
        config["timbre_weights"] = timbre_weights
    return config


def _parse_ws_message(raw: str) -> dict[str, Any]:
    """Parse a WebSocket text frame as JSON and raise on API errors."""
    msg: dict[str, Any] = json.loads(raw)
    # Check for error in base_resp if present.
    base_resp = msg.get("base_resp", {})
    code = int(base_resp.get("status_code", 0))
    if code != 0:
        _raise_for_status(msg)
    return msg


def _audio_response_from_ws_chunks(
    hex_chunks: list[str],
    extra_info: dict[str, Any],
) -> AudioResponse:
    """Assemble an ``AudioResponse`` from collected WebSocket hex chunks."""
    combined_hex = "".join(hex_chunks)
    audio_bytes = decode_hex_audio(combined_hex) if combined_hex else b""

    duration = float(extra_info.get("audio_length", 0))
    sample_rate = int(extra_info.get("audio_sample_rate", 0))
    audio_size = int(extra_info.get("audio_size", 0)) or len(audio_bytes)
    audio_format = extra_info.get("audio_format", "mp3")

    return AudioResponse(
        data=audio_bytes,
        duration=duration,
        sample_rate=sample_rate,
        format=audio_format,
        size=audio_size,
    )


# ── SSE Helpers ──────────────────────────────────────────────────────────────


def _iter_sse_audio_chunks(raw_iter: Iterator[Any]) -> Iterator[bytes]:
    """Yield decoded audio bytes from an SSE stream of TTS responses.

    Each chunk from the iterator is expected to be a parsed response dict
    (or a raw SSE line). We extract ``data.audio`` hex strings and decode.
    """
    for chunk in raw_iter:
        if isinstance(chunk, dict):
            data_section = chunk.get("data") or {}
            hex_audio = data_section.get("audio", "")
            if hex_audio:
                yield decode_hex_audio(hex_audio)
        elif isinstance(chunk, (str, bytes)):
            # Raw SSE line — attempt to parse as JSON
            text = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
            text = text.strip()
            if not text or text.startswith(":"):
                continue
            if text.startswith("data:"):
                text = text[len("data:") :].strip()
            if text == "[DONE]":
                return
            try:
                parsed = json.loads(text)
                data_section = parsed.get("data") or {}
                hex_audio = data_section.get("audio", "")
                if hex_audio:
                    yield decode_hex_audio(hex_audio)
            except json.JSONDecodeError:
                continue


async def _aiter_sse_audio_chunks(raw_iter: AsyncIterator[Any]) -> AsyncIterator[bytes]:
    """Async version of :func:`_iter_sse_audio_chunks`."""
    async for chunk in raw_iter:
        if isinstance(chunk, dict):
            data_section = chunk.get("data") or {}
            hex_audio = data_section.get("audio", "")
            if hex_audio:
                yield decode_hex_audio(hex_audio)
        elif isinstance(chunk, (str, bytes)):
            text = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
            text = text.strip()
            if not text or text.startswith(":"):
                continue
            if text.startswith("data:"):
                text = text[len("data:") :].strip()
            if text == "[DONE]":
                return
            try:
                parsed = json.loads(text)
                data_section = parsed.get("data") or {}
                hex_audio = data_section.get("audio", "")
                if hex_audio:
                    yield decode_hex_audio(hex_audio)
            except json.JSONDecodeError:
                continue


# ── SpeechConnection (sync) ─────────────────────────────────────────────────


class SpeechConnection:
    """Synchronous WebSocket connection for real-time TTS.

    Created by :meth:`Speech.connect`. Manages the lifecycle of a single
    WebSocket session, including the ``task_start`` / ``task_continue`` /
    ``task_finish`` protocol.

    Supports use as a context manager::

        with client.speech.connect(model="speech-2.8-hd", ...) as conn:
            audio = conn.send("Hello, world!")

    The WebSocket has a 120-second idle timeout enforced by the server.
    There is no auto-reconnect; create a new connection if the old one drops.
    """

    def __init__(
        self,
        ws: websockets.sync.client.ClientConnection,
        model: str,
        voice_setting: dict[str, Any],
        *,
        audio_setting: dict[str, Any] | None = None,
        language_boost: str | None = None,
        voice_modify: dict[str, Any] | None = None,
        pronunciation_dict: dict[str, Any] | None = None,
        timbre_weights: list[Any] | None = None,
    ) -> None:
        self._ws = ws
        self._model = model
        self._config = _build_ws_config(
            model,
            voice_setting=voice_setting,
            audio_setting=audio_setting,
            language_boost=language_boost,
            voice_modify=voice_modify,
            pronunciation_dict=pronunciation_dict,
            timbre_weights=timbre_weights,
        )
        self.session_id: str = ""
        self._closed = False

        # Send task_start and wait for task_started
        self._start()

    def _start(self) -> None:
        """Send ``task_start`` and block until ``task_started`` is received."""
        start_msg: dict[str, Any] = {
            "event": "task_start",
            **self._config,
        }
        self._ws.send(json.dumps(start_msg))

        # Wait for task_started acknowledgement
        while True:
            raw = self._ws.recv()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            msg = _parse_ws_message(raw)
            event = msg.get("event", "")
            if event == "task_started":
                self.session_id = msg.get("session_id", "")
                return
            if event == "task_failed":
                raise MiniMaxError(
                    msg.get("message", "WebSocket task_start failed"),
                    code=msg.get("base_resp", {}).get("status_code", 0),
                    trace_id=msg.get("trace_id", ""),
                )

    def send(self, text: str) -> AudioResponse:
        """Send text and receive a complete :class:`AudioResponse`.

        Sends a ``task_continue`` event with the given *text*, collects all
        ``task_continued`` response chunks, decodes the hex audio, and
        returns a single :class:`AudioResponse`.

        Parameters
        ----------
        text:
            The text to synthesize.

        Returns
        -------
        AudioResponse:
            The fully decoded audio response.

        Raises
        ------
        MiniMaxError:
            If the server returns an error event.
        ConnectionError:
            If the WebSocket connection drops unexpectedly.
        """
        if self._closed:
            raise ConnectionError("SpeechConnection is already closed.")

        logger.debug("WebSocket send text (%d chars)", len(text))
        continue_msg: dict[str, Any] = {
            "event": "task_continue",
            "text": text,
        }
        try:
            self._ws.send(json.dumps(continue_msg))
        except Exception as exc:
            raise ConnectionError(f"WebSocket send failed: {exc}") from exc

        hex_chunks: list[str] = []
        extra_info: dict[str, Any] = {}

        try:
            while True:
                raw = self._ws.recv()
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                msg = _parse_ws_message(raw)
                event = msg.get("event", "")

                if event == "task_continued":
                    data_section = msg.get("data") or {}
                    hex_audio = data_section.get("audio", "")
                    if hex_audio:
                        hex_chunks.append(hex_audio)
                    if "extra_info" in msg:
                        extra_info = msg["extra_info"]
                    # is_final signals the last chunk for this text
                    if msg.get("is_final"):
                        break

                elif event == "task_failed":
                    raise MiniMaxError(
                        msg.get("message", "WebSocket task_continue failed"),
                        code=msg.get("base_resp", {}).get("status_code", 0),
                        trace_id=msg.get("trace_id", ""),
                    )
        except websockets.exceptions.ConnectionClosed as exc:
            raise ConnectionError(f"WebSocket connection closed unexpectedly: {exc}") from exc

        return _audio_response_from_ws_chunks(hex_chunks, extra_info)

    def send_stream(self, text: str) -> Iterator[bytes]:
        """Send text and yield decoded audio bytes as they arrive.

        Sends a ``task_continue`` event and yields each decoded audio chunk
        as it is received from the server. This is useful for low-latency
        playback scenarios.

        Parameters
        ----------
        text:
            The text to synthesize.

        Yields
        ------
        bytes:
            Decoded audio bytes for each chunk.

        Raises
        ------
        MiniMaxError:
            If the server returns an error event.
        ConnectionError:
            If the WebSocket connection drops unexpectedly.
        """
        if self._closed:
            raise ConnectionError("SpeechConnection is already closed.")

        logger.debug("WebSocket send text (%d chars, stream)", len(text))
        continue_msg: dict[str, Any] = {
            "event": "task_continue",
            "text": text,
        }
        try:
            self._ws.send(json.dumps(continue_msg))
        except Exception as exc:
            raise ConnectionError(f"WebSocket send failed: {exc}") from exc

        try:
            while True:
                raw = self._ws.recv()
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                msg = _parse_ws_message(raw)
                event = msg.get("event", "")

                if event == "task_continued":
                    data_section = msg.get("data") or {}
                    hex_audio = data_section.get("audio", "")
                    if hex_audio:
                        yield decode_hex_audio(hex_audio)
                    if msg.get("is_final"):
                        return

                elif event == "task_failed":
                    raise MiniMaxError(
                        msg.get("message", "WebSocket task_continue failed"),
                        code=msg.get("base_resp", {}).get("status_code", 0),
                        trace_id=msg.get("trace_id", ""),
                    )
        except websockets.exceptions.ConnectionClosed as exc:
            raise ConnectionError(f"WebSocket connection closed unexpectedly: {exc}") from exc

    def close(self) -> None:
        """Send ``task_finish`` and close the WebSocket connection.

        Safe to call multiple times.
        """
        if self._closed:
            return
        self._closed = True

        logger.debug("WebSocket disconnecting")
        try:
            finish_msg: dict[str, Any] = {"event": "task_finish"}
            self._ws.send(json.dumps(finish_msg))

            # Wait for task_finished acknowledgement
            while True:
                raw = self._ws.recv()
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                msg = _parse_ws_message(raw)
                event = msg.get("event", "")
                if event == "task_finished":
                    break
                if event == "task_failed":
                    # Still close, but note the failure
                    break
        except (websockets.exceptions.ConnectionClosed, OSError):
            pass  # Connection already gone — nothing to do
        finally:
            try:
                self._ws.close()
            except Exception:
                pass

    def __enter__(self) -> SpeechConnection:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self.close()


# ── AsyncSpeechConnection ───────────────────────────────────────────────────


class AsyncSpeechConnection:
    """Asynchronous WebSocket connection for real-time TTS.

    Created by :meth:`AsyncSpeech.connect`. Manages the lifecycle of a single
    WebSocket session using the ``task_start`` / ``task_continue`` /
    ``task_finish`` protocol.

    Supports use as an async context manager::

        async with client.speech.connect(model="speech-2.8-hd", ...) as conn:
            audio = await conn.send("Hello, world!")

    The WebSocket has a 120-second idle timeout enforced by the server.
    There is no auto-reconnect; create a new connection if the old one drops.
    """

    def __init__(
        self,
        ws: websockets.asyncio.client.ClientConnection,
        model: str,
        voice_setting: dict[str, Any],
        *,
        audio_setting: dict[str, Any] | None = None,
        language_boost: str | None = None,
        voice_modify: dict[str, Any] | None = None,
        pronunciation_dict: dict[str, Any] | None = None,
        timbre_weights: list[Any] | None = None,
    ) -> None:
        self._ws = ws
        self._model = model
        self._config = _build_ws_config(
            model,
            voice_setting=voice_setting,
            audio_setting=audio_setting,
            language_boost=language_boost,
            voice_modify=voice_modify,
            pronunciation_dict=pronunciation_dict,
            timbre_weights=timbre_weights,
        )
        self.session_id: str = ""
        self._closed = False

    async def _start(self) -> None:
        """Send ``task_start`` and wait for ``task_started``."""
        start_msg: dict[str, Any] = {
            "event": "task_start",
            **self._config,
        }
        await self._ws.send(json.dumps(start_msg))

        while True:
            raw = await self._ws.recv()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            msg = _parse_ws_message(raw)
            event = msg.get("event", "")
            if event == "task_started":
                self.session_id = msg.get("session_id", "")
                return
            if event == "task_failed":
                raise MiniMaxError(
                    msg.get("message", "WebSocket task_start failed"),
                    code=msg.get("base_resp", {}).get("status_code", 0),
                    trace_id=msg.get("trace_id", ""),
                )

    async def send(self, text: str) -> AudioResponse:
        """Send text and receive a complete :class:`AudioResponse`.

        Sends a ``task_continue`` event with the given *text*, collects all
        ``task_continued`` response chunks, decodes the hex audio, and
        returns a single :class:`AudioResponse`.

        Parameters
        ----------
        text:
            The text to synthesize.

        Returns
        -------
        AudioResponse:
            The fully decoded audio response.

        Raises
        ------
        MiniMaxError:
            If the server returns an error event.
        ConnectionError:
            If the WebSocket connection drops unexpectedly.
        """
        if self._closed:
            raise ConnectionError("AsyncSpeechConnection is already closed.")

        logger.debug("WebSocket send text (%d chars)", len(text))
        continue_msg: dict[str, Any] = {
            "event": "task_continue",
            "text": text,
        }
        try:
            await self._ws.send(json.dumps(continue_msg))
        except Exception as exc:
            raise ConnectionError(f"WebSocket send failed: {exc}") from exc

        hex_chunks: list[str] = []
        extra_info: dict[str, Any] = {}

        try:
            while True:
                raw = await self._ws.recv()
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                msg = _parse_ws_message(raw)
                event = msg.get("event", "")

                if event == "task_continued":
                    data_section = msg.get("data") or {}
                    hex_audio = data_section.get("audio", "")
                    if hex_audio:
                        hex_chunks.append(hex_audio)
                    if "extra_info" in msg:
                        extra_info = msg["extra_info"]
                    if msg.get("is_final"):
                        break

                elif event == "task_failed":
                    raise MiniMaxError(
                        msg.get("message", "WebSocket task_continue failed"),
                        code=msg.get("base_resp", {}).get("status_code", 0),
                        trace_id=msg.get("trace_id", ""),
                    )
        except websockets.exceptions.ConnectionClosed as exc:
            raise ConnectionError(f"WebSocket connection closed unexpectedly: {exc}") from exc

        return _audio_response_from_ws_chunks(hex_chunks, extra_info)

    async def send_stream(self, text: str) -> AsyncIterator[bytes]:
        """Send text and yield decoded audio bytes as they arrive.

        Sends a ``task_continue`` event and yields each decoded audio chunk
        as it is received from the server.

        Parameters
        ----------
        text:
            The text to synthesize.

        Yields
        ------
        bytes:
            Decoded audio bytes for each chunk.

        Raises
        ------
        MiniMaxError:
            If the server returns an error event.
        ConnectionError:
            If the WebSocket connection drops unexpectedly.
        """
        if self._closed:
            raise ConnectionError("AsyncSpeechConnection is already closed.")

        logger.debug("WebSocket send text (%d chars, stream)", len(text))
        continue_msg: dict[str, Any] = {
            "event": "task_continue",
            "text": text,
        }
        try:
            await self._ws.send(json.dumps(continue_msg))
        except Exception as exc:
            raise ConnectionError(f"WebSocket send failed: {exc}") from exc

        try:
            while True:
                raw = await self._ws.recv()
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                msg = _parse_ws_message(raw)
                event = msg.get("event", "")

                if event == "task_continued":
                    data_section = msg.get("data") or {}
                    hex_audio = data_section.get("audio", "")
                    if hex_audio:
                        yield decode_hex_audio(hex_audio)
                    if msg.get("is_final"):
                        return

                elif event == "task_failed":
                    raise MiniMaxError(
                        msg.get("message", "WebSocket task_continue failed"),
                        code=msg.get("base_resp", {}).get("status_code", 0),
                        trace_id=msg.get("trace_id", ""),
                    )
        except websockets.exceptions.ConnectionClosed as exc:
            raise ConnectionError(f"WebSocket connection closed unexpectedly: {exc}") from exc

    async def close(self) -> None:
        """Send ``task_finish`` and close the WebSocket connection.

        Safe to call multiple times.
        """
        if self._closed:
            return
        self._closed = True

        logger.debug("WebSocket disconnecting")
        try:
            finish_msg: dict[str, Any] = {"event": "task_finish"}
            await self._ws.send(json.dumps(finish_msg))

            while True:
                raw = await self._ws.recv()
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                msg = _parse_ws_message(raw)
                event = msg.get("event", "")
                if event == "task_finished":
                    break
                if event == "task_failed":
                    break
        except (websockets.exceptions.ConnectionClosed, OSError):
            pass
        finally:
            try:
                await self._ws.close()
            except Exception:
                pass

    async def __aenter__(self) -> AsyncSpeechConnection:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()


# ── Speech (sync resource) ──────────────────────────────────────────────────


class Speech(SyncResource):
    """Synchronous speech synthesis resource.

    Exposes six methods covering the full MiniMax TTS surface:

    - :meth:`tts` — one-shot synchronous synthesis returning an
      :class:`AudioResponse`.
    - :meth:`tts_stream` — streaming synthesis yielding decoded ``bytes``
      chunks.
    - :meth:`connect` — WebSocket-based real-time TTS returning a
      :class:`SpeechConnection`.
    - :meth:`async_create` — low-level: create a long-text async task.
    - :meth:`async_query` — low-level: query an async task status.
    - :meth:`async_generate` — high-level: create + poll + retrieve for
      long-text synthesis.
    """

    # ── Synchronous TTS ──────────────────────────────────────────────────

    def tts(
        self,
        text: str,
        model: str,
        *,
        voice_setting: dict[str, Any] | None = None,
        audio_setting: dict[str, Any] | None = None,
        language_boost: str | None = None,
        voice_modify: dict[str, Any] | None = None,
        pronunciation_dict: dict[str, Any] | None = None,
        timbre_weights: list[Any] | None = None,
        subtitle_enable: bool = False,
        output_format: str = "hex",
    ) -> AudioResponse:
        """Synthesize speech from text (synchronous, non-streaming).

        Sends a ``POST /v1/t2a_v2`` request with ``stream=false`` and
        returns a fully decoded :class:`AudioResponse`.

        Parameters
        ----------
        text:
            The text to synthesize.
        model:
            The TTS model to use (e.g. ``"speech-2.8-hd"``).
        voice_setting:
            Voice configuration (voice_id, speed, vol, pitch, etc.).
        audio_setting:
            Audio output configuration (sample_rate, format, etc.).
        language_boost:
            ISO language code to boost recognition for a specific language.
        voice_modify:
            Voice modification parameters (pitch, intensity, etc.).
        pronunciation_dict:
            Custom pronunciation dictionary entries.
        timbre_weights:
            Timbre blending weights for multi-voice synthesis.
        subtitle_enable:
            Whether to include subtitle/timing information.
        output_format:
            Audio encoding in the response (default ``"hex"``).

        Returns
        -------
        AudioResponse:
            The synthesized audio with decoded bytes.
        """
        body = _build_tts_body(
            text,
            model,
            stream=False,
            voice_setting=voice_setting,
            audio_setting=audio_setting,
            language_boost=language_boost,
            voice_modify=voice_modify,
            pronunciation_dict=pronunciation_dict,
            timbre_weights=timbre_weights,
            subtitle_enable=subtitle_enable,
            output_format=output_format,
        )
        resp = self._http.request("POST", _T2A_PATH, json=body)
        return build_audio_response(resp)

    # ── Streaming TTS ────────────────────────────────────────────────────

    def tts_stream(
        self,
        text: str,
        model: str,
        *,
        voice_setting: dict[str, Any] | None = None,
        audio_setting: dict[str, Any] | None = None,
        language_boost: str | None = None,
        voice_modify: dict[str, Any] | None = None,
        pronunciation_dict: dict[str, Any] | None = None,
        timbre_weights: list[Any] | None = None,
        subtitle_enable: bool = False,
        output_format: str = "hex",
    ) -> Iterator[bytes]:
        """Synthesize speech from text with streaming output.

        Sends a ``POST /v1/t2a_v2`` request with ``stream=true`` in the
        body and yields decoded audio bytes as each SSE event arrives.

        Parameters
        ----------
        text:
            The text to synthesize.
        model:
            The TTS model to use.
        voice_setting:
            Voice configuration.
        audio_setting:
            Audio output configuration.
        language_boost:
            ISO language code to boost recognition for a specific language.
        voice_modify:
            Voice modification parameters.
        pronunciation_dict:
            Custom pronunciation dictionary entries.
        timbre_weights:
            Timbre blending weights.
        subtitle_enable:
            Whether to include subtitle/timing information.
        output_format:
            Audio encoding in the response (default ``"hex"``).

        Yields
        ------
        bytes:
            Decoded audio bytes for each streamed chunk.
        """
        body = _build_tts_body(
            text,
            model,
            stream=True,
            voice_setting=voice_setting,
            audio_setting=audio_setting,
            language_boost=language_boost,
            voice_modify=voice_modify,
            pronunciation_dict=pronunciation_dict,
            timbre_weights=timbre_weights,
            subtitle_enable=subtitle_enable,
            output_format=output_format,
        )
        raw_iter = self._http.stream_request("POST", _T2A_PATH, json=body)
        yield from _iter_sse_audio_chunks(raw_iter)

    # ── WebSocket TTS ────────────────────────────────────────────────────

    def connect(
        self,
        model: str,
        *,
        voice_setting: dict[str, Any],
        audio_setting: dict[str, Any] | None = None,
        language_boost: str | None = None,
        voice_modify: dict[str, Any] | None = None,
        pronunciation_dict: dict[str, Any] | None = None,
        timbre_weights: list[Any] | None = None,
    ) -> SpeechConnection:
        """Open a WebSocket connection for real-time TTS.

        Connects to ``wss://{host}/ws/v1/t2a_v2``, sends a ``task_start``
        message, and waits for ``task_started`` before returning a
        :class:`SpeechConnection`.

        The returned connection supports context manager usage::

            with client.speech.connect(model="speech-2.8-hd", ...) as conn:
                audio = conn.send("Hello!")

        Parameters
        ----------
        model:
            The TTS model to use.
        voice_setting:
            Voice configuration (required for WebSocket TTS).
        audio_setting:
            Audio output configuration.
        language_boost:
            ISO language code to boost recognition for a specific language.
        voice_modify:
            Voice modification parameters.
        pronunciation_dict:
            Custom pronunciation dictionary entries.
        timbre_weights:
            Timbre blending weights.

        Returns
        -------
        SpeechConnection:
            A connected WebSocket session ready for :meth:`~SpeechConnection.send`
            calls.

        Raises
        ------
        ConnectionError:
            If the WebSocket connection cannot be established.
        MiniMaxError:
            If the server rejects the ``task_start`` request.
        """
        url = _ws_url(self._http.base_url)
        headers = {"Authorization": f"Bearer {self._http._api_key}"}

        logger.debug("WebSocket connecting to %s", url)
        try:
            ws = websockets.sync.client.connect(url, additional_headers=headers)
        except Exception as exc:
            raise ConnectionError(
                f"Failed to establish WebSocket connection to {url}: {exc}"
            ) from exc

        return SpeechConnection(
            ws,
            model,
            voice_setting,
            audio_setting=audio_setting,
            language_boost=language_boost,
            voice_modify=voice_modify,
            pronunciation_dict=pronunciation_dict,
            timbre_weights=timbre_weights,
        )

    # ── Async TTS (long text) ────────────────────────────────────────────

    def async_create(
        self,
        text: str | None = None,
        model: str = "speech-2.8-hd",
        *,
        text_file_id: int | None = None,
        voice_setting: dict[str, Any],
        audio_setting: dict[str, Any] | None = None,
        language_boost: str | None = None,
        voice_modify: dict[str, Any] | None = None,
        pronunciation_dict: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a long-text async TTS task.

        Sends a ``POST /v1/t2a_async_v2`` request. Returns the raw response
        dict containing ``task_id``, ``file_id``, and ``task_token``.

        Either *text* or *text_file_id* must be provided.

        Parameters
        ----------
        text:
            The text to synthesize. Mutually exclusive with *text_file_id*.
        model:
            The TTS model to use.
        text_file_id:
            ID of a previously uploaded text file. Mutually exclusive with
            *text*.
        voice_setting:
            Voice configuration (required).
        audio_setting:
            Audio output configuration.
        language_boost:
            ISO language code to boost recognition for a specific language.
        voice_modify:
            Voice modification parameters.
        pronunciation_dict:
            Custom pronunciation dictionary entries.

        Returns
        -------
        dict:
            Raw API response with ``task_id``, ``file_id``, and
            ``task_token``.
        """
        body = _build_async_body(
            text=text,
            model=model,
            text_file_id=text_file_id,
            voice_setting=voice_setting,
            audio_setting=audio_setting,
            language_boost=language_boost,
            voice_modify=voice_modify,
            pronunciation_dict=pronunciation_dict,
        )
        return self._http.request("POST", _T2A_ASYNC_PATH, json=body)

    def async_query(self, task_id: str) -> dict[str, Any]:
        """Query the status of an async TTS task.

        Sends a ``GET /v1/query/t2a_async_query_v2?task_id={task_id}``.

        Parameters
        ----------
        task_id:
            The task identifier returned by :meth:`async_create`.

        Returns
        -------
        dict:
            Raw API response with ``task_id``, ``status``, and ``file_id``
            (when complete).
        """
        return self._http.request(
            "GET",
            _T2A_ASYNC_QUERY_PATH,
            params={"task_id": task_id},
        )

    def async_generate(
        self,
        text: str | None = None,
        model: str = "speech-2.8-hd",
        *,
        text_file_id: int | None = None,
        voice_setting: dict[str, Any],
        audio_setting: dict[str, Any] | None = None,
        language_boost: str | None = None,
        voice_modify: dict[str, Any] | None = None,
        pronunciation_dict: dict[str, Any] | None = None,
        poll_interval: float | None = None,
        poll_timeout: float | None = None,
    ) -> TaskResult:
        """Create a long-text TTS task and wait for it to complete.

        This high-level method combines :meth:`async_create`,
        :meth:`async_query` (via automatic polling), and
        ``files.retrieve`` into a single call.

        Parameters
        ----------
        text:
            The text to synthesize.
        model:
            The TTS model to use.
        text_file_id:
            ID of a previously uploaded text file.
        voice_setting:
            Voice configuration (required).
        audio_setting:
            Audio output configuration.
        language_boost:
            ISO language code to boost recognition for a specific language.
        voice_modify:
            Voice modification parameters.
        pronunciation_dict:
            Custom pronunciation dictionary entries.
        poll_interval:
            Seconds between status polls (default from client config).
        poll_timeout:
            Maximum seconds to wait for completion (default from client
            config).

        Returns
        -------
        TaskResult:
            The completed task result with ``download_url``.

        Raises
        ------
        PollTimeoutError:
            If the task does not complete within *poll_timeout*.
        MiniMaxError:
            If the task fails.
        """
        # Step 1: Create the async task
        create_resp = self.async_create(
            text=text,
            model=model,
            text_file_id=text_file_id,
            voice_setting=voice_setting,
            audio_setting=audio_setting,
            language_boost=language_boost,
            voice_modify=voice_modify,
            pronunciation_dict=pronunciation_dict,
        )
        task_id = create_resp.get("task_id", "")

        # Step 2: Poll until done
        interval = poll_interval if poll_interval is not None else self._client.poll_interval
        timeout = poll_timeout if poll_timeout is not None else self._client.poll_timeout

        poll_result = poll_task(
            self._http,
            _T2A_ASYNC_QUERY_PATH,
            task_id,
            poll_interval=interval,
            poll_timeout=timeout,
        )

        # Step 3: Retrieve file info for the download URL
        file_id = poll_result.get("file_id", "")
        file_info = self._client.files.retrieve(file_id)

        return TaskResult(
            task_id=task_id,
            status=poll_result.get("status", "Success"),
            file_id=file_id,
            download_url=file_info.download_url or "",
        )


# ── AsyncSpeech ─────────────────────────────────────────────────────────────


class AsyncSpeech(AsyncResource):
    """Asynchronous speech synthesis resource.

    Provides the same six methods as :class:`Speech` but as ``async``
    coroutines suitable for use with ``asyncio``.
    """

    # ── Synchronous TTS ──────────────────────────────────────────────────

    async def tts(
        self,
        text: str,
        model: str,
        *,
        voice_setting: dict[str, Any] | None = None,
        audio_setting: dict[str, Any] | None = None,
        language_boost: str | None = None,
        voice_modify: dict[str, Any] | None = None,
        pronunciation_dict: dict[str, Any] | None = None,
        timbre_weights: list[Any] | None = None,
        subtitle_enable: bool = False,
        output_format: str = "hex",
    ) -> AudioResponse:
        """Synthesize speech from text (non-streaming).

        Sends a ``POST /v1/t2a_v2`` request with ``stream=false`` and
        returns a fully decoded :class:`AudioResponse`.

        Parameters
        ----------
        text:
            The text to synthesize.
        model:
            The TTS model to use (e.g. ``"speech-2.8-hd"``).
        voice_setting:
            Voice configuration (voice_id, speed, vol, pitch, etc.).
        audio_setting:
            Audio output configuration (sample_rate, format, etc.).
        language_boost:
            ISO language code to boost recognition for a specific language.
        voice_modify:
            Voice modification parameters (pitch, intensity, etc.).
        pronunciation_dict:
            Custom pronunciation dictionary entries.
        timbre_weights:
            Timbre blending weights for multi-voice synthesis.
        subtitle_enable:
            Whether to include subtitle/timing information.
        output_format:
            Audio encoding in the response (default ``"hex"``).

        Returns
        -------
        AudioResponse:
            The synthesized audio with decoded bytes.
        """
        body = _build_tts_body(
            text,
            model,
            stream=False,
            voice_setting=voice_setting,
            audio_setting=audio_setting,
            language_boost=language_boost,
            voice_modify=voice_modify,
            pronunciation_dict=pronunciation_dict,
            timbre_weights=timbre_weights,
            subtitle_enable=subtitle_enable,
            output_format=output_format,
        )
        resp = await self._http.request("POST", _T2A_PATH, json=body)
        return build_audio_response(resp)

    # ── Streaming TTS ────────────────────────────────────────────────────

    async def tts_stream(
        self,
        text: str,
        model: str,
        *,
        voice_setting: dict[str, Any] | None = None,
        audio_setting: dict[str, Any] | None = None,
        language_boost: str | None = None,
        voice_modify: dict[str, Any] | None = None,
        pronunciation_dict: dict[str, Any] | None = None,
        timbre_weights: list[Any] | None = None,
        subtitle_enable: bool = False,
        output_format: str = "hex",
    ) -> AsyncIterator[bytes]:
        """Synthesize speech from text with streaming output.

        Sends a ``POST /v1/t2a_v2`` request with ``stream=true`` in the
        body and yields decoded audio bytes as each SSE event arrives.

        Parameters
        ----------
        text:
            The text to synthesize.
        model:
            The TTS model to use.
        voice_setting:
            Voice configuration.
        audio_setting:
            Audio output configuration.
        language_boost:
            ISO language code to boost recognition for a specific language.
        voice_modify:
            Voice modification parameters.
        pronunciation_dict:
            Custom pronunciation dictionary entries.
        timbre_weights:
            Timbre blending weights.
        subtitle_enable:
            Whether to include subtitle/timing information.
        output_format:
            Audio encoding in the response (default ``"hex"``).

        Yields
        ------
        bytes:
            Decoded audio bytes for each streamed chunk.
        """
        body = _build_tts_body(
            text,
            model,
            stream=True,
            voice_setting=voice_setting,
            audio_setting=audio_setting,
            language_boost=language_boost,
            voice_modify=voice_modify,
            pronunciation_dict=pronunciation_dict,
            timbre_weights=timbre_weights,
            subtitle_enable=subtitle_enable,
            output_format=output_format,
        )
        raw_iter = self._http.stream_request("POST", _T2A_PATH, json=body)
        async for chunk in _aiter_sse_audio_chunks(raw_iter):
            yield chunk

    # ── WebSocket TTS ────────────────────────────────────────────────────

    async def connect(
        self,
        model: str,
        *,
        voice_setting: dict[str, Any],
        audio_setting: dict[str, Any] | None = None,
        language_boost: str | None = None,
        voice_modify: dict[str, Any] | None = None,
        pronunciation_dict: dict[str, Any] | None = None,
        timbre_weights: list[Any] | None = None,
    ) -> AsyncSpeechConnection:
        """Open an async WebSocket connection for real-time TTS.

        Connects to ``wss://{host}/ws/v1/t2a_v2``, sends a ``task_start``
        message, and waits for ``task_started`` before returning an
        :class:`AsyncSpeechConnection`.

        The returned connection supports async context manager usage::

            async with client.speech.connect(model="speech-2.8-hd", ...) as conn:
                audio = await conn.send("Hello!")

        Parameters
        ----------
        model:
            The TTS model to use.
        voice_setting:
            Voice configuration (required for WebSocket TTS).
        audio_setting:
            Audio output configuration.
        language_boost:
            ISO language code to boost recognition for a specific language.
        voice_modify:
            Voice modification parameters.
        pronunciation_dict:
            Custom pronunciation dictionary entries.
        timbre_weights:
            Timbre blending weights.

        Returns
        -------
        AsyncSpeechConnection:
            A connected async WebSocket session ready for
            :meth:`~AsyncSpeechConnection.send` calls.

        Raises
        ------
        ConnectionError:
            If the WebSocket connection cannot be established.
        MiniMaxError:
            If the server rejects the ``task_start`` request.
        """
        url = _ws_url(self._http.base_url)
        headers = {"Authorization": f"Bearer {self._http._api_key}"}

        logger.debug("WebSocket connecting to %s", url)
        try:
            ws = await websockets.asyncio.client.connect(
                url, additional_headers=headers
            )
        except Exception as exc:
            raise ConnectionError(
                f"Failed to establish WebSocket connection to {url}: {exc}"
            ) from exc

        conn = AsyncSpeechConnection(
            ws,
            model,
            voice_setting,
            audio_setting=audio_setting,
            language_boost=language_boost,
            voice_modify=voice_modify,
            pronunciation_dict=pronunciation_dict,
            timbre_weights=timbre_weights,
        )
        await conn._start()
        return conn

    # ── Async TTS (long text) ────────────────────────────────────────────

    async def async_create(
        self,
        text: str | None = None,
        model: str = "speech-2.8-hd",
        *,
        text_file_id: int | None = None,
        voice_setting: dict[str, Any],
        audio_setting: dict[str, Any] | None = None,
        language_boost: str | None = None,
        voice_modify: dict[str, Any] | None = None,
        pronunciation_dict: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a long-text async TTS task.

        Sends a ``POST /v1/t2a_async_v2`` request. Returns the raw response
        dict containing ``task_id``, ``file_id``, and ``task_token``.

        Either *text* or *text_file_id* must be provided.

        Parameters
        ----------
        text:
            The text to synthesize.
        model:
            The TTS model to use.
        text_file_id:
            ID of a previously uploaded text file.
        voice_setting:
            Voice configuration (required).
        audio_setting:
            Audio output configuration.
        language_boost:
            ISO language code to boost recognition for a specific language.
        voice_modify:
            Voice modification parameters.
        pronunciation_dict:
            Custom pronunciation dictionary entries.

        Returns
        -------
        dict:
            Raw API response with ``task_id``, ``file_id``, and
            ``task_token``.
        """
        body = _build_async_body(
            text=text,
            model=model,
            text_file_id=text_file_id,
            voice_setting=voice_setting,
            audio_setting=audio_setting,
            language_boost=language_boost,
            voice_modify=voice_modify,
            pronunciation_dict=pronunciation_dict,
        )
        return await self._http.request("POST", _T2A_ASYNC_PATH, json=body)

    async def async_query(self, task_id: str) -> dict[str, Any]:
        """Query the status of an async TTS task.

        Sends a ``GET /v1/query/t2a_async_query_v2?task_id={task_id}``.

        Parameters
        ----------
        task_id:
            The task identifier returned by :meth:`async_create`.

        Returns
        -------
        dict:
            Raw API response with ``task_id``, ``status``, and ``file_id``
            (when complete).
        """
        return await self._http.request(
            "GET",
            _T2A_ASYNC_QUERY_PATH,
            params={"task_id": task_id},
        )

    async def async_generate(
        self,
        text: str | None = None,
        model: str = "speech-2.8-hd",
        *,
        text_file_id: int | None = None,
        voice_setting: dict[str, Any],
        audio_setting: dict[str, Any] | None = None,
        language_boost: str | None = None,
        voice_modify: dict[str, Any] | None = None,
        pronunciation_dict: dict[str, Any] | None = None,
        poll_interval: float | None = None,
        poll_timeout: float | None = None,
    ) -> TaskResult:
        """Create a long-text TTS task and wait for it to complete.

        This high-level method combines :meth:`async_create`,
        :meth:`async_query` (via automatic polling), and
        ``files.retrieve`` into a single call.

        Parameters
        ----------
        text:
            The text to synthesize.
        model:
            The TTS model to use.
        text_file_id:
            ID of a previously uploaded text file.
        voice_setting:
            Voice configuration (required).
        audio_setting:
            Audio output configuration.
        language_boost:
            ISO language code to boost recognition for a specific language.
        voice_modify:
            Voice modification parameters.
        pronunciation_dict:
            Custom pronunciation dictionary entries.
        poll_interval:
            Seconds between status polls (default from client config).
        poll_timeout:
            Maximum seconds to wait for completion (default from client
            config).

        Returns
        -------
        TaskResult:
            The completed task result with ``download_url``.

        Raises
        ------
        PollTimeoutError:
            If the task does not complete within *poll_timeout*.
        MiniMaxError:
            If the task fails.
        """
        # Step 1: Create the async task
        create_resp = await self.async_create(
            text=text,
            model=model,
            text_file_id=text_file_id,
            voice_setting=voice_setting,
            audio_setting=audio_setting,
            language_boost=language_boost,
            voice_modify=voice_modify,
            pronunciation_dict=pronunciation_dict,
        )
        task_id = create_resp.get("task_id", "")

        # Step 2: Poll until done
        interval = poll_interval if poll_interval is not None else self._client.poll_interval
        timeout = poll_timeout if poll_timeout is not None else self._client.poll_timeout

        poll_result = await async_poll_task(
            self._http,
            _T2A_ASYNC_QUERY_PATH,
            task_id,
            poll_interval=interval,
            poll_timeout=timeout,
        )

        # Step 3: Retrieve file info for the download URL
        file_id = poll_result.get("file_id", "")
        file_info = await self._client.files.retrieve(file_id)

        return TaskResult(
            task_id=task_id,
            status=poll_result.get("status", "Success"),
            file_id=file_id,
            download_url=file_info.download_url or "",
        )
