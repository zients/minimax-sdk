"""MiniMax SDK type definitions.

All types are Pydantic v2 BaseModel subclasses.
"""

from minimax_sdk.types.files import FileInfo, FileList
from minimax_sdk.types.image import (
    ImageResult,
    ImageSubjectReference,
)
from minimax_sdk.types.music import (
    LyricsResult,
)
from minimax_sdk.types.speech import (
    T2AAsyncResult,
    TaskResult,
)
from minimax_sdk.types.video import (
    VideoCreateResult,
    VideoQueryResult,
    VideoResult,
)
from minimax_sdk.types.voice import (
    VoiceCloneResult,
    VoiceDesignResult,
    VoiceInfo,
    VoiceList,
)

__all__ = [
    # speech
    "T2AAsyncResult",
    "TaskResult",
    # voice
    "VoiceCloneResult",
    "VoiceDesignResult",
    "VoiceInfo",
    "VoiceList",
    # video
    "VideoCreateResult",
    "VideoQueryResult",
    "VideoResult",
    # image
    "ImageResult",
    "ImageSubjectReference",
    # music
    "LyricsResult",
    # files
    "FileInfo",
    "FileList",
]
