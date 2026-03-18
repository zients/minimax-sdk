"""Type definitions for the Speech resource."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class VoiceSetting(BaseModel):
    """Voice configuration for TTS requests."""

    voice_id: str
    speed: Optional[float] = None
    vol: Optional[float] = None
    pitch: Optional[int] = None
    emotion: Optional[str] = None
    text_normalization: Optional[int] = None
    latex_read: Optional[str] = None


class AudioSetting(BaseModel):
    """Audio output configuration for TTS requests."""

    sample_rate: Optional[int] = None
    bitrate: Optional[int] = None
    format: Optional[str] = None
    channel: Optional[int] = None
    force_cbr: Optional[bool] = None


class VoiceModify(BaseModel):
    """Voice modification parameters."""

    pitch: Optional[int] = None
    intensity: Optional[int] = None
    timbre: Optional[int] = None
    sound_effects: Optional[str] = None


class T2ARequest(BaseModel):
    """Request body for synchronous TTS (POST /v1/t2a_v2)."""

    model: str
    text: str
    stream: Optional[bool] = False
    voice_setting: Optional[VoiceSetting] = None
    audio_setting: Optional[AudioSetting] = None
    pronunciation_dict: Optional[list[dict[str, Any]]] = None
    timbre_weights: Optional[list[dict[str, Any]]] = None
    language_boost: Optional[str] = None
    voice_modify: Optional[VoiceModify] = None
    subtitle_enable: Optional[bool] = None
    output_format: Optional[str] = None


class T2AAsyncCreateRequest(BaseModel):
    """Request body for async TTS task creation (POST /v1/t2a_async_v2)."""

    model: str
    text: Optional[str] = None
    text_file_id: Optional[str] = None
    voice_setting: Optional[VoiceSetting] = None
    audio_setting: Optional[AudioSetting] = None
    pronunciation_dict: Optional[list[dict[str, Any]]] = None
    language_boost: Optional[str] = None
    voice_modify: Optional[VoiceModify] = None


class T2AAsyncResult(BaseModel):
    """Result of an async TTS task query."""

    task_id: str
    status: str
    file_id: Optional[str] = None


class TaskResult(BaseModel):
    """Final result of a completed async task (create + poll + retrieve).

    Returned by high-level methods that auto-poll until completion,
    such as ``Speech.async_generate``.
    """

    task_id: str
    status: str
    file_id: str
    download_url: str
