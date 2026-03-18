"""Tests for the Speech resource — sync and async variants.

Covers Speech, AsyncSpeech, SpeechConnection, and AsyncSpeechConnection
as well as module-level helper functions.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import websockets.exceptions

from minimax_sdk._audio import AudioResponse
from minimax_sdk.exceptions import MiniMaxError
from minimax_sdk.resources.speech import (
    AsyncSpeech,
    AsyncSpeechConnection,
    Speech,
    SpeechConnection,
    _aiter_sse_audio_chunks,
    _audio_response_from_ws_chunks,
    _build_async_body,
    _build_tts_body,
    _build_ws_config,
    _iter_sse_audio_chunks,
    _parse_ws_message,
    _ws_url,
)
from minimax_sdk.types.speech import TaskResult


# ── Shared helpers ──────────────────────────────────────────────────────────


def _ok_resp(payload: dict) -> dict:
    """Wrap *payload* in a successful API response envelope."""
    return {"base_resp": {"status_code": 0, "status_msg": "success"}, **payload}


# "Hello" in hex
_SAMPLE_HEX = "48656c6c6f"
_SAMPLE_BYTES = bytes.fromhex(_SAMPLE_HEX)


def _make_speech_resource() -> tuple[Speech, MagicMock]:
    """Create a Speech resource with a mocked HttpClient."""
    mock_http = MagicMock()
    mock_http._api_key = "test-key"
    mock_http.base_url = "https://api.minimax.io"
    mock_client = MagicMock()
    mock_client.poll_interval = 5.0
    mock_client.poll_timeout = 600.0
    mock_client.files = MagicMock()
    speech = Speech(mock_http, client=mock_client)
    return speech, mock_http


def _make_async_speech_resource() -> tuple[AsyncSpeech, AsyncMock]:
    """Create an AsyncSpeech resource with a mocked AsyncHttpClient."""
    mock_http = AsyncMock()
    mock_http._api_key = "test-key"
    mock_http.base_url = "https://api.minimax.io"
    mock_client = AsyncMock()
    mock_client.poll_interval = 5.0
    mock_client.poll_timeout = 600.0
    mock_client.files = AsyncMock()
    speech = AsyncSpeech(mock_http, client=mock_client)
    return speech, mock_http


# ── Mock WebSocket classes ──────────────────────────────────────────────────


class MockWebSocket:
    """Synchronous mock for websockets.sync.client.ClientConnection."""

    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self._messages = [json.dumps(m) for m in messages]
        self._sent: list[dict[str, Any]] = []

    def send(self, data: str | bytes) -> None:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        self._sent.append(json.loads(data))

    def recv(self) -> str:
        if self._messages:
            return self._messages.pop(0)
        raise websockets.exceptions.ConnectionClosed(None, None)

    def close(self) -> None:
        pass


class MockAsyncWebSocket:
    """Async mock for websockets.asyncio.client.ClientConnection."""

    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self._messages = [json.dumps(m) for m in messages]
        self._sent: list[dict[str, Any]] = []

    async def send(self, data: str | bytes) -> None:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        self._sent.append(json.loads(data))

    async def recv(self) -> str:
        if self._messages:
            return self._messages.pop(0)
        raise websockets.exceptions.ConnectionClosed(None, None)

    async def close(self) -> None:
        pass


# Standard WebSocket message sequences used across tests.

_WS_TASK_STARTED = {"event": "task_started", "session_id": "test-session", "base_resp": {"status_code": 0}}

_WS_CHUNK_1 = {
    "event": "task_continued",
    "data": {"audio": _SAMPLE_HEX},
    "is_final": False,
    "extra_info": {
        "audio_length": 500,
        "audio_sample_rate": 24000,
        "audio_size": len(_SAMPLE_BYTES),
        "audio_format": "mp3",
    },
    "base_resp": {"status_code": 0},
}

_WS_CHUNK_FINAL = {
    "event": "task_continued",
    "data": {"audio": ""},
    "is_final": True,
    "extra_info": {
        "audio_length": 500,
        "audio_sample_rate": 24000,
        "audio_size": len(_SAMPLE_BYTES),
        "audio_format": "mp3",
    },
    "base_resp": {"status_code": 0},
}

_WS_TASK_COMPLETE = {
    "event": "task_complete",
    "extra_info": {
        "audio_length": 500,
        "audio_sample_rate": 24000,
        "audio_size": len(_SAMPLE_BYTES),
        "audio_format": "mp3",
    },
    "base_resp": {"status_code": 0},
}

_WS_TASK_FINISHED = {"event": "task_finished", "base_resp": {"status_code": 0}}


# ═══════════════════════════════════════════════════════════════════════════
# Module-level helper tests
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildTtsBody:
    """Tests for _build_tts_body."""

    def test_minimal(self):
        body = _build_tts_body("hello", "speech-2.8-hd")
        assert body["model"] == "speech-2.8-hd"
        assert body["text"] == "hello"
        assert body["stream"] is False
        assert body["output_format"] == "hex"
        assert "voice_setting" not in body
        assert "audio_setting" not in body

    def test_all_optional_params(self):
        body = _build_tts_body(
            "hello",
            "speech-2.8-hd",
            stream=True,
            voice_setting={"voice_id": "male-1"},
            audio_setting={"sample_rate": 24000},
            language_boost="en",
            voice_modify={"pitch": 1},
            pronunciation_dict={"key": "val"},
            timbre_weights=[{"w": 1.0}],
            subtitle_enable=True,
            output_format="hex",
        )
        assert body["stream"] is True
        assert body["voice_setting"] == {"voice_id": "male-1"}
        assert body["audio_setting"] == {"sample_rate": 24000}
        assert body["language_boost"] == "en"
        assert body["voice_modify"] == {"pitch": 1}
        assert body["pronunciation_dict"] == {"key": "val"}
        assert body["timbre_weights"] == [{"w": 1.0}]
        assert body["subtitle_enable"] is True

    def test_subtitle_enable_false(self):
        body = _build_tts_body("hello", "m", subtitle_enable=False)
        assert "subtitle_enable" not in body


class TestBuildAsyncBody:
    """Tests for _build_async_body."""

    def test_text(self):
        body = _build_async_body(text="hello", voice_setting={"voice_id": "v1"})
        assert body["text"] == "hello"
        assert body["model"] == "speech-2.8-hd"
        assert body["voice_setting"] == {"voice_id": "v1"}
        assert "text_file_id" not in body

    def test_text_file_id(self):
        body = _build_async_body(text_file_id=42, voice_setting={"voice_id": "v1"})
        assert body["text_file_id"] == 42
        assert "text" not in body

    def test_all_optional(self):
        body = _build_async_body(
            text="hi",
            model="speech-2.8-hd",
            voice_setting={"voice_id": "v1"},
            audio_setting={"format": "mp3"},
            language_boost="en",
            voice_modify={"pitch": 1},
            pronunciation_dict={"k": "v"},
        )
        assert body["audio_setting"] == {"format": "mp3"}
        assert body["language_boost"] == "en"
        assert body["voice_modify"] == {"pitch": 1}
        assert body["pronunciation_dict"] == {"k": "v"}


class TestWsUrl:
    """Tests for _ws_url."""

    def test_https_to_wss(self):
        assert _ws_url("https://api.minimax.io") == "wss://api.minimax.io/ws/v1/t2a_v2"

    def test_with_port(self):
        assert _ws_url("https://api.minimax.io:8443") == "wss://api.minimax.io:8443/ws/v1/t2a_v2"

    def test_fallback_host(self):
        # Scheme-only URL that has no hostname triggers fallback
        assert _ws_url("") == "wss://api.minimax.io/ws/v1/t2a_v2"


class TestBuildWsConfig:
    """Tests for _build_ws_config."""

    def test_minimal(self):
        cfg = _build_ws_config("speech-2.8-hd", voice_setting={"voice_id": "v1"})
        assert cfg["model"] == "speech-2.8-hd"
        assert cfg["voice_setting"] == {"voice_id": "v1"}
        assert "audio_setting" not in cfg

    def test_all_optional(self):
        cfg = _build_ws_config(
            "speech-2.8-hd",
            voice_setting={"voice_id": "v1"},
            audio_setting={"format": "mp3"},
            language_boost="en",
            voice_modify={"pitch": 1},
            pronunciation_dict={"k": "v"},
            timbre_weights=[{"w": 1.0}],
        )
        assert cfg["audio_setting"] == {"format": "mp3"}
        assert cfg["language_boost"] == "en"
        assert cfg["voice_modify"] == {"pitch": 1}
        assert cfg["pronunciation_dict"] == {"k": "v"}
        assert cfg["timbre_weights"] == [{"w": 1.0}]


class TestParseWsMessage:
    """Tests for _parse_ws_message."""

    def test_ok(self):
        msg = _parse_ws_message('{"event": "task_started", "base_resp": {"status_code": 0}}')
        assert msg["event"] == "task_started"

    def test_error_raises(self):
        raw = json.dumps({"event": "error", "base_resp": {"status_code": 1004, "status_msg": "auth fail"}})
        with pytest.raises(MiniMaxError):
            _parse_ws_message(raw)


class TestAudioResponseFromWsChunks:
    """Tests for _audio_response_from_ws_chunks."""

    def test_single_chunk(self):
        extra = {"audio_length": 500, "audio_sample_rate": 24000, "audio_size": 5, "audio_format": "mp3"}
        resp = _audio_response_from_ws_chunks([_SAMPLE_HEX], extra)
        assert isinstance(resp, AudioResponse)
        assert resp.data == _SAMPLE_BYTES
        assert resp.duration == 500.0
        assert resp.sample_rate == 24000
        assert resp.format == "mp3"

    def test_multiple_chunks(self):
        extra = {"audio_length": 1000, "audio_sample_rate": 24000, "audio_size": 10, "audio_format": "mp3"}
        resp = _audio_response_from_ws_chunks([_SAMPLE_HEX, _SAMPLE_HEX], extra)
        assert resp.data == _SAMPLE_BYTES + _SAMPLE_BYTES

    def test_empty_chunks(self):
        extra = {"audio_length": 0, "audio_sample_rate": 0, "audio_format": "mp3"}
        resp = _audio_response_from_ws_chunks([], extra)
        assert resp.data == b""
        assert resp.size == 0

    def test_defaults(self):
        """Verify defaults when extra_info is sparse."""
        resp = _audio_response_from_ws_chunks([_SAMPLE_HEX], {})
        assert resp.duration == 0.0
        assert resp.sample_rate == 0
        assert resp.format == "mp3"
        assert resp.size == len(_SAMPLE_BYTES)


# ── SSE helper tests ────────────────────────────────────────────────────────


class TestIterSseAudioChunks:
    """Tests for _iter_sse_audio_chunks (sync)."""

    def test_dict_chunks(self):
        chunks = [
            {"data": {"audio": _SAMPLE_HEX}},
            {"data": {"audio": ""}},  # empty — skipped
            {"data": {"audio": _SAMPLE_HEX}},
        ]
        result = list(_iter_sse_audio_chunks(iter(chunks)))
        assert result == [_SAMPLE_BYTES, _SAMPLE_BYTES]

    def test_string_chunks_with_sse_format(self):
        lines = [
            f"data: {json.dumps({'data': {'audio': _SAMPLE_HEX}})}",
            "",          # blank line — skipped
            ": comment",  # SSE comment — skipped
            "data: [DONE]",
        ]
        result = list(_iter_sse_audio_chunks(iter(lines)))
        assert result == [_SAMPLE_BYTES]

    def test_bytes_chunks(self):
        raw_line = f"data: {json.dumps({'data': {'audio': _SAMPLE_HEX}})}".encode("utf-8")
        result = list(_iter_sse_audio_chunks(iter([raw_line])))
        assert result == [_SAMPLE_BYTES]

    def test_invalid_json_skipped(self):
        result = list(_iter_sse_audio_chunks(iter(["not json"])))
        assert result == []

    def test_string_without_data_prefix(self):
        """A raw JSON string (no 'data:' prefix) should still be parsed."""
        raw = json.dumps({"data": {"audio": _SAMPLE_HEX}})
        result = list(_iter_sse_audio_chunks(iter([raw])))
        assert result == [_SAMPLE_BYTES]

    def test_done_terminates(self):
        lines = [
            f"data: [DONE]",
            f"data: {json.dumps({'data': {'audio': _SAMPLE_HEX}})}",
        ]
        result = list(_iter_sse_audio_chunks(iter(lines)))
        assert result == []


class TestAiterSseAudioChunks:
    """Tests for _aiter_sse_audio_chunks (async)."""

    @pytest.mark.asyncio
    async def test_dict_chunks(self):
        async def _aiter():
            yield {"data": {"audio": _SAMPLE_HEX}}
            yield {"data": {"audio": ""}}
            yield {"data": {"audio": _SAMPLE_HEX}}

        result = [chunk async for chunk in _aiter_sse_audio_chunks(_aiter())]
        assert result == [_SAMPLE_BYTES, _SAMPLE_BYTES]

    @pytest.mark.asyncio
    async def test_string_chunks_with_sse_format(self):
        async def _aiter():
            yield f"data: {json.dumps({'data': {'audio': _SAMPLE_HEX}})}"
            yield ""
            yield ": comment"
            yield "data: [DONE]"

        result = [chunk async for chunk in _aiter_sse_audio_chunks(_aiter())]
        assert result == [_SAMPLE_BYTES]

    @pytest.mark.asyncio
    async def test_bytes_chunks(self):
        async def _aiter():
            yield f"data: {json.dumps({'data': {'audio': _SAMPLE_HEX}})}".encode("utf-8")

        result = [chunk async for chunk in _aiter_sse_audio_chunks(_aiter())]
        assert result == [_SAMPLE_BYTES]

    @pytest.mark.asyncio
    async def test_invalid_json_skipped(self):
        async def _aiter():
            yield "not json"

        result = [chunk async for chunk in _aiter_sse_audio_chunks(_aiter())]
        assert result == []

    @pytest.mark.asyncio
    async def test_string_without_data_prefix(self):
        async def _aiter():
            yield json.dumps({"data": {"audio": _SAMPLE_HEX}})

        result = [chunk async for chunk in _aiter_sse_audio_chunks(_aiter())]
        assert result == [_SAMPLE_BYTES]

    @pytest.mark.asyncio
    async def test_done_terminates(self):
        async def _aiter():
            yield "data: [DONE]"
            yield f"data: {json.dumps({'data': {'audio': _SAMPLE_HEX}})}"

        result = [chunk async for chunk in _aiter_sse_audio_chunks(_aiter())]
        assert result == []


# ═══════════════════════════════════════════════════════════════════════════
# Sync Speech tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSpeechTts:
    """Tests for Speech.tts()."""

    def test_tts_returns_audio_response(self):
        speech, mock_http = _make_speech_resource()
        mock_http.request.return_value = _ok_resp({
            "data": {"audio": _SAMPLE_HEX},
            "extra_info": {
                "audio_length": 500,
                "audio_sample_rate": 24000,
                "audio_size": len(_SAMPLE_BYTES),
                "audio_format": "mp3",
            },
        })

        result = speech.tts("Hello", "speech-2.8-hd")

        assert isinstance(result, AudioResponse)
        assert result.data == _SAMPLE_BYTES
        assert result.duration == 500.0
        assert result.sample_rate == 24000
        assert result.format == "mp3"
        assert result.size == len(_SAMPLE_BYTES)

        mock_http.request.assert_called_once()
        call_args = mock_http.request.call_args
        assert call_args[0] == ("POST", "/v1/t2a_v2")
        body = call_args[1]["json"]
        assert body["text"] == "Hello"
        assert body["model"] == "speech-2.8-hd"
        assert body["stream"] is False

    def test_tts_with_all_optional_params(self):
        speech, mock_http = _make_speech_resource()
        mock_http.request.return_value = _ok_resp({
            "data": {"audio": _SAMPLE_HEX},
            "extra_info": {
                "audio_length": 500,
                "audio_sample_rate": 24000,
                "audio_size": len(_SAMPLE_BYTES),
                "audio_format": "mp3",
            },
        })

        result = speech.tts(
            "Hello",
            "speech-2.8-hd",
            voice_setting={"voice_id": "male-1"},
            audio_setting={"sample_rate": 24000, "format": "mp3"},
            language_boost="en",
            voice_modify={"pitch": 1},
            pronunciation_dict={"k": "v"},
            timbre_weights=[{"w": 1.0}],
            subtitle_enable=True,
            output_format="hex",
        )

        assert isinstance(result, AudioResponse)
        body = mock_http.request.call_args[1]["json"]
        assert body["voice_setting"] == {"voice_id": "male-1"}
        assert body["audio_setting"] == {"sample_rate": 24000, "format": "mp3"}
        assert body["language_boost"] == "en"
        assert body["voice_modify"] == {"pitch": 1}
        assert body["pronunciation_dict"] == {"k": "v"}
        assert body["timbre_weights"] == [{"w": 1.0}]
        assert body["subtitle_enable"] is True


class TestSpeechTtsStream:
    """Tests for Speech.tts_stream()."""

    def test_tts_stream_yields_bytes(self):
        speech, mock_http = _make_speech_resource()
        mock_http.stream_request.return_value = iter([
            {"data": {"audio": _SAMPLE_HEX}},
            {"data": {"audio": _SAMPLE_HEX}},
        ])

        result = list(speech.tts_stream("Hello", "speech-2.8-hd"))

        assert result == [_SAMPLE_BYTES, _SAMPLE_BYTES]
        mock_http.stream_request.assert_called_once()
        call_args = mock_http.stream_request.call_args
        assert call_args[0] == ("POST", "/v1/t2a_v2")
        body = call_args[1]["json"]
        assert body["stream"] is True


class TestSpeechAsyncCreate:
    """Tests for Speech.async_create()."""

    def test_async_create_returns_dict(self):
        speech, mock_http = _make_speech_resource()
        mock_http.request.return_value = _ok_resp({
            "task_id": "task-123",
            "file_id": "file-456",
            "task_token": "tok-789",
        })

        result = speech.async_create(
            text="Long text here",
            model="speech-2.8-hd",
            voice_setting={"voice_id": "v1"},
        )

        assert result["task_id"] == "task-123"
        assert result["file_id"] == "file-456"
        mock_http.request.assert_called_once()
        call_args = mock_http.request.call_args
        assert call_args[0] == ("POST", "/v1/t2a_async_v2")

    def test_async_create_with_all_params(self):
        speech, mock_http = _make_speech_resource()
        mock_http.request.return_value = _ok_resp({"task_id": "t1"})

        speech.async_create(
            text="text",
            model="speech-2.8-hd",
            text_file_id=42,
            voice_setting={"voice_id": "v1"},
            audio_setting={"format": "mp3"},
            language_boost="en",
            voice_modify={"pitch": 1},
            pronunciation_dict={"k": "v"},
        )

        body = mock_http.request.call_args[1]["json"]
        assert body["text"] == "text"
        assert body["text_file_id"] == 42


class TestSpeechAsyncQuery:
    """Tests for Speech.async_query()."""

    def test_async_query_returns_status(self):
        speech, mock_http = _make_speech_resource()
        mock_http.request.return_value = _ok_resp({
            "task_id": "task-123",
            "status": "Processing",
        })

        result = speech.async_query("task-123")

        assert result["status"] == "Processing"
        mock_http.request.assert_called_once_with(
            "GET",
            "/v1/query/t2a_async_query_v2",
            params={"task_id": "task-123"},
        )


class TestSpeechAsyncGenerate:
    """Tests for Speech.async_generate()."""

    @patch("minimax_sdk.resources.speech.poll_task")
    def test_async_generate_full_pipeline(self, mock_poll):
        speech, mock_http = _make_speech_resource()

        # Step 1: async_create returns task_id
        mock_http.request.return_value = _ok_resp({
            "task_id": "task-123",
            "file_id": "file-456",
        })

        # Step 2: poll_task returns success
        mock_poll.return_value = _ok_resp({
            "task_id": "task-123",
            "status": "Success",
            "file_id": "file-789",
        })

        # Step 3: files.retrieve returns FileInfo
        mock_file_info = MagicMock()
        mock_file_info.download_url = "https://cdn.minimax.io/audio.mp3"
        speech._client.files.retrieve.return_value = mock_file_info

        result = speech.async_generate(
            text="Long text",
            voice_setting={"voice_id": "v1"},
            poll_interval=1.0,
            poll_timeout=30.0,
        )

        assert isinstance(result, TaskResult)
        assert result.task_id == "task-123"
        assert result.status == "Success"
        assert result.file_id == "file-789"
        assert result.download_url == "https://cdn.minimax.io/audio.mp3"
        speech._client.files.retrieve.assert_called_once_with("file-789")

    @patch("minimax_sdk.resources.speech.poll_task")
    def test_async_generate_uses_default_poll_settings(self, mock_poll):
        speech, mock_http = _make_speech_resource()
        speech._client.poll_interval = 10.0
        speech._client.poll_timeout = 300.0

        mock_http.request.return_value = _ok_resp({"task_id": "t1"})
        mock_poll.return_value = _ok_resp({"status": "Success", "file_id": "f1"})
        mock_file_info = MagicMock()
        mock_file_info.download_url = "https://example.com/a.mp3"
        speech._client.files.retrieve.return_value = mock_file_info

        speech.async_generate(text="hello", voice_setting={"voice_id": "v1"})

        # Verify poll_task was called with default intervals
        _, kwargs = mock_poll.call_args
        assert kwargs["poll_interval"] == 10.0
        assert kwargs["poll_timeout"] == 300.0


class TestSpeechConnect:
    """Tests for Speech.connect()."""

    @patch("minimax_sdk.resources.speech.websockets.sync.client.connect")
    def test_connect_returns_speech_connection(self, mock_ws_connect):
        speech, mock_http = _make_speech_resource()

        # Mock websocket: returns task_started on first recv
        ws = MockWebSocket([_WS_TASK_STARTED])
        mock_ws_connect.return_value = ws

        conn = speech.connect(
            model="speech-2.8-hd",
            voice_setting={"voice_id": "v1"},
        )

        assert isinstance(conn, SpeechConnection)
        assert conn.session_id == "test-session"

        # Verify task_start was sent
        assert len(ws._sent) == 1
        assert ws._sent[0]["event"] == "task_start"
        assert ws._sent[0]["model"] == "speech-2.8-hd"

    @patch("minimax_sdk.resources.speech.websockets.sync.client.connect")
    def test_connect_raises_connection_error(self, mock_ws_connect):
        speech, mock_http = _make_speech_resource()
        mock_ws_connect.side_effect = Exception("Connection refused")

        with pytest.raises(ConnectionError, match="Failed to establish WebSocket"):
            speech.connect(model="speech-2.8-hd", voice_setting={"voice_id": "v1"})


# ═══════════════════════════════════════════════════════════════════════════
# SpeechConnection (sync) tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSpeechConnection:
    """Tests for SpeechConnection."""

    def _make_connection(self, extra_messages: list[dict]) -> tuple[SpeechConnection, MockWebSocket]:
        """Create a SpeechConnection with task_started + additional messages."""
        all_messages = [_WS_TASK_STARTED] + extra_messages
        ws = MockWebSocket(all_messages)
        conn = SpeechConnection(
            ws, "test-key", "speech-2.8-hd", {"voice_id": "v1"},
        )
        return conn, ws

    def test_send_returns_audio_response(self):
        conn, ws = self._make_connection([_WS_CHUNK_1, _WS_TASK_COMPLETE])

        result = conn.send("Hello")

        assert isinstance(result, AudioResponse)
        assert result.data == _SAMPLE_BYTES
        assert result.duration == 500.0
        assert result.sample_rate == 24000
        assert result.format == "mp3"

        # Verify task_continue was sent
        sent_continue = [m for m in ws._sent if m.get("event") == "task_continue"]
        assert len(sent_continue) == 1
        assert sent_continue[0]["text"] == "Hello"

    def test_send_multiple_chunks(self):
        conn, ws = self._make_connection([_WS_CHUNK_1, _WS_CHUNK_1, _WS_TASK_COMPLETE])

        result = conn.send("Hello world")

        assert result.data == _SAMPLE_BYTES + _SAMPLE_BYTES

    def test_send_when_closed_raises(self):
        conn, ws = self._make_connection([_WS_TASK_FINISHED])
        conn.close()

        with pytest.raises(ConnectionError, match="already closed"):
            conn.send("Hello")

    def test_send_ws_send_fails(self):
        """If ws.send raises, ConnectionError is raised."""
        conn, ws = self._make_connection([])
        ws.send = MagicMock(side_effect=Exception("network down"))
        conn._closed = False  # ensure not closed

        with pytest.raises(ConnectionError, match="WebSocket send failed"):
            conn.send("Hello")

    def test_send_task_failed_raises(self):
        failed_msg = {
            "event": "task_failed",
            "message": "synthesis failed",
            "base_resp": {"status_code": 0},
            "trace_id": "tr-1",
        }
        conn, ws = self._make_connection([failed_msg])

        with pytest.raises(MiniMaxError, match="synthesis failed"):
            conn.send("Hello")

    def test_send_connection_closed_unexpectedly(self):
        """If the WebSocket drops during recv, ConnectionError is raised."""
        # No messages after task_continue -> will hit ConnectionClosed
        conn, ws = self._make_connection([])

        with pytest.raises(ConnectionError, match="WebSocket connection closed unexpectedly"):
            conn.send("Hello")

    def test_send_stream_yields_bytes(self):
        conn, ws = self._make_connection([_WS_CHUNK_1, _WS_TASK_COMPLETE])

        result = list(conn.send_stream("Hello"))

        assert result == [_SAMPLE_BYTES]

    def test_send_stream_multiple_chunks(self):
        conn, ws = self._make_connection([_WS_CHUNK_1, _WS_CHUNK_1, _WS_TASK_COMPLETE])

        result = list(conn.send_stream("Hello world"))

        assert result == [_SAMPLE_BYTES, _SAMPLE_BYTES]

    def test_send_stream_when_closed_raises(self):
        conn, ws = self._make_connection([_WS_TASK_FINISHED])
        conn.close()

        with pytest.raises(ConnectionError, match="already closed"):
            list(conn.send_stream("Hello"))

    def test_send_stream_ws_send_fails(self):
        conn, ws = self._make_connection([])
        ws.send = MagicMock(side_effect=Exception("network down"))
        conn._closed = False

        with pytest.raises(ConnectionError, match="WebSocket send failed"):
            list(conn.send_stream("Hello"))

    def test_send_stream_task_failed_raises(self):
        failed_msg = {
            "event": "task_failed",
            "message": "stream failed",
            "base_resp": {"status_code": 0},
        }
        conn, ws = self._make_connection([failed_msg])

        with pytest.raises(MiniMaxError, match="stream failed"):
            list(conn.send_stream("Hello"))

    def test_send_stream_connection_closed_unexpectedly(self):
        conn, ws = self._make_connection([])

        with pytest.raises(ConnectionError, match="WebSocket connection closed unexpectedly"):
            list(conn.send_stream("Hello"))

    def test_close(self):
        conn, ws = self._make_connection([_WS_TASK_FINISHED])

        conn.close()

        assert conn._closed is True
        # Verify task_finish was sent
        sent_finish = [m for m in ws._sent if m.get("event") == "task_finish"]
        assert len(sent_finish) == 1

    def test_close_idempotent(self):
        conn, ws = self._make_connection([_WS_TASK_FINISHED])
        conn.close()
        conn.close()  # Second call should be a no-op
        assert conn._closed is True

    def test_close_handles_task_failed(self):
        """Close should not raise if server responds with task_failed."""
        failed_msg = {"event": "task_failed", "base_resp": {"status_code": 0}}
        conn, ws = self._make_connection([failed_msg])
        conn.close()  # Should not raise
        assert conn._closed is True

    def test_close_handles_connection_already_gone(self):
        """Close should not raise if the connection is already dropped."""
        conn, ws = self._make_connection([])
        # No messages -> recv raises ConnectionClosed, which should be caught
        conn.close()
        assert conn._closed is True

    def test_close_handles_ws_close_exception(self):
        """Close should swallow exceptions from ws.close()."""
        conn, ws = self._make_connection([_WS_TASK_FINISHED])
        ws.close = MagicMock(side_effect=Exception("close failed"))
        conn.close()
        assert conn._closed is True

    def test_context_manager(self):
        all_messages = [_WS_TASK_STARTED, _WS_CHUNK_1, _WS_TASK_COMPLETE, _WS_TASK_FINISHED]
        ws = MockWebSocket(all_messages)

        with SpeechConnection(ws, "test-key", "speech-2.8-hd", {"voice_id": "v1"}) as conn:
            result = conn.send("Hello")
            assert isinstance(result, AudioResponse)

        assert conn._closed is True

    def test_start_receives_bytes(self):
        """_start should handle bytes messages from the WebSocket."""
        ws_messages = [_WS_TASK_STARTED]
        ws = MockWebSocket(ws_messages)
        # Override recv to return bytes
        original_messages = [json.dumps(_WS_TASK_STARTED).encode("utf-8")]
        ws._messages = original_messages

        conn = SpeechConnection(ws, "test-key", "speech-2.8-hd", {"voice_id": "v1"})
        assert conn.session_id == "test-session"

    def test_start_task_failed(self):
        """_start should raise MiniMaxError if task_failed is received."""
        failed = {"event": "task_failed", "message": "start failed", "base_resp": {"status_code": 0}, "trace_id": "tr-1"}
        ws = MockWebSocket([failed])

        with pytest.raises(MiniMaxError, match="start failed"):
            SpeechConnection(ws, "test-key", "speech-2.8-hd", {"voice_id": "v1"})

    def test_send_receives_bytes_messages(self):
        """send() should handle bytes messages from the WebSocket."""
        conn, ws = self._make_connection([])
        # Override _messages with bytes
        ws._messages = [
            json.dumps(_WS_CHUNK_1).encode("utf-8"),
            json.dumps(_WS_TASK_COMPLETE).encode("utf-8"),
        ]
        conn._closed = False

        result = conn.send("Hello")
        assert isinstance(result, AudioResponse)
        assert result.data == _SAMPLE_BYTES

    def test_send_stream_receives_bytes_messages(self):
        """send_stream() should handle bytes messages from the WebSocket."""
        conn, ws = self._make_connection([])
        ws._messages = [
            json.dumps(_WS_CHUNK_1).encode("utf-8"),
            json.dumps(_WS_TASK_COMPLETE).encode("utf-8"),
        ]
        conn._closed = False

        result = list(conn.send_stream("Hello"))
        assert result == [_SAMPLE_BYTES]

    def test_close_receives_bytes_messages(self):
        """close() should handle bytes messages from the WebSocket."""
        conn, ws = self._make_connection([])
        ws._messages = [json.dumps(_WS_TASK_FINISHED).encode("utf-8")]
        conn._closed = False

        conn.close()
        assert conn._closed is True

    def test_send_continued_with_extra_info_only_on_last(self):
        """extra_info is captured from the last chunk that has it."""
        chunk_no_extra = {
            "event": "task_continued",
            "data": {"audio": _SAMPLE_HEX},
            "base_resp": {"status_code": 0},
        }
        chunk_with_extra = {
            "event": "task_continued",
            "data": {"audio": _SAMPLE_HEX},
            "extra_info": {
                "audio_length": 999,
                "audio_sample_rate": 44100,
                "audio_size": 10,
                "audio_format": "wav",
            },
            "base_resp": {"status_code": 0},
        }
        complete_with_extra = {
            "event": "task_complete",
            "extra_info": {
                "audio_length": 1000,
                "audio_sample_rate": 48000,
                "audio_size": 10,
                "audio_format": "flac",
            },
            "base_resp": {"status_code": 0},
        }
        conn, ws = self._make_connection([chunk_no_extra, chunk_with_extra, complete_with_extra])

        result = conn.send("Hello")
        # task_complete extra_info should be used last
        assert result.format == "flac"
        assert result.sample_rate == 48000

    def test_send_stream_skips_empty_audio(self):
        """send_stream() skips chunks with empty audio."""
        empty_chunk = {
            "event": "task_continued",
            "data": {"audio": ""},
            "base_resp": {"status_code": 0},
        }
        conn, ws = self._make_connection([empty_chunk, _WS_CHUNK_1, _WS_TASK_COMPLETE])

        result = list(conn.send_stream("Hello"))
        assert result == [_SAMPLE_BYTES]

    def test_constructor_with_all_optional_params(self):
        """SpeechConnection constructor accepts all optional config params."""
        ws = MockWebSocket([_WS_TASK_STARTED])
        conn = SpeechConnection(
            ws, "test-key", "speech-2.8-hd", {"voice_id": "v1"},
            audio_setting={"format": "mp3"},
            language_boost="en",
            voice_modify={"pitch": 1},
            pronunciation_dict={"k": "v"},
            timbre_weights=[{"w": 1.0}],
        )
        assert conn.session_id == "test-session"
        # Verify config was built correctly
        assert conn._config["audio_setting"] == {"format": "mp3"}


# ═══════════════════════════════════════════════════════════════════════════
# Async Speech tests
# ═══════════════════════════════════════════════════════════════════════════


class TestAsyncSpeechTts:
    """Tests for AsyncSpeech.tts()."""

    @pytest.mark.asyncio
    async def test_tts_returns_audio_response(self):
        speech, mock_http = _make_async_speech_resource()
        mock_http.request.return_value = _ok_resp({
            "data": {"audio": _SAMPLE_HEX},
            "extra_info": {
                "audio_length": 500,
                "audio_sample_rate": 24000,
                "audio_size": len(_SAMPLE_BYTES),
                "audio_format": "mp3",
            },
        })

        result = await speech.tts("Hello", "speech-2.8-hd")

        assert isinstance(result, AudioResponse)
        assert result.data == _SAMPLE_BYTES
        assert result.duration == 500.0
        mock_http.request.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_tts_with_all_optional_params(self):
        speech, mock_http = _make_async_speech_resource()
        mock_http.request.return_value = _ok_resp({
            "data": {"audio": _SAMPLE_HEX},
            "extra_info": {
                "audio_length": 500,
                "audio_sample_rate": 24000,
                "audio_size": len(_SAMPLE_BYTES),
                "audio_format": "mp3",
            },
        })

        await speech.tts(
            "Hello",
            "speech-2.8-hd",
            voice_setting={"voice_id": "male-1"},
            audio_setting={"sample_rate": 24000},
            language_boost="en",
            voice_modify={"pitch": 1},
            pronunciation_dict={"k": "v"},
            timbre_weights=[{"w": 1.0}],
            subtitle_enable=True,
            output_format="hex",
        )

        body = mock_http.request.call_args[1]["json"]
        assert body["voice_setting"] == {"voice_id": "male-1"}
        assert body["subtitle_enable"] is True


class TestAsyncSpeechTtsStream:
    """Tests for AsyncSpeech.tts_stream()."""

    @pytest.mark.asyncio
    async def test_tts_stream_yields_bytes(self):
        speech, mock_http = _make_async_speech_resource()

        async def _mock_aiter():
            yield {"data": {"audio": _SAMPLE_HEX}}
            yield {"data": {"audio": _SAMPLE_HEX}}

        # stream_request is called without await, so it must be a regular
        # callable that returns an async iterable.
        mock_http.stream_request = MagicMock(return_value=_mock_aiter())

        result = [chunk async for chunk in speech.tts_stream("Hello", "speech-2.8-hd")]

        assert result == [_SAMPLE_BYTES, _SAMPLE_BYTES]


class TestAsyncSpeechAsyncCreate:
    """Tests for AsyncSpeech.async_create()."""

    @pytest.mark.asyncio
    async def test_async_create_returns_dict(self):
        speech, mock_http = _make_async_speech_resource()
        mock_http.request.return_value = _ok_resp({
            "task_id": "task-123",
            "file_id": "file-456",
        })

        result = await speech.async_create(
            text="Long text",
            voice_setting={"voice_id": "v1"},
        )

        assert result["task_id"] == "task-123"
        mock_http.request.assert_awaited_once()
        call_args = mock_http.request.call_args
        assert call_args[0] == ("POST", "/v1/t2a_async_v2")


class TestAsyncSpeechAsyncQuery:
    """Tests for AsyncSpeech.async_query()."""

    @pytest.mark.asyncio
    async def test_async_query_returns_status(self):
        speech, mock_http = _make_async_speech_resource()
        mock_http.request.return_value = _ok_resp({
            "task_id": "task-123",
            "status": "Processing",
        })

        result = await speech.async_query("task-123")

        assert result["status"] == "Processing"
        mock_http.request.assert_awaited_once_with(
            "GET",
            "/v1/query/t2a_async_query_v2",
            params={"task_id": "task-123"},
        )


class TestAsyncSpeechAsyncGenerate:
    """Tests for AsyncSpeech.async_generate()."""

    @pytest.mark.asyncio
    @patch("minimax_sdk.resources.speech.async_poll_task")
    async def test_async_generate_full_pipeline(self, mock_poll):
        speech, mock_http = _make_async_speech_resource()

        # async_create
        mock_http.request.return_value = _ok_resp({
            "task_id": "task-123",
            "file_id": "file-456",
        })

        # poll
        mock_poll.return_value = _ok_resp({
            "status": "Success",
            "file_id": "file-789",
        })

        # files.retrieve
        mock_file_info = MagicMock()
        mock_file_info.download_url = "https://cdn.minimax.io/audio.mp3"
        speech._client.files.retrieve.return_value = mock_file_info

        result = await speech.async_generate(
            text="Long text",
            voice_setting={"voice_id": "v1"},
            poll_interval=1.0,
            poll_timeout=30.0,
        )

        assert isinstance(result, TaskResult)
        assert result.task_id == "task-123"
        assert result.status == "Success"
        assert result.download_url == "https://cdn.minimax.io/audio.mp3"

    @pytest.mark.asyncio
    @patch("minimax_sdk.resources.speech.async_poll_task")
    async def test_async_generate_uses_default_poll_settings(self, mock_poll):
        speech, mock_http = _make_async_speech_resource()
        speech._client.poll_interval = 10.0
        speech._client.poll_timeout = 300.0

        mock_http.request.return_value = _ok_resp({"task_id": "t1"})
        mock_poll.return_value = _ok_resp({"status": "Success", "file_id": "f1"})
        mock_file_info = MagicMock()
        mock_file_info.download_url = "https://example.com/a.mp3"
        speech._client.files.retrieve.return_value = mock_file_info

        await speech.async_generate(text="hello", voice_setting={"voice_id": "v1"})

        _, kwargs = mock_poll.call_args
        assert kwargs["poll_interval"] == 10.0
        assert kwargs["poll_timeout"] == 300.0


class TestAsyncSpeechConnect:
    """Tests for AsyncSpeech.connect()."""

    @pytest.mark.asyncio
    @patch("minimax_sdk.resources.speech.websockets.asyncio.client.connect", new_callable=AsyncMock)
    async def test_connect_returns_async_speech_connection(self, mock_ws_connect):
        speech, mock_http = _make_async_speech_resource()

        ws = MockAsyncWebSocket([_WS_TASK_STARTED])
        mock_ws_connect.return_value = ws

        conn = await speech.connect(
            model="speech-2.8-hd",
            voice_setting={"voice_id": "v1"},
        )

        assert isinstance(conn, AsyncSpeechConnection)
        assert conn.session_id == "test-session"

    @pytest.mark.asyncio
    @patch("minimax_sdk.resources.speech.websockets.asyncio.client.connect", new_callable=AsyncMock)
    async def test_connect_raises_connection_error(self, mock_ws_connect):
        speech, mock_http = _make_async_speech_resource()
        mock_ws_connect.side_effect = Exception("Connection refused")

        with pytest.raises(ConnectionError, match="Failed to establish WebSocket"):
            await speech.connect(model="speech-2.8-hd", voice_setting={"voice_id": "v1"})


# ═══════════════════════════════════════════════════════════════════════════
# AsyncSpeechConnection tests
# ═══════════════════════════════════════════════════════════════════════════


class TestAsyncSpeechConnection:
    """Tests for AsyncSpeechConnection."""

    async def _make_connection(self, extra_messages: list[dict]) -> tuple[AsyncSpeechConnection, MockAsyncWebSocket]:
        """Create an AsyncSpeechConnection with task_started + additional messages."""
        all_messages = [_WS_TASK_STARTED] + extra_messages
        ws = MockAsyncWebSocket(all_messages)
        conn = AsyncSpeechConnection(
            ws, "test-key", "speech-2.8-hd", {"voice_id": "v1"},
        )
        await conn._start()
        return conn, ws

    @pytest.mark.asyncio
    async def test_send_returns_audio_response(self):
        conn, ws = await self._make_connection([_WS_CHUNK_1, _WS_TASK_COMPLETE])

        result = await conn.send("Hello")

        assert isinstance(result, AudioResponse)
        assert result.data == _SAMPLE_BYTES
        assert result.duration == 500.0

    @pytest.mark.asyncio
    async def test_send_multiple_chunks(self):
        conn, ws = await self._make_connection([_WS_CHUNK_1, _WS_CHUNK_1, _WS_TASK_COMPLETE])

        result = await conn.send("Hello world")

        assert result.data == _SAMPLE_BYTES + _SAMPLE_BYTES

    @pytest.mark.asyncio
    async def test_send_when_closed_raises(self):
        conn, ws = await self._make_connection([_WS_TASK_FINISHED])
        await conn.close()

        with pytest.raises(ConnectionError, match="already closed"):
            await conn.send("Hello")

    @pytest.mark.asyncio
    async def test_send_ws_send_fails(self):
        conn, ws = await self._make_connection([])
        async def _fail(*a, **kw):
            raise Exception("network down")
        ws.send = _fail
        conn._closed = False

        with pytest.raises(ConnectionError, match="WebSocket send failed"):
            await conn.send("Hello")

    @pytest.mark.asyncio
    async def test_send_task_failed_raises(self):
        failed_msg = {
            "event": "task_failed",
            "message": "synthesis failed",
            "base_resp": {"status_code": 0},
        }
        conn, ws = await self._make_connection([failed_msg])

        with pytest.raises(MiniMaxError, match="synthesis failed"):
            await conn.send("Hello")

    @pytest.mark.asyncio
    async def test_send_connection_closed_unexpectedly(self):
        conn, ws = await self._make_connection([])

        with pytest.raises(ConnectionError, match="WebSocket connection closed unexpectedly"):
            await conn.send("Hello")

    @pytest.mark.asyncio
    async def test_send_stream_yields_bytes(self):
        conn, ws = await self._make_connection([_WS_CHUNK_1, _WS_TASK_COMPLETE])

        result = [chunk async for chunk in conn.send_stream("Hello")]

        assert result == [_SAMPLE_BYTES]

    @pytest.mark.asyncio
    async def test_send_stream_when_closed_raises(self):
        conn, ws = await self._make_connection([_WS_TASK_FINISHED])
        await conn.close()

        with pytest.raises(ConnectionError, match="already closed"):
            async for _ in conn.send_stream("Hello"):
                pass

    @pytest.mark.asyncio
    async def test_send_stream_ws_send_fails(self):
        conn, ws = await self._make_connection([])
        async def _fail(*a, **kw):
            raise Exception("network down")
        ws.send = _fail
        conn._closed = False

        with pytest.raises(ConnectionError, match="WebSocket send failed"):
            async for _ in conn.send_stream("Hello"):
                pass

    @pytest.mark.asyncio
    async def test_send_stream_task_failed_raises(self):
        failed_msg = {
            "event": "task_failed",
            "message": "stream failed",
            "base_resp": {"status_code": 0},
        }
        conn, ws = await self._make_connection([failed_msg])

        with pytest.raises(MiniMaxError, match="stream failed"):
            async for _ in conn.send_stream("Hello"):
                pass

    @pytest.mark.asyncio
    async def test_send_stream_connection_closed_unexpectedly(self):
        conn, ws = await self._make_connection([])

        with pytest.raises(ConnectionError, match="WebSocket connection closed unexpectedly"):
            async for _ in conn.send_stream("Hello"):
                pass

    @pytest.mark.asyncio
    async def test_close(self):
        conn, ws = await self._make_connection([_WS_TASK_FINISHED])

        await conn.close()

        assert conn._closed is True
        sent_finish = [m for m in ws._sent if m.get("event") == "task_finish"]
        assert len(sent_finish) == 1

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        conn, ws = await self._make_connection([_WS_TASK_FINISHED])
        await conn.close()
        await conn.close()
        assert conn._closed is True

    @pytest.mark.asyncio
    async def test_close_handles_task_failed(self):
        failed_msg = {"event": "task_failed", "base_resp": {"status_code": 0}}
        conn, ws = await self._make_connection([failed_msg])
        await conn.close()
        assert conn._closed is True

    @pytest.mark.asyncio
    async def test_close_handles_connection_already_gone(self):
        conn, ws = await self._make_connection([])
        await conn.close()
        assert conn._closed is True

    @pytest.mark.asyncio
    async def test_close_handles_ws_close_exception(self):
        conn, ws = await self._make_connection([_WS_TASK_FINISHED])
        async def _fail():
            raise Exception("close failed")
        ws.close = _fail
        await conn.close()
        assert conn._closed is True

    @pytest.mark.asyncio
    async def test_context_manager(self):
        all_messages = [_WS_TASK_STARTED, _WS_CHUNK_1, _WS_TASK_COMPLETE, _WS_TASK_FINISHED]
        ws = MockAsyncWebSocket(all_messages)
        conn = AsyncSpeechConnection(ws, "test-key", "speech-2.8-hd", {"voice_id": "v1"})
        await conn._start()

        async with conn:
            result = await conn.send("Hello")
            assert isinstance(result, AudioResponse)

        assert conn._closed is True

    @pytest.mark.asyncio
    async def test_start_receives_bytes(self):
        ws = MockAsyncWebSocket([])
        ws._messages = [json.dumps(_WS_TASK_STARTED).encode("utf-8")]
        conn = AsyncSpeechConnection(ws, "test-key", "speech-2.8-hd", {"voice_id": "v1"})
        await conn._start()
        assert conn.session_id == "test-session"

    @pytest.mark.asyncio
    async def test_start_task_failed(self):
        failed = {"event": "task_failed", "message": "start failed", "base_resp": {"status_code": 0}, "trace_id": "tr-1"}
        ws = MockAsyncWebSocket([failed])
        conn = AsyncSpeechConnection(ws, "test-key", "speech-2.8-hd", {"voice_id": "v1"})

        with pytest.raises(MiniMaxError, match="start failed"):
            await conn._start()

    @pytest.mark.asyncio
    async def test_send_receives_bytes_messages(self):
        conn, ws = await self._make_connection([])
        ws._messages = [
            json.dumps(_WS_CHUNK_1).encode("utf-8"),
            json.dumps(_WS_TASK_COMPLETE).encode("utf-8"),
        ]
        conn._closed = False

        result = await conn.send("Hello")
        assert result.data == _SAMPLE_BYTES

    @pytest.mark.asyncio
    async def test_send_stream_receives_bytes_messages(self):
        conn, ws = await self._make_connection([])
        ws._messages = [
            json.dumps(_WS_CHUNK_1).encode("utf-8"),
            json.dumps(_WS_TASK_COMPLETE).encode("utf-8"),
        ]
        conn._closed = False

        result = [chunk async for chunk in conn.send_stream("Hello")]
        assert result == [_SAMPLE_BYTES]

    @pytest.mark.asyncio
    async def test_close_receives_bytes_messages(self):
        conn, ws = await self._make_connection([])
        ws._messages = [json.dumps(_WS_TASK_FINISHED).encode("utf-8")]
        conn._closed = False

        await conn.close()
        assert conn._closed is True

    @pytest.mark.asyncio
    async def test_send_continued_with_extra_info_updates(self):
        chunk_no_extra = {
            "event": "task_continued",
            "data": {"audio": _SAMPLE_HEX},
            "base_resp": {"status_code": 0},
        }
        complete_with_extra = {
            "event": "task_complete",
            "extra_info": {
                "audio_length": 1000,
                "audio_sample_rate": 48000,
                "audio_size": 10,
                "audio_format": "flac",
            },
            "base_resp": {"status_code": 0},
        }
        conn, ws = await self._make_connection([chunk_no_extra, complete_with_extra])

        result = await conn.send("Hello")
        assert result.format == "flac"

    @pytest.mark.asyncio
    async def test_send_stream_skips_empty_audio(self):
        empty_chunk = {
            "event": "task_continued",
            "data": {"audio": ""},
            "base_resp": {"status_code": 0},
        }
        conn, ws = await self._make_connection([empty_chunk, _WS_CHUNK_1, _WS_TASK_COMPLETE])

        result = [chunk async for chunk in conn.send_stream("Hello")]
        assert result == [_SAMPLE_BYTES]

    @pytest.mark.asyncio
    async def test_constructor_with_all_optional_params(self):
        ws = MockAsyncWebSocket([_WS_TASK_STARTED])
        conn = AsyncSpeechConnection(
            ws, "test-key", "speech-2.8-hd", {"voice_id": "v1"},
            audio_setting={"format": "mp3"},
            language_boost="en",
            voice_modify={"pitch": 1},
            pronunciation_dict={"k": "v"},
            timbre_weights=[{"w": 1.0}],
        )
        await conn._start()
        assert conn.session_id == "test-session"
        assert conn._config["audio_setting"] == {"format": "mp3"}

    @pytest.mark.asyncio
    async def test_send_stream_multiple_chunks(self):
        conn, ws = await self._make_connection([_WS_CHUNK_1, _WS_CHUNK_1, _WS_TASK_COMPLETE])

        result = [chunk async for chunk in conn.send_stream("Hello")]
        assert result == [_SAMPLE_BYTES, _SAMPLE_BYTES]
