"""Top-level MiniMax client classes.

Provides :class:`MiniMax` (synchronous) and :class:`AsyncMiniMax` (asynchronous)
entry points for the MiniMax SDK.  Each client resolves configuration from
constructor parameters, environment variables, and sensible defaults, then
exposes resource namespaces (``speech``, ``voice``, ``video``, ``image``,
``music``, ``files``) for calling the underlying APIs.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import NamedTuple, TypeVar

import httpx

from minimax_sdk._http import AsyncHttpClient, HttpClient
from minimax_sdk.resources.files import AsyncFiles, Files
from minimax_sdk.resources.image import AsyncImage, Image
from minimax_sdk.resources.music import AsyncMusic, Music
from minimax_sdk.resources.speech import AsyncSpeech, Speech
from minimax_sdk.resources.text import AsyncText, Text
from minimax_sdk.resources.video import AsyncVideo, Video
from minimax_sdk.resources.voice import AsyncVoice, Voice

# ── Configuration defaults ───────────────────────────────────────────────────

_DEFAULT_BASE_URL: str = "https://api.minimax.io"
_DEFAULT_TIMEOUT_CONNECT: float = 5.0
_DEFAULT_TIMEOUT_READ: float = 600.0
_DEFAULT_TIMEOUT_WRITE: float = 600.0
_DEFAULT_TIMEOUT_POOL: float = 600.0
_DEFAULT_MAX_RETRIES: int = 2
_DEFAULT_POLL_INTERVAL: float = 5.0
_DEFAULT_POLL_TIMEOUT: float = 600.0

T = TypeVar("T")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _resolve_config(
    param: T | None,
    env_var: str,
    default: T,
    cast: Callable[[str], T] = str,  # type: ignore[assignment]
) -> T:
    """Resolve a configuration value with priority: parameter > env var > default.

    Parameters
    ----------
    param:
        Explicitly provided constructor parameter (highest priority).
    env_var:
        Name of the environment variable to check as fallback.
    default:
        Default value if neither *param* nor *env_var* yields a result.
    cast:
        Callable used to convert the environment variable string to the
        target type (e.g. ``float``, ``int``).

    Returns
    -------
    T:
        The resolved configuration value.
    """
    if param is not None:
        return param
    env_val = os.environ.get(env_var)
    if env_val is not None:
        return cast(env_val)
    return default


class _ResolvedConfig(NamedTuple):
    """Holds all resolved configuration values for client construction."""

    api_key: str
    base_url: str
    timeout: httpx.Timeout
    max_retries: int
    poll_interval: float
    poll_timeout: float


def _build_config(
    *,
    api_key: str | None,
    base_url: str | None,
    timeout_connect: float | None,
    timeout_read: float | None,
    timeout_write: float | None,
    timeout_pool: float | None,
    max_retries: int | None,
    poll_interval: float | None,
    poll_timeout: float | None,
) -> _ResolvedConfig:
    """Resolve all configuration values and build an httpx Timeout.

    Both :class:`MiniMax` and :class:`AsyncMiniMax` delegate to this function
    so that the resolution logic is defined exactly once.
    """
    resolved_api_key: str = _resolve_config(api_key, "MINIMAX_API_KEY", "", cast=str)
    if not resolved_api_key:
        raise ValueError(
            "MiniMax API key is required. Provide it via the 'api_key' "
            "parameter or set the MINIMAX_API_KEY environment variable."
        )

    resolved_base_url: str = _resolve_config(
        base_url, "MINIMAX_BASE_URL", _DEFAULT_BASE_URL, cast=str
    )
    timeout = httpx.Timeout(
        connect=timeout_connect if timeout_connect is not None else _DEFAULT_TIMEOUT_CONNECT,
        read=timeout_read if timeout_read is not None else _DEFAULT_TIMEOUT_READ,
        write=timeout_write if timeout_write is not None else _DEFAULT_TIMEOUT_WRITE,
        pool=timeout_pool if timeout_pool is not None else _DEFAULT_TIMEOUT_POOL,
    )
    resolved_max_retries = max_retries if max_retries is not None else _DEFAULT_MAX_RETRIES
    resolved_poll_interval = poll_interval if poll_interval is not None else _DEFAULT_POLL_INTERVAL
    resolved_poll_timeout = poll_timeout if poll_timeout is not None else _DEFAULT_POLL_TIMEOUT

    return _ResolvedConfig(
        api_key=resolved_api_key,
        base_url=resolved_base_url,
        timeout=timeout,
        max_retries=resolved_max_retries,
        poll_interval=resolved_poll_interval,
        poll_timeout=resolved_poll_timeout,
    )


# ── Sync client ──────────────────────────────────────────────────────────────


class MiniMax:
    """Synchronous MiniMax API client.

    Provides access to all MiniMax resources via attribute namespaces::

        client = MiniMax(api_key="sk-xxx")
        audio = client.speech.tts(text="Hello", model="speech-2.8-hd", ...)
        result = client.video.text_to_video(prompt="A cat", model="...", ...)

    Configuration is resolved with priority: parameter > default.
    Only ``api_key`` and ``base_url`` support environment variables.
    """

    text: Text
    speech: Speech
    voice: Voice
    video: Video
    image: Image
    music: Music
    files: Files

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_connect: float | None = None,
        timeout_read: float | None = None,
        timeout_write: float | None = None,
        timeout_pool: float | None = None,
        max_retries: int | None = None,
        poll_interval: float | None = None,
        poll_timeout: float | None = None,
    ) -> None:
        cfg = _build_config(
            api_key=api_key,
            base_url=base_url,
            timeout_connect=timeout_connect,
            timeout_read=timeout_read,
            timeout_write=timeout_write,
            timeout_pool=timeout_pool,
            max_retries=max_retries,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
        )

        self.poll_interval = cfg.poll_interval
        self.poll_timeout = cfg.poll_timeout

        self._http_client = HttpClient(
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            timeout=cfg.timeout,
            max_retries=cfg.max_retries,
        )

        # Mount resource namespaces
        self.text = Text(self._http_client, self)
        self.speech = Speech(self._http_client, self)
        self.voice = Voice(self._http_client, self)
        self.video = Video(self._http_client, self)
        self.image = Image(self._http_client, self)
        self.music = Music(self._http_client, self)
        self.files = Files(self._http_client, self)

    def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        self._http_client.close()

    def __enter__(self) -> MiniMax:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"MiniMax(base_url={self._http_client.base_url!r}, "
            f"poll_interval={self.poll_interval}, "
            f"poll_timeout={self.poll_timeout})"
        )


# ── Async client ─────────────────────────────────────────────────────────────


class AsyncMiniMax:
    """Asynchronous MiniMax API client.

    Provides access to all MiniMax resources via attribute namespaces::

        client = AsyncMiniMax(api_key="sk-xxx")
        audio = await client.speech.tts(text="Hello", model="speech-2.8-hd", ...)
        result = await client.video.text_to_video(prompt="A cat", model="...", ...)

    Configuration is resolved with priority: parameter > default.
    Only ``api_key`` and ``base_url`` support environment variables.
    """

    text: AsyncText
    speech: AsyncSpeech
    voice: AsyncVoice
    video: AsyncVideo
    image: AsyncImage
    music: AsyncMusic
    files: AsyncFiles

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_connect: float | None = None,
        timeout_read: float | None = None,
        timeout_write: float | None = None,
        timeout_pool: float | None = None,
        max_retries: int | None = None,
        poll_interval: float | None = None,
        poll_timeout: float | None = None,
    ) -> None:
        cfg = _build_config(
            api_key=api_key,
            base_url=base_url,
            timeout_connect=timeout_connect,
            timeout_read=timeout_read,
            timeout_write=timeout_write,
            timeout_pool=timeout_pool,
            max_retries=max_retries,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
        )

        self.poll_interval = cfg.poll_interval
        self.poll_timeout = cfg.poll_timeout

        self._http_client = AsyncHttpClient(
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            timeout=cfg.timeout,
            max_retries=cfg.max_retries,
        )

        # Mount resource namespaces
        self.text = AsyncText(self._http_client, self)
        self.speech = AsyncSpeech(self._http_client, self)
        self.voice = AsyncVoice(self._http_client, self)
        self.video = AsyncVideo(self._http_client, self)
        self.image = AsyncImage(self._http_client, self)
        self.music = AsyncMusic(self._http_client, self)
        self.files = AsyncFiles(self._http_client, self)

    async def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        await self._http_client.close()

    async def __aenter__(self) -> AsyncMiniMax:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    def __repr__(self) -> str:
        return (
            f"AsyncMiniMax(base_url={self._http_client.base_url!r}, "
            f"poll_interval={self.poll_interval}, "
            f"poll_timeout={self.poll_timeout})"
        )
