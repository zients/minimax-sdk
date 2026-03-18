"""Type definitions for the Voice resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from .._audio import AudioResponse


class VoiceCloneResult(BaseModel):
    """Result of a voice clone operation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    voice_id: str
    demo_audio: Optional[str] = None  # URL to preview audio, or None
    input_sensitive: Any = None


class VoiceDesignResult(BaseModel):
    """Result of a voice design operation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    voice_id: str
    trial_audio: AudioResponse | None = None


class VoiceInfo(BaseModel):
    """Information about a single voice."""

    voice_id: str
    voice_name: Optional[str] = None
    description: list[str] = []
    created_time: Optional[str] = None


class VoiceList(BaseModel):
    """Result of listing voices."""

    system_voice: list[VoiceInfo] = []
    voice_cloning: list[VoiceInfo] = []
    voice_generation: list[VoiceInfo] = []
