"""Top-level MiniMax client classes.

Provides :class:`MiniMax` (synchronous) and :class:`AsyncMiniMax` (asynchronous)
entry points for the MiniMax SDK.  Each client resolves configuration from
constructor parameters, environment variables, and sensible defaults, then
exposes resource namespaces (``speech``, ``voice``, ``video``, ``image``,
``music``, ``files``) for calling the underlying APIs.
"""

from __future__ import annotations

import os
from typing import TypeVar

import dotenv
import httpx

from minimax_sdk._http import AsyncHttpClient, HttpClient
from minimax_sdk.resources.files import AsyncFiles, Files

# ── Forward-compatible imports for resources that will be added later ─────────
# Speech, Voice, Video, Image, and Music resources are not yet implemented.
# The following try/except blocks allow the client to be instantiated once those
# modules exist, while still providing clear type information.

try:
    from minimax_sdk.resources.speech import AsyncSpeech, Speech
except ImportError:  # pragma: no cover
    Speech = None  # type: ignore[assignment,misc]
    AsyncSpeech = None  # type: ignore[assignment,misc]

try:
    from minimax_sdk.resources.voice import AsyncVoice, Voice
except ImportError:  # pragma: no cover
    Voice = None  # type: ignore[assignment,misc]
    AsyncVoice = None  # type: ignore[assignment,misc]

try:
    from minimax_sdk.resources.video import AsyncVideo, Video
except ImportError:  # pragma: no cover
    Video = None  # type: ignore[assignment,misc]
    AsyncVideo = None  # type: ignore[assignment,misc]

try:
    from minimax_sdk.resources.image import AsyncImage, Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment,misc]
    AsyncImage = None  # type: ignore[assignment,misc]

try:
    from minimax_sdk.resources.music import AsyncMusic, Music
except ImportError:  # pragma: no cover
    Music = None  # type: ignore[assignment,misc]
    AsyncMusic = None  # type: ignore[assignment,misc]

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
    cast: type[T] = str,  # type: ignore[assignment]
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


# ── Sync client ──────────────────────────────────────────────────────────────


class MiniMax:
    """Synchronous MiniMax API client.

    Provides access to all MiniMax resources via attribute namespaces::

        client = MiniMax()  # reads .env automatically
        audio = client.speech.tts(text="Hello", model="speech-2.8-hd", ...)
        result = client.video.text_to_video(prompt="A cat", model="...", ...)

    Configuration is resolved with priority: parameter > env var > default.
    """

    speech: Speech  # type: ignore[valid-type]
    voice: Voice  # type: ignore[valid-type]
    video: Video  # type: ignore[valid-type]
    image: Image  # type: ignore[valid-type]
    music: Music  # type: ignore[valid-type]
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
        load_dotenv: bool = True,
    ) -> None:
        # Step 1: Load .env if requested
        if load_dotenv:
            dotenv.load_dotenv(dotenv.find_dotenv())

        # Step 2: Resolve configuration
        resolved_api_key: str = _resolve_config(api_key, "MINIMAX_API_KEY", "", cast=str)
        if not resolved_api_key:
            raise ValueError(
                "MiniMax API key is required. Provide it via the 'api_key' "
                "parameter or set the MINIMAX_API_KEY environment variable."
            )

        resolved_base_url: str = _resolve_config(
            base_url, "MINIMAX_BASE_URL", _DEFAULT_BASE_URL, cast=str
        )
        resolved_timeout_connect: float = _resolve_config(
            timeout_connect, "MINIMAX_TIMEOUT_CONNECT", _DEFAULT_TIMEOUT_CONNECT, cast=float
        )
        resolved_timeout_read: float = _resolve_config(
            timeout_read, "MINIMAX_TIMEOUT_READ", _DEFAULT_TIMEOUT_READ, cast=float
        )
        resolved_timeout_write: float = _resolve_config(
            timeout_write, "MINIMAX_TIMEOUT_WRITE", _DEFAULT_TIMEOUT_WRITE, cast=float
        )
        resolved_timeout_pool: float = _resolve_config(
            timeout_pool, "MINIMAX_TIMEOUT_POOL", _DEFAULT_TIMEOUT_POOL, cast=float
        )
        resolved_max_retries: int = _resolve_config(
            max_retries, "MINIMAX_MAX_RETRIES", _DEFAULT_MAX_RETRIES, cast=int
        )

        self.poll_interval: float = _resolve_config(
            poll_interval, "MINIMAX_POLL_INTERVAL", _DEFAULT_POLL_INTERVAL, cast=float
        )
        self.poll_timeout: float = _resolve_config(
            poll_timeout, "MINIMAX_POLL_TIMEOUT", _DEFAULT_POLL_TIMEOUT, cast=float
        )

        # Step 3: Create the HTTP transport
        timeout = httpx.Timeout(
            connect=resolved_timeout_connect,
            read=resolved_timeout_read,
            write=resolved_timeout_write,
            pool=resolved_timeout_pool,
        )

        self._http_client = HttpClient(
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            timeout=timeout,
            max_retries=resolved_max_retries,
        )

        # Step 4: Mount resource namespaces
        if Speech is not None:
            self.speech = Speech(self._http_client, self)
        if Voice is not None:
            self.voice = Voice(self._http_client, self)
        if Video is not None:
            self.video = Video(self._http_client, self)
        if Image is not None:
            self.image = Image(self._http_client, self)
        if Music is not None:
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

        client = AsyncMiniMax()
        audio = await client.speech.tts(text="Hello", model="speech-2.8-hd", ...)
        result = await client.video.text_to_video(prompt="A cat", model="...", ...)

    Configuration is resolved with priority: parameter > env var > default.
    """

    speech: AsyncSpeech  # type: ignore[valid-type]
    voice: AsyncVoice  # type: ignore[valid-type]
    video: AsyncVideo  # type: ignore[valid-type]
    image: AsyncImage  # type: ignore[valid-type]
    music: AsyncMusic  # type: ignore[valid-type]
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
        load_dotenv: bool = True,
    ) -> None:
        # Step 1: Load .env if requested
        if load_dotenv:
            dotenv.load_dotenv(dotenv.find_dotenv())

        # Step 2: Resolve configuration
        resolved_api_key: str = _resolve_config(api_key, "MINIMAX_API_KEY", "", cast=str)
        if not resolved_api_key:
            raise ValueError(
                "MiniMax API key is required. Provide it via the 'api_key' "
                "parameter or set the MINIMAX_API_KEY environment variable."
            )

        resolved_base_url: str = _resolve_config(
            base_url, "MINIMAX_BASE_URL", _DEFAULT_BASE_URL, cast=str
        )
        resolved_timeout_connect: float = _resolve_config(
            timeout_connect, "MINIMAX_TIMEOUT_CONNECT", _DEFAULT_TIMEOUT_CONNECT, cast=float
        )
        resolved_timeout_read: float = _resolve_config(
            timeout_read, "MINIMAX_TIMEOUT_READ", _DEFAULT_TIMEOUT_READ, cast=float
        )
        resolved_timeout_write: float = _resolve_config(
            timeout_write, "MINIMAX_TIMEOUT_WRITE", _DEFAULT_TIMEOUT_WRITE, cast=float
        )
        resolved_timeout_pool: float = _resolve_config(
            timeout_pool, "MINIMAX_TIMEOUT_POOL", _DEFAULT_TIMEOUT_POOL, cast=float
        )
        resolved_max_retries: int = _resolve_config(
            max_retries, "MINIMAX_MAX_RETRIES", _DEFAULT_MAX_RETRIES, cast=int
        )

        self.poll_interval: float = _resolve_config(
            poll_interval, "MINIMAX_POLL_INTERVAL", _DEFAULT_POLL_INTERVAL, cast=float
        )
        self.poll_timeout: float = _resolve_config(
            poll_timeout, "MINIMAX_POLL_TIMEOUT", _DEFAULT_POLL_TIMEOUT, cast=float
        )

        # Step 3: Create the HTTP transport
        timeout = httpx.Timeout(
            connect=resolved_timeout_connect,
            read=resolved_timeout_read,
            write=resolved_timeout_write,
            pool=resolved_timeout_pool,
        )

        self._http_client = AsyncHttpClient(
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            timeout=timeout,
            max_retries=resolved_max_retries,
        )

        # Step 4: Mount resource namespaces
        if AsyncSpeech is not None:
            self.speech = AsyncSpeech(self._http_client, self)
        if AsyncVoice is not None:
            self.voice = AsyncVoice(self._http_client, self)
        if AsyncVideo is not None:
            self.video = AsyncVideo(self._http_client, self)
        if AsyncImage is not None:
            self.image = AsyncImage(self._http_client, self)
        if AsyncMusic is not None:
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
