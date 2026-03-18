"""Audio response model and hex-decoding utilities.

Provides :class:`AudioResponse` — the primary return type for TTS and music
generation calls — plus standalone helper functions for decoding MiniMax's
hex-encoded audio payloads.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


def decode_hex_audio(hex_str: str) -> bytes:
    """Decode a hex-encoded audio string into raw bytes.

    MiniMax APIs return audio data as hex-encoded strings; this function
    converts them back to the original binary representation.

    Parameters
    ----------
    hex_str:
        The hex-encoded audio string from the API response.

    Returns
    -------
    bytes:
        The decoded raw audio bytes.
    """
    return bytes.fromhex(hex_str)


class AudioResponse(BaseModel):
    """Decoded audio returned by TTS and music generation endpoints.

    Attributes
    ----------
    data:
        Raw audio bytes (decoded from hex).
    duration:
        Duration in milliseconds (float to avoid truncation).
    sample_rate:
        Audio sample rate in Hz.
    format:
        Audio format — ``"mp3"``, ``"pcm"``, ``"flac"``, or ``"wav"``.
    size:
        Size of the audio data in bytes.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    data: bytes
    duration: float = 0
    sample_rate: int = 0
    format: str = "mp3"
    size: int = 0

    def save(self, path: str | Path) -> None:
        """Write the audio data to a file on disk.

        Parameters
        ----------
        path:
            Destination file path.
        """
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.data)

    def to_base64(self) -> str:
        """Return the audio data as a base64-encoded string."""
        return base64.b64encode(self.data).decode("ascii")

    def __repr__(self) -> str:
        data_preview = f"<{len(self.data)} bytes>"
        return (
            f"AudioResponse(data={data_preview}, duration={self.duration}, "
            f"sample_rate={self.sample_rate}, format={self.format!r}, "
            f"size={self.size})"
        )


def build_audio_response(api_response: dict[str, Any]) -> AudioResponse:
    """Build an :class:`AudioResponse` from a raw MiniMax API response dict.

    Expects the response dict to contain at minimum:

    - ``data.audio`` — hex-encoded audio string
    - ``extra_info.audio_length`` — duration in milliseconds
    - ``extra_info.audio_sample_rate`` — sample rate in Hz
    - ``extra_info.audio_size`` — size in bytes
    - ``extra_info.audio_format`` or the ``audio_setting.format`` from the
      request (caller should pass whichever is available)

    The function also supports a flattened structure where the keys live at the
    top level of *api_response* (e.g., ``audio_hex``, ``audio_length``, etc.)
    as a convenience for different endpoint shapes.

    Parameters
    ----------
    api_response:
        The parsed JSON body returned by the MiniMax API (after ``base_resp``
        validation has already passed).

    Returns
    -------
    AudioResponse:
        A fully populated audio response with decoded bytes.
    """
    # ── Nested structure (e.g. T2A v2) ────────────────────────────────────
    data_section = api_response.get("data", {})
    extra_info = api_response.get("extra_info", {})

    hex_audio: str = (
        data_section.get("audio", "")
        or api_response.get("audio_hex", "")
        or api_response.get("audio", "")
    )

    audio_bytes = decode_hex_audio(hex_audio) if hex_audio else b""

    duration: float = float(
        extra_info.get("audio_length", 0)
        or api_response.get("audio_length", 0)
        or api_response.get("duration", 0)
    )

    sample_rate: int = int(
        extra_info.get("audio_sample_rate", 0)
        or api_response.get("audio_sample_rate", 0)
        or api_response.get("sample_rate", 0)
    )

    audio_size: int = int(
        extra_info.get("audio_size", 0)
        or api_response.get("audio_size", 0)
        or api_response.get("size", 0)
        or len(audio_bytes)
    )

    audio_format: str = (
        extra_info.get("audio_format", "")
        or api_response.get("audio_format", "")
        or api_response.get("format", "mp3")
    )

    return AudioResponse(
        data=audio_bytes,
        duration=duration,
        sample_rate=sample_rate,
        format=audio_format,
        size=audio_size,
    )
