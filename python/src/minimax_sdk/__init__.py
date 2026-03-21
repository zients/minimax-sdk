"""MiniMax SDK — Python client for MiniMax's multimodal APIs.

Usage::

    from minimax_sdk import MiniMax

    client = MiniMax()  # reads MINIMAX_API_KEY from environment variable
    audio = client.speech.tts(text="Hello world", model="speech-2.8-hd", ...)
"""

from __future__ import annotations

from minimax_sdk._audio import AudioResponse
from minimax_sdk.client import AsyncMiniMax, MiniMax
from minimax_sdk.exceptions import (
    AuthError,
    ContentSafetyError,
    InsufficientBalanceError,
    InputSafetyError,
    InvalidParameterError,
    MiniMaxError,
    OutputSafetyError,
    PollTimeoutError,
    RateLimitError,
    ServerError,
    APITimeoutError,
    VoiceCloneError,
    VoiceDuplicateError,
    VoiceError,
    VoicePermissionError,
)
from minimax_sdk.types.files import FileInfo
from minimax_sdk.types.image import ImageResult, ImageSubjectReference
from minimax_sdk.types.music import LyricsResult
from minimax_sdk.types.text import (
    ContentBlock,
    ContentBlockDeltaEvent,
    ContentBlockStartEvent,
    ContentBlockStopEvent,
    Delta,
    InputJsonDelta,
    Message,
    MessageDelta,
    MessageDeltaEvent,
    MessageStartEvent,
    MessageStopEvent,
    SignatureDelta,
    StreamEvent,
    TextBlock,
    TextDelta,
    ThinkingBlock,
    ThinkingDelta,
    ToolUseBlock,
    Usage,
)
from minimax_sdk.types.video import VideoResult
from minimax_sdk.types.voice import (
    VoiceCloneResult,
    VoiceDesignResult,
    VoiceInfo,
    VoiceList,
)

__version__ = "0.1.1"

__all__ = [
    # Clients
    "MiniMax",
    "AsyncMiniMax",
    # Exceptions
    "MiniMaxError",
    "AuthError",
    "RateLimitError",
    "InsufficientBalanceError",
    "ContentSafetyError",
    "InputSafetyError",
    "OutputSafetyError",
    "InvalidParameterError",
    "APITimeoutError",
    "PollTimeoutError",
    "VoiceError",
    "VoiceCloneError",
    "VoiceDuplicateError",
    "VoicePermissionError",
    "ServerError",
    # Types — shared
    "AudioResponse",
    # Types — text
    "Message",
    "ContentBlock",
    "TextBlock",
    "ToolUseBlock",
    "ThinkingBlock",
    "Usage",
    # Types — text streaming
    "StreamEvent",
    "MessageStartEvent",
    "ContentBlockStartEvent",
    "ContentBlockDeltaEvent",
    "ContentBlockStopEvent",
    "MessageDeltaEvent",
    "MessageStopEvent",
    "Delta",
    "TextDelta",
    "InputJsonDelta",
    "ThinkingDelta",
    "SignatureDelta",
    "MessageDelta",
    # Types — video
    "VideoResult",
    # Types — image
    "ImageResult",
    "ImageSubjectReference",
    # Types — voice
    "VoiceCloneResult",
    "VoiceDesignResult",
    "VoiceList",
    "VoiceInfo",
    # Types — music
    "LyricsResult",
    # Types — files
    "FileInfo",
    # Version
    "__version__",
]
