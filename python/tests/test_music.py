"""Tests for the Music resource."""

from __future__ import annotations

from unittest.mock import MagicMock

from minimax_sdk._audio import AudioResponse
from minimax_sdk.resources.music import Music
from minimax_sdk.types.music import LyricsResult


# ── Helpers ──────────────────────────────────────────────────────────────────


def _ok_resp(payload: dict) -> dict:
    """Wrap a payload in a successful API response envelope."""
    return {"base_resp": {"status_code": 0, "status_msg": "success"}, **payload}


def _make_music_resource() -> tuple[Music, MagicMock]:
    """Create a Music resource with mocked _http.

    Music.generate() and Music.generate_lyrics() call self._http.request().
    """
    mock_http = MagicMock()
    mock_client = MagicMock()
    music = Music(mock_http, client=mock_client)
    return music, mock_http


# Some sample hex-encoded audio (b"music" -> hex "6d75736963")
_SAMPLE_HEX = "6d75736963"
_SAMPLE_BYTES = bytes.fromhex(_SAMPLE_HEX)


# ── Tests ────────────────────────────────────────────────────────────────────


class TestMusicGenerate:
    """Tests for music.generate()."""

    def test_generate_returns_audio_response_with_decoded_audio(self):
        """music.generate() decodes hex audio and returns AudioResponse."""
        music, mock_client = _make_music_resource()
        mock_client.request.return_value = _ok_resp({
            "data": {"audio": _SAMPLE_HEX},
            "extra_info": {
                "music_duration": 30000.0,
                "music_sample_rate": 44100,
                "music_size": len(_SAMPLE_BYTES),
                "audio_format": "mp3",
            },
        })

        result = music.generate(
            model="music-2.5+",
            prompt="upbeat electronic dance music",
            lyrics="la la la",
        )

        assert isinstance(result, AudioResponse)
        assert result.data == _SAMPLE_BYTES
        assert result.duration == 30000.0
        assert result.sample_rate == 44100
        assert result.format == "mp3"
        assert result.size == len(_SAMPLE_BYTES)

        # Verify request body
        mock_client.request.assert_called_once()
        call_args = mock_client.request.call_args
        assert call_args[0] == ("POST", "/v1/music_generation")
        body = call_args[1]["json"]
        assert body["model"] == "music-2.5+"
        assert body["prompt"] == "upbeat electronic dance music"
        assert body["lyrics"] == "la la la"
        assert body["stream"] is False


class TestMusicGenerateLyrics:
    """Tests for music.generate_lyrics()."""

    def test_generate_lyrics_returns_lyrics_result(self):
        """music.generate_lyrics() returns a LyricsResult with title, tags, and lyrics."""
        music, mock_client = _make_music_resource()
        mock_client.request.return_value = _ok_resp({
            "data": {
                "song_title": "Midnight Dreams",
                "style_tags": "pop, electronic, dreamy",
                "lyrics": "[Verse 1]\nUnder the stars tonight\n[Chorus]\nMidnight dreams...",
            },
        })

        result = music.generate_lyrics(
            mode="write_full_song",
            prompt="a dreamy pop song about nighttime",
        )

        assert isinstance(result, LyricsResult)
        assert result.song_title == "Midnight Dreams"
        assert result.style_tags == "pop, electronic, dreamy"
        assert "Midnight dreams" in result.lyrics

        # Verify request body
        call_args = mock_client.request.call_args
        assert call_args[0] == ("POST", "/v1/lyrics_generation")
        body = call_args[1]["json"]
        assert body["mode"] == "write_full_song"
        assert body["prompt"] == "a dreamy pop song about nighttime"

    def test_generate_lyrics_with_mode_edit(self):
        """music.generate_lyrics() with mode='edit' includes existing lyrics in the body."""
        music, mock_client = _make_music_resource()
        mock_client.request.return_value = _ok_resp({
            "data": {
                "song_title": "Revised Song",
                "style_tags": "rock",
                "lyrics": "[Verse 1]\nRevised lyrics here\n[Chorus]\nNew chorus...",
            },
        })

        existing_lyrics = "[Verse 1]\nOld lyrics\n[Chorus]\nOld chorus"

        result = music.generate_lyrics(
            mode="edit",
            lyrics=existing_lyrics,
            prompt="make it more energetic",
            title="Revised Song",
        )

        assert isinstance(result, LyricsResult)
        assert result.song_title == "Revised Song"
        assert result.style_tags == "rock"

        # Verify the edit mode body includes existing lyrics
        body = mock_client.request.call_args[1]["json"]
        assert body["mode"] == "edit"
        assert body["lyrics"] == existing_lyrics
        assert body["prompt"] == "make it more energetic"
        assert body["title"] == "Revised Song"


# ── _build_music_body / _build_audio_response_from_music coverage ───────────

from minimax_sdk.resources.music import (
    _build_audio_response_from_music,
    _build_music_body,
    _parse_sse_line,
)


class TestBuildMusicBody:
    """Cover optional branches in _build_music_body."""

    def test_with_audio_setting(self):
        body = _build_music_body(
            "music-2.5+",
            prompt="upbeat",
            lyrics="la la",
            stream=False,
            output_format="url",
            lyrics_optimizer=True,
            is_instrumental=False,
            audio_setting={"sample_rate": 44100, "bitrate": 320, "format": "mp3"},
        )
        assert body["audio_setting"] == {"sample_rate": 44100, "bitrate": 320, "format": "mp3"}
        assert body["prompt"] == "upbeat"
        assert body["lyrics"] == "la la"
        assert body["output_format"] == "url"


class TestBuildAudioResponseFromMusic:
    """Cover branches of _build_audio_response_from_music."""

    def test_url_mode_stores_url_as_bytes(self):
        """When audio field is a URL, it's stored as encoded bytes."""
        resp = {
            "data": {"audio": "https://cdn.minimax.io/music/track.mp3"},
            "extra_info": {
                "music_duration": 60000.0,
                "music_sample_rate": 44100,
                "music_size": 0,
                "audio_format": "mp3",
            },
        }
        result = _build_audio_response_from_music(resp)
        assert result.data == b"https://cdn.minimax.io/music/track.mp3"
        assert result.duration == 60000.0
        assert result.sample_rate == 44100

    def test_empty_audio_returns_empty_bytes(self):
        """When audio field is empty, data is empty bytes."""
        resp = {
            "data": {"audio": ""},
            "extra_info": {
                "music_duration": 0,
                "music_sample_rate": 0,
                "music_size": 0,
                "audio_format": "mp3",
            },
        }
        result = _build_audio_response_from_music(resp)
        assert result.data == b""
        assert result.size == 0

    def test_missing_extra_info(self):
        """When extra_info is missing entirely."""
        resp = {
            "data": {"audio": _SAMPLE_HEX},
        }
        result = _build_audio_response_from_music(resp)
        assert result.data == _SAMPLE_BYTES
        assert result.duration == 0.0
        assert result.sample_rate == 0
        assert result.format == "mp3"
        assert result.size == len(_SAMPLE_BYTES)


class TestParseSseLine:
    """Cover all branches of _parse_sse_line."""

    def test_empty_line(self):
        assert _parse_sse_line("") is None

    def test_comment_line(self):
        assert _parse_sse_line(": keep-alive") is None

    def test_done_sentinel(self):
        assert _parse_sse_line("data: [DONE]") is None

    def test_valid_json_data(self):
        result = _parse_sse_line('data: {"key": "value"}')
        assert result == {"key": "value"}

    def test_invalid_json_data(self):
        assert _parse_sse_line("data: not-json") is None

    def test_non_data_line(self):
        assert _parse_sse_line("event: something") is None


# ── Sync generate_stream ────────────────────────────────────────────────────

import json
from contextlib import contextmanager


class TestMusicGenerateStream:
    """Tests for music.generate_stream()."""

    def test_generate_stream_yields_decoded_audio_chunks(self):
        """generate_stream() yields decoded bytes from SSE events."""
        mock_http = MagicMock()
        mock_client = MagicMock()
        music = Music(mock_http, client=mock_client)

        chunk1_hex = "48454c4c4f"  # b"HELLO"
        chunk2_hex = "574f524c44"  # b"WORLD"
        sse_lines = [
            f'data: {json.dumps({"data": {"audio": chunk1_hex}})}',
            f'data: {json.dumps({"data": {"audio": chunk2_hex}})}',
            "data: [DONE]",
        ]

        mock_http.stream_request.return_value = iter(sse_lines)

        chunks = list(music.generate_stream(
            model="music-2.5+",
            prompt="upbeat electronic",
        ))

        assert len(chunks) == 2
        assert chunks[0] == bytes.fromhex(chunk1_hex)
        assert chunks[1] == bytes.fromhex(chunk2_hex)

    def test_generate_stream_skips_non_audio_events(self):
        """generate_stream() skips SSE events without audio data."""
        mock_http = MagicMock()
        mock_client = MagicMock()
        music = Music(mock_http, client=mock_client)

        chunk_hex = "48454c4c4f"
        sse_lines = [
            ": keep-alive",
            f'data: {json.dumps({"data": {"audio": ""}})}',
            f'data: {json.dumps({"data": {"audio": chunk_hex}})}',
            "",
            "data: [DONE]",
        ]

        mock_http.stream_request.return_value = iter(sse_lines)

        chunks = list(music.generate_stream(model="music-2.5+"))

        assert len(chunks) == 1
        assert chunks[0] == bytes.fromhex(chunk_hex)


class TestMusicGenerateWithUrl:
    """Test music.generate() with URL-formatted audio."""

    def test_generate_with_url_audio(self):
        """music.generate() when audio is a URL stores it as bytes."""
        music, mock_client = _make_music_resource()
        mock_client.request.return_value = _ok_resp({
            "data": {"audio": "https://cdn.minimax.io/music/track.mp3"},
            "extra_info": {
                "music_duration": 60000.0,
                "music_sample_rate": 44100,
                "music_size": 0,
                "audio_format": "mp3",
            },
        })

        result = music.generate(
            model="music-2.5+",
            prompt="chill vibes",
            output_format="url",
        )

        assert isinstance(result, AudioResponse)
        assert result.data == b"https://cdn.minimax.io/music/track.mp3"


# ── Async Tests ─────────────────────────────────────────────────────────────

from unittest.mock import AsyncMock

import pytest

from minimax_sdk.resources.music import AsyncMusic


def _make_async_music_resource() -> tuple[AsyncMusic, MagicMock]:
    """Create an AsyncMusic resource with mocked _http."""
    mock_http = AsyncMock()
    mock_client = AsyncMock()
    music = AsyncMusic(mock_http, client=mock_client)
    return music, mock_http


class TestAsyncMusicGenerate:
    """Tests for async music.generate()."""

    @pytest.mark.asyncio
    async def test_generate_returns_audio_response(self):
        """Async music.generate() returns AudioResponse."""
        music, mock_client = _make_async_music_resource()
        mock_client.request.return_value = _ok_resp({
            "data": {"audio": _SAMPLE_HEX},
            "extra_info": {
                "music_duration": 30000.0,
                "music_sample_rate": 44100,
                "music_size": len(_SAMPLE_BYTES),
                "audio_format": "mp3",
            },
        })

        result = await music.generate(
            model="music-2.5+",
            prompt="upbeat electronic",
            lyrics="la la la",
        )

        assert isinstance(result, AudioResponse)
        assert result.data == _SAMPLE_BYTES
        assert result.duration == 30000.0
        assert result.sample_rate == 44100

        mock_client.request.assert_awaited_once()
        body = mock_client.request.call_args[1]["json"]
        assert body["stream"] is False


class TestAsyncMusicGenerateLyrics:
    """Tests for async music.generate_lyrics()."""

    @pytest.mark.asyncio
    async def test_generate_lyrics_returns_lyrics_result(self):
        """Async music.generate_lyrics() returns LyricsResult."""
        music, mock_client = _make_async_music_resource()
        mock_client.request.return_value = _ok_resp({
            "data": {
                "song_title": "Async Dreams",
                "style_tags": "pop",
                "lyrics": "[Verse]\nAsync verse...",
            },
        })

        result = await music.generate_lyrics(
            mode="write_full_song",
            prompt="a pop song",
            title="Async Dreams",
        )

        assert isinstance(result, LyricsResult)
        assert result.song_title == "Async Dreams"
        mock_client.request.assert_awaited_once()
        body = mock_client.request.call_args[1]["json"]
        assert body["mode"] == "write_full_song"
        assert body["title"] == "Async Dreams"

    @pytest.mark.asyncio
    async def test_generate_lyrics_edit_mode(self):
        """Async music.generate_lyrics() edit mode includes lyrics."""
        music, mock_client = _make_async_music_resource()
        mock_client.request.return_value = _ok_resp({
            "data": {
                "song_title": "Edited",
                "style_tags": "rock",
                "lyrics": "[Verse]\nEdited...",
            },
        })

        result = await music.generate_lyrics(
            mode="edit",
            lyrics="[Verse]\nOld...",
            prompt="make it rock",
        )

        assert isinstance(result, LyricsResult)
        body = mock_client.request.call_args[1]["json"]
        assert body["mode"] == "edit"
        assert body["lyrics"] == "[Verse]\nOld..."


class TestAsyncMusicGenerateStream:
    """Tests for async music.generate_stream()."""

    @pytest.mark.asyncio
    async def test_generate_stream_yields_decoded_chunks(self):
        """Async generate_stream() yields decoded bytes from SSE events."""
        mock_http = AsyncMock()
        mock_client = MagicMock()
        music = AsyncMusic(mock_http, client=mock_client)

        chunk1_hex = "48454c4c4f"  # b"HELLO"
        chunk2_hex = "574f524c44"  # b"WORLD"
        sse_lines = [
            f'data: {json.dumps({"data": {"audio": chunk1_hex}})}',
            f'data: {json.dumps({"data": {"audio": chunk2_hex}})}',
            "data: [DONE]",
        ]

        async def mock_stream_request(*args, **kwargs):
            for line in sse_lines:
                yield line

        mock_http.stream_request = mock_stream_request

        chunks = []
        async for chunk in music.generate_stream(
            model="music-2.5+",
            prompt="upbeat",
        ):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0] == bytes.fromhex(chunk1_hex)
        assert chunks[1] == bytes.fromhex(chunk2_hex)
