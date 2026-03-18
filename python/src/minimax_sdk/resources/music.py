"""Music resource -- synchronous and asynchronous music & lyrics generation.

Provides both synchronous (:class:`Music`) and asynchronous (:class:`AsyncMusic`)
clients for the MiniMax Music Generation API (``POST /v1/music_generation``) and
Lyrics Generation API (``POST /v1/lyrics_generation``).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

from .._audio import AudioResponse, decode_hex_audio
from .._base import AsyncResource, SyncResource
from ..types.music import LyricsResult


def _build_music_body(
    model: str,
    *,
    prompt: str | None,
    lyrics: str | None,
    stream: bool,
    output_format: str | None,
    lyrics_optimizer: bool,
    is_instrumental: bool,
    audio_setting: dict | None,
) -> dict[str, Any]:
    """Build the JSON request body for music generation, excluding None values."""
    body: dict[str, Any] = {
        "model": model,
        "stream": stream,
        "lyrics_optimizer": lyrics_optimizer,
        "is_instrumental": is_instrumental,
    }

    if prompt is not None:
        body["prompt"] = prompt
    if lyrics is not None:
        body["lyrics"] = lyrics
    if output_format is not None:
        body["output_format"] = output_format
    if audio_setting is not None:
        body["audio_setting"] = audio_setting

    return body


def _build_audio_response_from_music(resp: dict[str, Any]) -> AudioResponse:
    """Build an :class:`AudioResponse` from a music generation API response.

    Music endpoints use ``extra_info`` field names that differ from speech:
    ``music_duration``, ``music_sample_rate``, ``music_channel``, ``bitrate``,
    and ``music_size``.
    """
    data_section = resp.get("data", {})
    extra_info = resp.get("extra_info", {})

    audio_raw: str = data_section.get("audio", "")

    # If the audio field looks like hex-encoded data, decode it.
    # If it's a URL (output_format="url"), store the URL bytes as a placeholder
    # so callers can detect and handle it.
    if audio_raw and not audio_raw.startswith(("http://", "https://")):
        audio_bytes = decode_hex_audio(audio_raw)
    elif audio_raw:
        # URL mode -- store the URL string encoded as bytes so AudioResponse
        # still holds something useful.  Callers who request output_format="url"
        # should read the URL from the raw response or decode this field.
        audio_bytes = audio_raw.encode("utf-8")
    else:
        audio_bytes = b""

    duration: float = float(extra_info.get("music_duration", 0))
    sample_rate: int = int(extra_info.get("music_sample_rate", 0))
    audio_format: str = extra_info.get("audio_format", "mp3")
    size: int = int(extra_info.get("music_size", 0) or len(audio_bytes))

    return AudioResponse(
        data=audio_bytes,
        duration=duration,
        sample_rate=sample_rate,
        format=audio_format,
        size=size,
    )


def _build_lyrics_body(
    mode: str,
    *,
    prompt: str | None,
    lyrics: str | None,
    title: str | None,
) -> dict[str, Any]:
    """Build the JSON request body for lyrics generation, excluding None values."""
    body: dict[str, Any] = {"mode": mode}

    if prompt is not None:
        body["prompt"] = prompt
    if lyrics is not None:
        body["lyrics"] = lyrics
    if title is not None:
        body["title"] = title

    return body


def _parse_lyrics_result(resp: dict[str, Any]) -> LyricsResult:
    """Parse a raw API response dict into a :class:`LyricsResult`."""
    data = resp.get("data", resp)

    return LyricsResult(
        song_title=data.get("song_title", ""),
        style_tags=data.get("style_tags", ""),
        lyrics=data.get("lyrics", ""),
    )


def _parse_sse_line(line: str) -> dict[str, Any] | None:
    """Extract JSON payload from a single SSE ``data:`` line.

    Returns ``None`` for non-data lines, keep-alive comments, or the
    ``[DONE]`` sentinel.
    """
    line = line.strip()
    if not line or line.startswith(":"):
        return None
    if line.startswith("data:"):
        payload = line[len("data:") :].strip()
        if payload == "[DONE]":
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None
    return None


# -- Sync ---------------------------------------------------------------------


class Music(SyncResource):
    """Synchronous music and lyrics generation resource."""

    def generate(
        self,
        model: str = "music-2.5+",
        *,
        prompt: str | None = None,
        lyrics: str | None = None,
        output_format: str = "url",
        lyrics_optimizer: bool = False,
        is_instrumental: bool = False,
        audio_setting: dict | None = None,
    ) -> AudioResponse:
        """Generate music from a text prompt and/or lyrics.

        Args:
            model: The model identifier (default ``"music-2.5+"``).
            prompt: A text description of the desired music style/mood.
            lyrics: Lyrics for the generated track.
            output_format: ``"url"`` (default) returns a download URL;
                ``"hex"`` returns hex-encoded audio data.
            lyrics_optimizer: Whether to let the API optimise the lyrics.
            is_instrumental: Generate an instrumental track (no vocals).
            audio_setting: Optional dict with keys like ``"sample_rate"``,
                ``"bitrate"``, ``"format"``.

        Returns:
            An :class:`AudioResponse` containing the generated audio data.
        """
        body = _build_music_body(
            model,
            prompt=prompt,
            lyrics=lyrics,
            stream=False,
            output_format=output_format,
            lyrics_optimizer=lyrics_optimizer,
            is_instrumental=is_instrumental,
            audio_setting=audio_setting,
        )

        resp = self._http.request("POST", "/v1/music_generation", json=body)
        return _build_audio_response_from_music(resp)

    def generate_stream(
        self,
        model: str = "music-2.5+",
        *,
        prompt: str | None = None,
        lyrics: str | None = None,
        lyrics_optimizer: bool = False,
        is_instrumental: bool = False,
        audio_setting: dict | None = None,
    ) -> Iterator[bytes]:
        """Generate music as a stream of decoded audio chunks.

        Streaming always uses ``output_format="hex"`` (API requirement).  Each
        yielded chunk is the decoded ``bytes`` from one SSE event.

        Args:
            model: The model identifier (default ``"music-2.5+"``).
            prompt: A text description of the desired music style/mood.
            lyrics: Lyrics for the generated track.
            lyrics_optimizer: Whether to let the API optimise the lyrics.
            is_instrumental: Generate an instrumental track (no vocals).
            audio_setting: Optional dict with keys like ``"sample_rate"``,
                ``"bitrate"``, ``"format"``.

        Yields:
            Decoded ``bytes`` chunks of audio data.
        """
        body = _build_music_body(
            model,
            prompt=prompt,
            lyrics=lyrics,
            stream=True,
            output_format="hex",
            lyrics_optimizer=lyrics_optimizer,
            is_instrumental=is_instrumental,
            audio_setting=audio_setting,
        )

        # Use the underlying httpx client directly for streaming.
        with self._http._client.stream(
            "POST",
            "/v1/music_generation",
            json=body,
        ) as response:
            for line in response.iter_lines():
                event = _parse_sse_line(line)
                if event is None:
                    continue
                data_section = event.get("data", {})
                hex_audio = data_section.get("audio", "")
                if hex_audio:
                    yield decode_hex_audio(hex_audio)

    def generate_lyrics(
        self,
        mode: str,
        *,
        prompt: str | None = None,
        lyrics: str | None = None,
        title: str | None = None,
    ) -> LyricsResult:
        """Generate or edit lyrics.

        Args:
            mode: Generation mode -- ``"write_full_song"`` to create new
                lyrics from a prompt, or ``"edit"`` to refine existing lyrics.
            prompt: A text description of the desired song theme/style.
            lyrics: Existing lyrics (required for ``"edit"`` mode).
            title: Desired song title hint.

        Returns:
            A :class:`LyricsResult` containing the song title, style tags,
            and generated lyrics.
        """
        body = _build_lyrics_body(
            mode,
            prompt=prompt,
            lyrics=lyrics,
            title=title,
        )

        resp = self._http.request("POST", "/v1/lyrics_generation", json=body)
        return _parse_lyrics_result(resp)


# -- Async --------------------------------------------------------------------


class AsyncMusic(AsyncResource):
    """Asynchronous music and lyrics generation resource."""

    async def generate(
        self,
        model: str = "music-2.5+",
        *,
        prompt: str | None = None,
        lyrics: str | None = None,
        output_format: str = "url",
        lyrics_optimizer: bool = False,
        is_instrumental: bool = False,
        audio_setting: dict | None = None,
    ) -> AudioResponse:
        """Generate music from a text prompt and/or lyrics.

        Args:
            model: The model identifier (default ``"music-2.5+"``).
            prompt: A text description of the desired music style/mood.
            lyrics: Lyrics for the generated track.
            output_format: ``"url"`` (default) returns a download URL;
                ``"hex"`` returns hex-encoded audio data.
            lyrics_optimizer: Whether to let the API optimise the lyrics.
            is_instrumental: Generate an instrumental track (no vocals).
            audio_setting: Optional dict with keys like ``"sample_rate"``,
                ``"bitrate"``, ``"format"``.

        Returns:
            An :class:`AudioResponse` containing the generated audio data.
        """
        body = _build_music_body(
            model,
            prompt=prompt,
            lyrics=lyrics,
            stream=False,
            output_format=output_format,
            lyrics_optimizer=lyrics_optimizer,
            is_instrumental=is_instrumental,
            audio_setting=audio_setting,
        )

        resp = await self._http.request("POST", "/v1/music_generation", json=body)
        return _build_audio_response_from_music(resp)

    async def generate_stream(
        self,
        model: str = "music-2.5+",
        *,
        prompt: str | None = None,
        lyrics: str | None = None,
        lyrics_optimizer: bool = False,
        is_instrumental: bool = False,
        audio_setting: dict | None = None,
    ) -> AsyncIterator[bytes]:
        """Generate music as a stream of decoded audio chunks.

        Streaming always uses ``output_format="hex"`` (API requirement).  Each
        yielded chunk is the decoded ``bytes`` from one SSE event.

        Args:
            model: The model identifier (default ``"music-2.5+"``).
            prompt: A text description of the desired music style/mood.
            lyrics: Lyrics for the generated track.
            lyrics_optimizer: Whether to let the API optimise the lyrics.
            is_instrumental: Generate an instrumental track (no vocals).
            audio_setting: Optional dict with keys like ``"sample_rate"``,
                ``"bitrate"``, ``"format"``.

        Yields:
            Decoded ``bytes`` chunks of audio data.
        """
        body = _build_music_body(
            model,
            prompt=prompt,
            lyrics=lyrics,
            stream=True,
            output_format="hex",
            lyrics_optimizer=lyrics_optimizer,
            is_instrumental=is_instrumental,
            audio_setting=audio_setting,
        )

        # Use the underlying httpx async client directly for streaming.
        async with self._http._client.stream(
            "POST",
            "/v1/music_generation",
            json=body,
        ) as response:
            async for line in response.aiter_lines():
                event = _parse_sse_line(line)
                if event is None:
                    continue
                data_section = event.get("data", {})
                hex_audio = data_section.get("audio", "")
                if hex_audio:
                    yield decode_hex_audio(hex_audio)

    async def generate_lyrics(
        self,
        mode: str,
        *,
        prompt: str | None = None,
        lyrics: str | None = None,
        title: str | None = None,
    ) -> LyricsResult:
        """Generate or edit lyrics.

        Args:
            mode: Generation mode -- ``"write_full_song"`` to create new
                lyrics from a prompt, or ``"edit"`` to refine existing lyrics.
            prompt: A text description of the desired song theme/style.
            lyrics: Existing lyrics (required for ``"edit"`` mode).
            title: Desired song title hint.

        Returns:
            A :class:`LyricsResult` containing the song title, style tags,
            and generated lyrics.
        """
        body = _build_lyrics_body(
            mode,
            prompt=prompt,
            lyrics=lyrics,
            title=title,
        )

        resp = await self._http.request("POST", "/v1/lyrics_generation", json=body)
        return _parse_lyrics_result(resp)
