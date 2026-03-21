"""Tests for the Files resource."""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest

from minimax_sdk.resources.files import Files
from minimax_sdk.types.files import FileInfo


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_file_dict(**overrides) -> dict:
    """Return a minimal file dict suitable for FileInfo.model_validate."""
    defaults = {
        "file_id": "123456",
        "bytes": 1024,
        "created_at": 1710000000,
        "filename": "test.wav",
        "purpose": "voice_clone",
        "download_url": None,
    }
    defaults.update(overrides)
    return defaults


def _ok_resp(payload: dict) -> dict:
    """Wrap a payload in a successful API response envelope."""
    return {"base_resp": {"status_code": 0, "status_msg": "success"}, **payload}


def _make_files_resource() -> tuple[Files, MagicMock]:
    """Create a Files resource with a mocked HttpClient."""
    mock_http = MagicMock()
    files = Files(mock_http, client=None)
    return files, mock_http


# ── Tests ────────────────────────────────────────────────────────────────────


class TestFilesUpload:
    """Tests for files.upload()."""

    def test_upload_with_file_path(self, tmp_path):
        """Upload using a file path string delegates to _http.upload."""
        files, mock_http = _make_files_resource()
        file_dict = _make_file_dict(filename="audio.wav")
        mock_http.upload.return_value = _ok_resp({"file": file_dict})

        # Create a real file on disk
        audio_file = tmp_path / "audio.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

        result = files.upload(str(audio_file), purpose="voice_clone")

        assert isinstance(result, FileInfo)
        assert result.file_id == "123456"
        assert result.filename == "audio.wav"
        # Verify _http.upload was called with the right endpoint and purpose
        mock_http.upload.assert_called_once()
        call_args = mock_http.upload.call_args
        assert call_args[0][0] == "/v1/files/upload"  # path
        assert call_args[1]["purpose"] == "voice_clone" or call_args[0][2] == "voice_clone"

    def test_upload_with_binary_io(self):
        """Upload using a BinaryIO object delegates to _http.upload."""
        files, mock_http = _make_files_resource()
        file_dict = _make_file_dict(filename="upload")
        mock_http.upload.return_value = _ok_resp({"file": file_dict})

        bio = io.BytesIO(b"audio data here")
        result = files.upload(bio, purpose="prompt_audio")

        assert isinstance(result, FileInfo)
        assert result.file_id == "123456"
        mock_http.upload.assert_called_once()

    def test_upload_with_invalid_purpose_raises_value_error(self):
        """Upload with an invalid purpose raises ValueError before any HTTP call."""
        files, mock_http = _make_files_resource()

        with pytest.raises(ValueError, match="Invalid upload purpose"):
            files.upload(io.BytesIO(b"data"), purpose="invalid_purpose")

        # No HTTP call should have been made
        mock_http.upload.assert_not_called()


class TestFilesList:
    """Tests for files.list()."""

    def test_list_returns_list_of_file_info(self):
        """files.list() returns a list of FileInfo objects."""
        files, mock_http = _make_files_resource()
        file1 = _make_file_dict(file_id="100", filename="a.wav")
        file2 = _make_file_dict(file_id="200", filename="b.wav")
        mock_http.request.return_value = _ok_resp({"files": [file1, file2]})

        result = files.list(purpose="voice_clone")

        assert len(result) == 2
        assert all(isinstance(f, FileInfo) for f in result)
        assert result[0].file_id == "100"
        assert result[1].file_id == "200"
        mock_http.request.assert_called_once_with(
            "GET", "/v1/files/list", params={"purpose": "voice_clone"}
        )


class TestFilesRetrieve:
    """Tests for files.retrieve()."""

    def test_retrieve_returns_file_info_with_download_url(self):
        """files.retrieve() returns FileInfo with download_url populated."""
        files, mock_http = _make_files_resource()
        file_dict = _make_file_dict(
            file_id="999",
            download_url="https://cdn.minimax.io/files/999?token=abc",
        )
        mock_http.request.return_value = _ok_resp({"file": file_dict})

        result = files.retrieve("999")

        assert isinstance(result, FileInfo)
        assert result.file_id == "999"
        assert result.download_url == "https://cdn.minimax.io/files/999?token=abc"
        mock_http.request.assert_called_once_with(
            "GET", "/v1/files/retrieve", params={"file_id": 999}
        )


class TestFilesDelete:
    """Tests for files.delete()."""

    def test_delete_returns_none(self):
        """files.delete() returns None on success."""
        files, mock_http = _make_files_resource()
        mock_http.request.return_value = _ok_resp({})

        result = files.delete("999", purpose="voice_clone")

        assert result is None
        mock_http.request.assert_called_once_with(
            "POST",
            "/v1/files/delete",
            json={"file_id": 999, "purpose": "voice_clone"},
        )


class TestFilesRetrieveContent:
    """Tests for files.retrieve_content()."""

    def test_retrieve_content_returns_raw_response(self):
        """files.retrieve_content() uses request_bytes for binary data."""
        files, mock_http = _make_files_resource()
        mock_http.request_bytes.return_value = b"raw file content"

        result = files.retrieve_content("42")

        assert result == b"raw file content"
        mock_http.request_bytes.assert_called_once_with(
            "GET", "/v1/files/retrieve_content", params={"file_id": 42}
        )


# ── Async Tests ─────────────────────────────────────────────────────────────

from unittest.mock import AsyncMock

import pytest

from minimax_sdk.resources.files import AsyncFiles


def _make_async_files_resource() -> tuple[AsyncFiles, AsyncMock]:
    """Create an AsyncFiles resource with a mocked AsyncHttpClient."""
    mock_http = AsyncMock()
    files = AsyncFiles(mock_http, client=None)
    return files, mock_http


class TestAsyncFilesUpload:
    """Tests for async files.upload()."""

    @pytest.mark.asyncio
    async def test_upload_with_binary_io(self):
        """Async upload using a BinaryIO object delegates to _http.upload."""
        files, mock_http = _make_async_files_resource()
        file_dict = _make_file_dict(filename="upload")
        mock_http.upload.return_value = _ok_resp({"file": file_dict})

        bio = io.BytesIO(b"audio data here")
        result = await files.upload(bio, purpose="prompt_audio")

        assert isinstance(result, FileInfo)
        assert result.file_id == "123456"
        mock_http.upload.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upload_with_file_path(self, tmp_path):
        """Async upload using a file path string."""
        files, mock_http = _make_async_files_resource()
        file_dict = _make_file_dict(filename="audio.wav")
        mock_http.upload.return_value = _ok_resp({"file": file_dict})

        audio_file = tmp_path / "audio.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

        result = await files.upload(str(audio_file), purpose="voice_clone")

        assert isinstance(result, FileInfo)
        assert result.file_id == "123456"
        mock_http.upload.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upload_with_invalid_purpose_raises_value_error(self):
        """Async upload with an invalid purpose raises ValueError."""
        files, mock_http = _make_async_files_resource()

        with pytest.raises(ValueError, match="Invalid upload purpose"):
            await files.upload(io.BytesIO(b"data"), purpose="bad_purpose")

        mock_http.upload.assert_not_awaited()


class TestAsyncFilesList:
    """Tests for async files.list()."""

    @pytest.mark.asyncio
    async def test_list_returns_list_of_file_info(self):
        """Async files.list() returns a list of FileInfo objects."""
        files, mock_http = _make_async_files_resource()
        file1 = _make_file_dict(file_id="100", filename="a.wav")
        file2 = _make_file_dict(file_id="200", filename="b.wav")
        mock_http.request.return_value = _ok_resp({"files": [file1, file2]})

        result = await files.list(purpose="voice_clone")

        assert len(result) == 2
        assert all(isinstance(f, FileInfo) for f in result)
        assert result[0].file_id == "100"
        assert result[1].file_id == "200"
        mock_http.request.assert_awaited_once_with(
            "GET", "/v1/files/list", params={"purpose": "voice_clone"}
        )


class TestAsyncFilesRetrieve:
    """Tests for async files.retrieve()."""

    @pytest.mark.asyncio
    async def test_retrieve_returns_file_info(self):
        """Async files.retrieve() returns FileInfo with download_url."""
        files, mock_http = _make_async_files_resource()
        file_dict = _make_file_dict(
            file_id="999",
            download_url="https://cdn.minimax.io/files/999?token=abc",
        )
        mock_http.request.return_value = _ok_resp({"file": file_dict})

        result = await files.retrieve("999")

        assert isinstance(result, FileInfo)
        assert result.file_id == "999"
        assert result.download_url == "https://cdn.minimax.io/files/999?token=abc"
        mock_http.request.assert_awaited_once_with(
            "GET", "/v1/files/retrieve", params={"file_id": 999}
        )


class TestAsyncFilesRetrieveContent:
    """Tests for async files.retrieve_content()."""

    @pytest.mark.asyncio
    async def test_retrieve_content_returns_raw_response(self):
        """Async files.retrieve_content() uses request_bytes for binary data."""
        files, mock_http = _make_async_files_resource()
        mock_http.request_bytes.return_value = b"raw content"

        result = await files.retrieve_content("42")

        assert result == b"raw content"
        mock_http.request_bytes.assert_awaited_once_with(
            "GET", "/v1/files/retrieve_content", params={"file_id": 42}
        )


class TestAsyncFilesDelete:
    """Tests for async files.delete()."""

    @pytest.mark.asyncio
    async def test_delete_returns_none(self):
        """Async files.delete() returns None on success."""
        files, mock_http = _make_async_files_resource()
        mock_http.request.return_value = _ok_resp({})

        result = await files.delete("999", purpose="voice_clone")

        assert result is None
        mock_http.request.assert_awaited_once_with(
            "POST",
            "/v1/files/delete",
            json={"file_id": 999, "purpose": "voice_clone"},
        )
