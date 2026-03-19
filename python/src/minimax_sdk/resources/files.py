"""Files resource — upload, list, retrieve, download, and delete files.

Provides both synchronous (`Files`) and asynchronous (`AsyncFiles`) clients.
"""

from __future__ import annotations

from typing import BinaryIO, Union

from .._base import AsyncResource, SyncResource
from ..types.files import FileInfo

_VALID_UPLOAD_PURPOSES = frozenset({"voice_clone", "prompt_audio", "t2a_async_input"})


def _validate_upload_purpose(purpose: str) -> None:
    """Raise ValueError if *purpose* is not valid for upload."""
    if purpose not in _VALID_UPLOAD_PURPOSES:
        raise ValueError(
            f"Invalid upload purpose {purpose!r}. "
            f"Must be one of: {', '.join(sorted(_VALID_UPLOAD_PURPOSES))}"
        )


def _open_file(file: Union[str, BinaryIO]) -> tuple[BinaryIO, bool]:
    """Return a (stream, should_close) pair.

    If *file* is a path string the file is opened in binary mode and the
    caller is responsible for closing it (``should_close=True``).  If it is
    already a file-like object it is returned as-is.
    """
    if isinstance(file, str):
        return open(file, "rb"), True
    return file, False


# ── Sync ─────────────────────────────────────────────────────────────────────


class Files(SyncResource):
    """Synchronous files resource."""

    def upload(self, file: Union[str, BinaryIO], purpose: str) -> FileInfo:
        """Upload a file.

        Args:
            file: A filesystem path (``str``) or an already-opened binary
                file object.
            purpose: The intended use of the file.  Must be one of
                ``"voice_clone"``, ``"prompt_audio"``, or
                ``"t2a_async_input"``.

        Returns:
            A :class:`FileInfo` describing the uploaded file.
        """
        _validate_upload_purpose(purpose)

        stream, should_close = _open_file(file)
        try:
            resp = self._http.upload("/v1/files/upload", file=stream, purpose=purpose)
        finally:
            if should_close:
                stream.close()

        return FileInfo.model_validate(resp["file"])

    def list(self, purpose: str) -> list[FileInfo]:
        """List files that match the given *purpose*.

        Args:
            purpose: Filter files by purpose.

        Returns:
            A list of :class:`FileInfo` objects.
        """
        resp = self._http.request("GET", "/v1/files/list", params={"purpose": purpose})
        return [FileInfo.model_validate(f) for f in resp["files"]]

    def retrieve(self, file_id: str) -> FileInfo:
        """Retrieve metadata (and a temporary download URL) for a file.

        Args:
            file_id: The identifier of the file to retrieve.

        Returns:
            A :class:`FileInfo` with a ``download_url`` (valid for ~1 hr
            for video files, ~9 hr for T2A async files).
        """
        resp = self._http.request("GET", "/v1/files/retrieve", params={"file_id": int(file_id)})
        return FileInfo.model_validate(resp["file"])

    def retrieve_content(self, file_id: str) -> bytes:
        """Download the raw content of a file.

        Args:
            file_id: The identifier of the file to download.

        Returns:
            The file content as ``bytes``.
        """
        return self._http.request_bytes(
            "GET", "/v1/files/retrieve_content", params={"file_id": int(file_id)}
        )

    def delete(self, file_id: str, purpose: str) -> None:
        """Delete a file.

        Args:
            file_id: The identifier of the file to delete.
            purpose: The purpose tag of the file.
        """
        self._http.request(
            "POST",
            "/v1/files/delete",
            json={"file_id": int(file_id), "purpose": purpose},
        )


# ── Async ────────────────────────────────────────────────────────────────────


class AsyncFiles(AsyncResource):
    """Asynchronous files resource."""

    async def upload(self, file: Union[str, BinaryIO], purpose: str) -> FileInfo:
        """Upload a file.

        Args:
            file: A filesystem path (``str``) or an already-opened binary
                file object.
            purpose: The intended use of the file.  Must be one of
                ``"voice_clone"``, ``"prompt_audio"``, or
                ``"t2a_async_input"``.

        Returns:
            A :class:`FileInfo` describing the uploaded file.
        """
        _validate_upload_purpose(purpose)

        stream, should_close = _open_file(file)
        try:
            resp = await self._http.upload("/v1/files/upload", file=stream, purpose=purpose)
        finally:
            if should_close:
                stream.close()

        return FileInfo.model_validate(resp["file"])

    async def list(self, purpose: str) -> list[FileInfo]:
        """List files that match the given *purpose*.

        Args:
            purpose: Filter files by purpose.

        Returns:
            A list of :class:`FileInfo` objects.
        """
        resp = await self._http.request("GET", "/v1/files/list", params={"purpose": purpose})
        return [FileInfo.model_validate(f) for f in resp["files"]]

    async def retrieve(self, file_id: str) -> FileInfo:
        """Retrieve metadata (and a temporary download URL) for a file.

        Args:
            file_id: The identifier of the file to retrieve.

        Returns:
            A :class:`FileInfo` with a ``download_url`` (valid for ~1 hr
            for video files, ~9 hr for T2A async files).
        """
        resp = await self._http.request(
            "GET", "/v1/files/retrieve", params={"file_id": int(file_id)}
        )
        return FileInfo.model_validate(resp["file"])

    async def retrieve_content(self, file_id: str) -> bytes:
        """Download the raw content of a file.

        Args:
            file_id: The identifier of the file to download.

        Returns:
            The file content as ``bytes``.
        """
        return await self._http.request_bytes(
            "GET", "/v1/files/retrieve_content", params={"file_id": int(file_id)}
        )

    async def delete(self, file_id: str, purpose: str) -> None:
        """Delete a file.

        Args:
            file_id: The identifier of the file to delete.
            purpose: The purpose tag of the file.
        """
        await self._http.request(
            "POST",
            "/v1/files/delete",
            json={"file_id": int(file_id), "purpose": purpose},
        )
