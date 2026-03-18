"""HTTP transport layer for the MiniMax SDK.

Provides ``HttpClient`` (sync) and ``AsyncHttpClient`` wrapping httpx,
with automatic error mapping, retry logic, and multipart upload support.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, BinaryIO

import httpx

from minimax_sdk.exceptions import (
    ERROR_CODE_MAP,
    RETRYABLE_CODES,
    MiniMaxError,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

_DEFAULT_BASE_DELAY: float = 1.0  # seconds, for exponential backoff


def _parse_error(body: dict[str, Any]) -> tuple[int, str, str]:
    """Extract (status_code, status_msg, trace_id) from a MiniMax response."""
    base = body.get("base_resp", body)
    code = int(base.get("status_code", 0))
    msg = base.get("status_msg", "")
    trace_id = body.get("trace_id", base.get("trace_id", ""))
    return code, msg, trace_id


def _raise_for_status(body: dict[str, Any]) -> None:
    """Raise a mapped exception when *base_resp.status_code* != 0."""
    code, msg, trace_id = _parse_error(body)
    if code == 0:
        return
    exc_cls = ERROR_CODE_MAP.get(code, MiniMaxError)
    raise exc_cls(msg, code=code, trace_id=trace_id)


def _backoff_delay(attempt: int, *, base: float = _DEFAULT_BASE_DELAY) -> float:
    """Compute exponential backoff delay: base * 2^attempt."""
    return base * (2**attempt)


def _should_retry(code: int) -> bool:
    return code in RETRYABLE_CODES


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Return the value of the Retry-After header in seconds, if present."""
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# ── Sync Client ───────────────────────────────────────────────────────────────


class HttpClient:
    """Synchronous HTTP client for MiniMax APIs."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.minimax.io",
        timeout: httpx.Timeout | None = None,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries

        if timeout is None:
            timeout = httpx.Timeout(
                connect=5.0,
                read=600.0,
                write=600.0,
                pool=600.0,
            )

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    # ── Core request ──────────────────────────────────────────────────────

    def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send an HTTP request, decode JSON, map errors, and auto-retry.

        Returns the full parsed JSON body on success (``base_resp.status_code == 0``).

        Raises a mapped :class:`MiniMaxError` subclass on API errors.
        Retries automatically on retryable status codes using exponential backoff.
        """
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.request(method, path, **kwargs)
                body: dict[str, Any] = response.json()
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(_backoff_delay(attempt))
                    continue
                raise MiniMaxError(
                    f"HTTP transport error: {exc}",
                    code=0,
                    trace_id="",
                ) from exc

            code, msg, trace_id = _parse_error(body)

            if code == 0:
                return body

            if _should_retry(code) and attempt < self.max_retries:
                # For 1002 (Rate Limit), honour Retry-After header if present.
                if code == 1002:
                    retry_after = _retry_after_seconds(response)
                    if retry_after is not None:
                        time.sleep(retry_after)
                        continue
                time.sleep(_backoff_delay(attempt))
                continue

            # Non-retryable or exhausted retries — raise immediately.
            _raise_for_status(body)

        # Should not reach here, but just in case:
        if last_exc is not None:
            raise MiniMaxError(
                f"Request failed after {self.max_retries + 1} attempts: {last_exc}",
                code=0,
                trace_id="",
            ) from last_exc
        raise MiniMaxError("Request failed with unknown error", code=0, trace_id="")

    # ── Raw bytes request ────────────────────────────────────────────────

    def request_bytes(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> bytes:
        """Send an HTTP request and return raw response bytes.

        Unlike :meth:`request`, this does **not** parse JSON — it returns
        the raw binary content.  Used for endpoints that return file data
        (e.g. ``/v1/files/retrieve_content``).
        """
        response = self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.content

    # ── Upload ────────────────────────────────────────────────────────────

    def upload(
        self,
        path: str,
        file: str | Path | BinaryIO,
        purpose: str,
    ) -> dict[str, Any]:
        """Upload a file via multipart/form-data.

        Parameters
        ----------
        path:
            API path (e.g. ``"/v1/files/upload"``).
        file:
            A file path (str / Path) or an open binary file-like object.
        purpose:
            Upload purpose (e.g. ``"voice_clone"``, ``"prompt_audio"``).
        """
        if isinstance(file, (str, Path)):
            file_path = Path(file)
            with open(file_path, "rb") as fh:
                files = {"file": (file_path.name, fh)}
                return self.request(
                    "POST",
                    path,
                    files=files,
                    data={"purpose": purpose},
                )
        else:
            filename = getattr(file, "name", "upload")
            if isinstance(filename, (str, Path)):
                filename = Path(filename).name
            files = {"file": (filename, file)}
            return self.request(
                "POST",
                path,
                files=files,
                data={"purpose": purpose},
            )

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ── Async Client ──────────────────────────────────────────────────────────────


class AsyncHttpClient:
    """Asynchronous HTTP client for MiniMax APIs."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.minimax.io",
        timeout: httpx.Timeout | None = None,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries

        if timeout is None:
            timeout = httpx.Timeout(
                connect=5.0,
                read=600.0,
                write=600.0,
                pool=600.0,
            )

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    # ── Core request ──────────────────────────────────────────────────────

    async def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send an async HTTP request, decode JSON, map errors, and auto-retry."""
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.request(method, path, **kwargs)
                body: dict[str, Any] = response.json()
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(_backoff_delay(attempt))
                    continue
                raise MiniMaxError(
                    f"HTTP transport error: {exc}",
                    code=0,
                    trace_id="",
                ) from exc

            code, msg, trace_id = _parse_error(body)

            if code == 0:
                return body

            if _should_retry(code) and attempt < self.max_retries:
                if code == 1002:
                    retry_after = _retry_after_seconds(response)
                    if retry_after is not None:
                        await asyncio.sleep(retry_after)
                        continue
                await asyncio.sleep(_backoff_delay(attempt))
                continue

            _raise_for_status(body)

        if last_exc is not None:
            raise MiniMaxError(
                f"Request failed after {self.max_retries + 1} attempts: {last_exc}",
                code=0,
                trace_id="",
            ) from last_exc
        raise MiniMaxError("Request failed with unknown error", code=0, trace_id="")

    # ── Raw bytes request ────────────────────────────────────────────────

    async def request_bytes(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> bytes:
        """Send an async HTTP request and return raw response bytes."""
        response = await self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.content

    # ── Upload ────────────────────────────────────────────────────────────

    async def upload(
        self,
        path: str,
        file: str | Path | BinaryIO,
        purpose: str,
    ) -> dict[str, Any]:
        """Upload a file via multipart/form-data (async)."""
        if isinstance(file, (str, Path)):
            file_path = Path(file)
            with open(file_path, "rb") as fh:
                files = {"file": (file_path.name, fh)}
                return await self.request(
                    "POST",
                    path,
                    files=files,
                    data={"purpose": purpose},
                )
        else:
            filename = getattr(file, "name", "upload")
            if isinstance(filename, (str, Path)):
                filename = Path(filename).name
            files = {"file": (filename, file)}
            return await self.request(
                "POST",
                path,
                files=files,
                data={"purpose": purpose},
            )

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncHttpClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
