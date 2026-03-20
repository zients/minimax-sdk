"""Tests for minimax_sdk._http — HttpClient and AsyncHttpClient."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from minimax_sdk._http import (
    AsyncHttpClient,
    HttpClient,
    _backoff_delay,
    _parse_error,
    _raise_anthropic_error,
    _raise_for_status,
    _retry_after_seconds,
    _should_retry,
)
from minimax_sdk.exceptions import (
    AuthError,
    InsufficientBalanceError,
    InvalidParameterError,
    MiniMaxError,
    RateLimitError,
    ServerError,
)


# ── Helper function tests ────────────────────────────────────────────────────


class TestParseError:
    def test_extracts_from_base_resp(self) -> None:
        body = {
            "base_resp": {"status_code": 1004, "status_msg": "Auth failed"},
            "trace_id": "tr-123",
        }
        code, msg, trace_id = _parse_error(body)
        assert code == 1004
        assert msg == "Auth failed"
        assert trace_id == "tr-123"

    def test_extracts_from_flat_body(self) -> None:
        body = {"status_code": 1002, "status_msg": "Rate limited", "trace_id": "tr-456"}
        code, msg, trace_id = _parse_error(body)
        assert code == 1002
        assert msg == "Rate limited"
        assert trace_id == "tr-456"

    def test_defaults_when_missing(self) -> None:
        code, msg, trace_id = _parse_error({})
        assert code == 0
        assert msg == ""
        assert trace_id == ""

    def test_trace_id_from_base_resp_fallback(self) -> None:
        body = {"base_resp": {"status_code": 0, "status_msg": "", "trace_id": "inner"}}
        _, _, trace_id = _parse_error(body)
        assert trace_id == "inner"


class TestRaiseForStatus:
    def test_no_raise_on_code_zero(self) -> None:
        _raise_for_status({"base_resp": {"status_code": 0, "status_msg": ""}})

    def test_raises_mapped_exception(self) -> None:
        body = {"base_resp": {"status_code": 1004, "status_msg": "Auth failed"}, "trace_id": "t1"}
        with pytest.raises(AuthError) as exc_info:
            _raise_for_status(body)
        assert exc_info.value.code == 1004

    def test_raises_minimax_error_for_unknown_code(self) -> None:
        body = {"base_resp": {"status_code": 9999, "status_msg": "Unknown"}, "trace_id": "t2"}
        with pytest.raises(MiniMaxError) as exc_info:
            _raise_for_status(body)
        assert exc_info.value.code == 9999


class TestBackoffDelay:
    def test_exponential_backoff(self) -> None:
        assert _backoff_delay(0) == 1.0
        assert _backoff_delay(1) == 2.0
        assert _backoff_delay(2) == 4.0

    def test_custom_base(self) -> None:
        assert _backoff_delay(0, base=0.5) == 0.5
        assert _backoff_delay(2, base=0.5) == 2.0


class TestShouldRetry:
    def test_retryable(self) -> None:
        assert _should_retry(1000) is True
        assert _should_retry(1001) is True
        assert _should_retry(1002) is True

    def test_not_retryable(self) -> None:
        assert _should_retry(1004) is False
        assert _should_retry(9999) is False


class TestRetryAfterSeconds:
    def test_returns_float_when_present(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.headers = {"retry-after": "3.5"}
        assert _retry_after_seconds(response) == 3.5

    def test_returns_none_when_absent(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.headers = {}
        assert _retry_after_seconds(response) is None

    def test_returns_none_on_invalid_value(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.headers = {"retry-after": "not-a-number"}
        assert _retry_after_seconds(response) is None


# ── HttpClient constructor ───────────────────────────────────────────────────


class TestHttpClientConstructor:
    def test_sets_attributes(self) -> None:
        client = HttpClient(api_key="sk-key", base_url="https://example.com/", max_retries=5)
        assert client._api_key == "sk-key"
        assert client.base_url == "https://example.com"  # trailing slash stripped
        assert client.max_retries == 5
        client.close()

    def test_default_timeout_is_applied(self) -> None:
        client = HttpClient(api_key="sk-key")
        timeout = client._client.timeout
        assert timeout.connect == 5.0
        assert timeout.read == 600.0
        assert timeout.write == 600.0
        assert timeout.pool == 600.0
        client.close()

    def test_custom_timeout(self) -> None:
        custom = httpx.Timeout(connect=1.0, read=2.0, write=3.0, pool=4.0)
        client = HttpClient(api_key="sk-key", timeout=custom)
        assert client._client.timeout.connect == 1.0
        assert client._client.timeout.read == 2.0
        client.close()

    def test_default_base_url(self) -> None:
        client = HttpClient(api_key="sk-key")
        assert client.base_url == "https://api.minimax.io"
        client.close()

    def test_default_max_retries(self) -> None:
        client = HttpClient(api_key="sk-key")
        assert client.max_retries == 2
        client.close()


# ── HttpClient.request() ─────────────────────────────────────────────────────


def _make_httpx_response(body: dict[str, Any], headers: dict[str, str] | None = None) -> MagicMock:
    """Build a fake httpx.Response with .json() returning *body*."""
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = body
    resp.headers = headers or {}
    return resp


class TestHttpClientRequest:
    def test_success_returns_body(self) -> None:
        client = HttpClient(api_key="sk-key")
        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}, "data": "ok"}
        client._client.request = MagicMock(return_value=_make_httpx_response(success_body))

        result = client.request("GET", "/v1/test")

        assert result == success_body
        client._client.request.assert_called_once_with("GET", "/v1/test")
        client.close()

    def test_error_raises_mapped_exception(self) -> None:
        client = HttpClient(api_key="sk-key", max_retries=0)
        error_body = {
            "base_resp": {"status_code": 1004, "status_msg": "Unauthorized"},
            "trace_id": "tr-err",
        }
        client._client.request = MagicMock(return_value=_make_httpx_response(error_body))

        with pytest.raises(AuthError) as exc_info:
            client.request("POST", "/v1/test")
        assert exc_info.value.code == 1004
        client.close()

    @patch("minimax_sdk._http.time.sleep", return_value=None)
    def test_retry_on_retryable_code(self, mock_sleep: MagicMock) -> None:
        client = HttpClient(api_key="sk-key", max_retries=2)

        retryable_body = {
            "base_resp": {"status_code": 1000, "status_msg": "Server error"},
            "trace_id": "tr-retry",
        }
        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}, "data": "ok"}

        client._client.request = MagicMock(
            side_effect=[
                _make_httpx_response(retryable_body),
                _make_httpx_response(success_body),
            ]
        )

        result = client.request("GET", "/v1/test")
        assert result == success_body
        assert client._client.request.call_count == 2
        mock_sleep.assert_called_once()
        client.close()

    @patch("minimax_sdk._http.time.sleep", return_value=None)
    def test_retry_after_header_honored_for_1002(self, mock_sleep: MagicMock) -> None:
        client = HttpClient(api_key="sk-key", max_retries=2)

        rate_limit_body = {
            "base_resp": {"status_code": 1002, "status_msg": "Rate limited"},
            "trace_id": "",
        }
        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}}

        client._client.request = MagicMock(
            side_effect=[
                _make_httpx_response(rate_limit_body, headers={"retry-after": "7.0"}),
                _make_httpx_response(success_body),
            ]
        )

        result = client.request("GET", "/v1/test")
        assert result == success_body
        # Should have slept for the Retry-After value (7.0), not the default backoff
        mock_sleep.assert_called_once_with(7.0)
        client.close()

    @patch("minimax_sdk._http.time.sleep", return_value=None)
    def test_retry_1002_falls_through_to_backoff_without_retry_after(
        self, mock_sleep: MagicMock
    ) -> None:
        client = HttpClient(api_key="sk-key", max_retries=2)

        rate_limit_body = {
            "base_resp": {"status_code": 1002, "status_msg": "Rate limited"},
            "trace_id": "",
        }
        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}}

        client._client.request = MagicMock(
            side_effect=[
                _make_httpx_response(rate_limit_body),  # no Retry-After header
                _make_httpx_response(success_body),
            ]
        )

        result = client.request("GET", "/v1/test")
        assert result == success_body
        # Falls through to normal backoff (attempt=0 => 1.0s)
        mock_sleep.assert_called_once_with(1.0)
        client.close()

    @patch("minimax_sdk._http.time.sleep", return_value=None)
    def test_max_retries_exceeded_raises(self, mock_sleep: MagicMock) -> None:
        client = HttpClient(api_key="sk-key", max_retries=1)

        retryable_body = {
            "base_resp": {"status_code": 1000, "status_msg": "Server error"},
            "trace_id": "tr-max",
        }

        client._client.request = MagicMock(
            side_effect=[
                _make_httpx_response(retryable_body),
                _make_httpx_response(retryable_body),
            ]
        )

        with pytest.raises(ServerError) as exc_info:
            client.request("GET", "/v1/test")
        assert exc_info.value.code == 1000
        assert client._client.request.call_count == 2
        client.close()

    @patch("minimax_sdk._http.time.sleep", return_value=None)
    def test_http_transport_error_retries_then_raises(self, mock_sleep: MagicMock) -> None:
        client = HttpClient(api_key="sk-key", max_retries=1)

        client._client.request = MagicMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with pytest.raises(MiniMaxError, match="HTTP transport error"):
            client.request("GET", "/v1/test")
        # Should have attempted max_retries + 1 = 2 times
        assert client._client.request.call_count == 2
        client.close()

    @patch("minimax_sdk._http.time.sleep", return_value=None)
    def test_http_transport_error_recovers_on_retry(self, mock_sleep: MagicMock) -> None:
        client = HttpClient(api_key="sk-key", max_retries=2)

        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}, "data": "ok"}
        client._client.request = MagicMock(
            side_effect=[
                httpx.ConnectError("Connection refused"),
                _make_httpx_response(success_body),
            ]
        )

        result = client.request("GET", "/v1/test")
        assert result == success_body
        assert client._client.request.call_count == 2
        client.close()

    def test_non_retryable_error_raises_immediately(self) -> None:
        client = HttpClient(api_key="sk-key", max_retries=3)
        error_body = {
            "base_resp": {"status_code": 1004, "status_msg": "Unauthorized"},
            "trace_id": "tr-noretry",
        }
        client._client.request = MagicMock(return_value=_make_httpx_response(error_body))

        with pytest.raises(AuthError):
            client.request("GET", "/v1/test")
        # Only called once — no retries for non-retryable codes
        assert client._client.request.call_count == 1
        client.close()


# ── HttpClient.upload() ──────────────────────────────────────────────────────


class TestHttpClientUpload:
    def test_upload_from_file_path(self, tmp_path: Path) -> None:
        client = HttpClient(api_key="sk-key")

        # Create a temp file
        test_file = tmp_path / "audio.wav"
        test_file.write_bytes(b"fake audio data")

        success_body = {
            "base_resp": {"status_code": 0, "status_msg": ""},
            "file": {"file_id": "file-123"},
        }
        client._client.request = MagicMock(return_value=_make_httpx_response(success_body))

        result = client.upload("/v1/files/upload", str(test_file), purpose="voice_clone")
        assert result["file"]["file_id"] == "file-123"

        # Verify POST was called with files and data kwargs
        call_args = client._client.request.call_args
        assert call_args[0] == ("POST", "/v1/files/upload")
        assert "files" in call_args[1]
        assert "data" in call_args[1]
        assert call_args[1]["data"] == {"purpose": "voice_clone"}
        client.close()

    def test_upload_from_path_object(self, tmp_path: Path) -> None:
        client = HttpClient(api_key="sk-key")

        test_file = tmp_path / "audio.wav"
        test_file.write_bytes(b"fake audio data")

        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}}
        client._client.request = MagicMock(return_value=_make_httpx_response(success_body))

        result = client.upload("/v1/files/upload", Path(test_file), purpose="prompt_audio")
        assert result == success_body
        client.close()

    def test_upload_from_file_object(self) -> None:
        client = HttpClient(api_key="sk-key")

        file_obj = io.BytesIO(b"fake data")
        file_obj.name = "/some/path/test.wav"

        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}}
        client._client.request = MagicMock(return_value=_make_httpx_response(success_body))

        result = client.upload("/v1/files/upload", file_obj, purpose="voice_clone")
        assert result == success_body

        call_args = client._client.request.call_args
        files_kwarg = call_args[1]["files"]
        assert files_kwarg["file"][0] == "test.wav"  # basename extracted
        client.close()

    def test_upload_from_file_object_without_name(self) -> None:
        client = HttpClient(api_key="sk-key")

        file_obj = io.BytesIO(b"fake data")
        # No .name attribute → should default to "upload"

        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}}
        client._client.request = MagicMock(return_value=_make_httpx_response(success_body))

        result = client.upload("/v1/files/upload", file_obj, purpose="voice_clone")
        assert result == success_body

        call_args = client._client.request.call_args
        files_kwarg = call_args[1]["files"]
        assert files_kwarg["file"][0] == "upload"
        client.close()

    def test_upload_from_file_object_with_path_name(self) -> None:
        """When file.name is a Path object, it should be converted to just the name."""
        client = HttpClient(api_key="sk-key")

        file_obj = io.BytesIO(b"fake data")
        file_obj.name = Path("/some/dir/recording.mp3")

        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}}
        client._client.request = MagicMock(return_value=_make_httpx_response(success_body))

        result = client.upload("/v1/files/upload", file_obj, purpose="voice_clone")
        assert result == success_body

        call_args = client._client.request.call_args
        files_kwarg = call_args[1]["files"]
        assert files_kwarg["file"][0] == "recording.mp3"
        client.close()


# ── HttpClient context manager ───────────────────────────────────────────────


class TestHttpClientContextManager:
    def test_enter_exit(self) -> None:
        client = HttpClient(api_key="sk-key")
        with client as c:
            assert c is client
        # After __exit__, the underlying httpx client should be closed.
        # Calling close again shouldn't fail.

    def test_with_statement(self) -> None:
        with HttpClient(api_key="sk-key") as client:
            assert isinstance(client, HttpClient)
            assert client._api_key == "sk-key"


# ── AsyncHttpClient constructor ──────────────────────────────────────────────


class TestAsyncHttpClientConstructor:
    def test_sets_attributes(self) -> None:
        client = AsyncHttpClient(api_key="sk-async", base_url="https://async.io/", max_retries=3)
        assert client._api_key == "sk-async"
        assert client.base_url == "https://async.io"
        assert client.max_retries == 3

    def test_default_timeout(self) -> None:
        client = AsyncHttpClient(api_key="sk-async")
        timeout = client._client.timeout
        assert timeout.connect == 5.0
        assert timeout.read == 600.0

    def test_custom_timeout(self) -> None:
        custom = httpx.Timeout(connect=10.0, read=20.0, write=30.0, pool=40.0)
        client = AsyncHttpClient(api_key="sk-async", timeout=custom)
        assert client._client.timeout.connect == 10.0


# ── AsyncHttpClient.request() ────────────────────────────────────────────────


class TestAsyncHttpClientRequest:
    @pytest.mark.asyncio
    async def test_success_returns_body(self) -> None:
        client = AsyncHttpClient(api_key="sk-key")
        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}, "data": "ok"}

        mock_response = _make_httpx_response(success_body)
        client._client.request = AsyncMock(return_value=mock_response)

        result = await client.request("GET", "/v1/test")
        assert result == success_body
        await client.close()

    @pytest.mark.asyncio
    async def test_error_raises_mapped_exception(self) -> None:
        client = AsyncHttpClient(api_key="sk-key", max_retries=0)
        error_body = {
            "base_resp": {"status_code": 1004, "status_msg": "Unauthorized"},
            "trace_id": "tr-async-err",
        }
        client._client.request = AsyncMock(return_value=_make_httpx_response(error_body))

        with pytest.raises(AuthError) as exc_info:
            await client.request("POST", "/v1/test")
        assert exc_info.value.code == 1004
        await client.close()

    @pytest.mark.asyncio
    @patch("minimax_sdk._http.asyncio.sleep", new_callable=AsyncMock)
    async def test_retry_on_retryable_code(self, mock_sleep: AsyncMock) -> None:
        client = AsyncHttpClient(api_key="sk-key", max_retries=2)

        retryable_body = {
            "base_resp": {"status_code": 1000, "status_msg": "Server error"},
            "trace_id": "",
        }
        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}}

        client._client.request = AsyncMock(
            side_effect=[
                _make_httpx_response(retryable_body),
                _make_httpx_response(success_body),
            ]
        )

        result = await client.request("GET", "/v1/test")
        assert result == success_body
        assert client._client.request.call_count == 2
        mock_sleep.assert_called_once()
        await client.close()

    @pytest.mark.asyncio
    @patch("minimax_sdk._http.asyncio.sleep", new_callable=AsyncMock)
    async def test_retry_after_header_honored(self, mock_sleep: AsyncMock) -> None:
        client = AsyncHttpClient(api_key="sk-key", max_retries=2)

        rate_body = {
            "base_resp": {"status_code": 1002, "status_msg": "Rate limited"},
            "trace_id": "",
        }
        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}}

        client._client.request = AsyncMock(
            side_effect=[
                _make_httpx_response(rate_body, headers={"retry-after": "5.0"}),
                _make_httpx_response(success_body),
            ]
        )

        result = await client.request("GET", "/v1/test")
        assert result == success_body
        mock_sleep.assert_called_once_with(5.0)
        await client.close()

    @pytest.mark.asyncio
    @patch("minimax_sdk._http.asyncio.sleep", new_callable=AsyncMock)
    async def test_retry_1002_without_retry_after_uses_backoff(
        self, mock_sleep: AsyncMock
    ) -> None:
        client = AsyncHttpClient(api_key="sk-key", max_retries=2)

        rate_body = {
            "base_resp": {"status_code": 1002, "status_msg": "Rate limited"},
            "trace_id": "",
        }
        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}}

        client._client.request = AsyncMock(
            side_effect=[
                _make_httpx_response(rate_body),  # no Retry-After
                _make_httpx_response(success_body),
            ]
        )

        result = await client.request("GET", "/v1/test")
        assert result == success_body
        mock_sleep.assert_called_once_with(1.0)  # backoff(0)
        await client.close()

    @pytest.mark.asyncio
    @patch("minimax_sdk._http.asyncio.sleep", new_callable=AsyncMock)
    async def test_max_retries_exceeded_raises(self, mock_sleep: AsyncMock) -> None:
        client = AsyncHttpClient(api_key="sk-key", max_retries=1)

        retryable_body = {
            "base_resp": {"status_code": 1000, "status_msg": "Server error"},
            "trace_id": "tr-async-max",
        }

        client._client.request = AsyncMock(
            side_effect=[
                _make_httpx_response(retryable_body),
                _make_httpx_response(retryable_body),
            ]
        )

        with pytest.raises(ServerError):
            await client.request("GET", "/v1/test")
        assert client._client.request.call_count == 2
        await client.close()

    @pytest.mark.asyncio
    @patch("minimax_sdk._http.asyncio.sleep", new_callable=AsyncMock)
    async def test_http_error_retries_then_raises(self, mock_sleep: AsyncMock) -> None:
        client = AsyncHttpClient(api_key="sk-key", max_retries=1)

        client._client.request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with pytest.raises(MiniMaxError, match="HTTP transport error"):
            await client.request("GET", "/v1/test")
        assert client._client.request.call_count == 2
        await client.close()

    @pytest.mark.asyncio
    @patch("minimax_sdk._http.asyncio.sleep", new_callable=AsyncMock)
    async def test_http_error_recovers_on_retry(self, mock_sleep: AsyncMock) -> None:
        client = AsyncHttpClient(api_key="sk-key", max_retries=2)

        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}}
        client._client.request = AsyncMock(
            side_effect=[
                httpx.ConnectError("Connection refused"),
                _make_httpx_response(success_body),
            ]
        )

        result = await client.request("GET", "/v1/test")
        assert result == success_body
        await client.close()

    @pytest.mark.asyncio
    async def test_non_retryable_error_raises_immediately(self) -> None:
        client = AsyncHttpClient(api_key="sk-key", max_retries=3)
        error_body = {
            "base_resp": {"status_code": 1004, "status_msg": "Unauthorized"},
            "trace_id": "",
        }
        client._client.request = AsyncMock(return_value=_make_httpx_response(error_body))

        with pytest.raises(AuthError):
            await client.request("GET", "/v1/test")
        assert client._client.request.call_count == 1
        await client.close()


# ── AsyncHttpClient.upload() ─────────────────────────────────────────────────


class TestAsyncHttpClientUpload:
    @pytest.mark.asyncio
    async def test_upload_from_file_path(self, tmp_path: Path) -> None:
        client = AsyncHttpClient(api_key="sk-key")

        test_file = tmp_path / "audio.wav"
        test_file.write_bytes(b"fake audio data")

        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}}
        client._client.request = AsyncMock(return_value=_make_httpx_response(success_body))

        result = await client.upload("/v1/files/upload", str(test_file), purpose="voice_clone")
        assert result == success_body
        await client.close()

    @pytest.mark.asyncio
    async def test_upload_from_path_object(self, tmp_path: Path) -> None:
        client = AsyncHttpClient(api_key="sk-key")

        test_file = tmp_path / "audio.wav"
        test_file.write_bytes(b"fake audio")

        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}}
        client._client.request = AsyncMock(return_value=_make_httpx_response(success_body))

        result = await client.upload("/v1/files/upload", Path(test_file), purpose="prompt_audio")
        assert result == success_body
        await client.close()

    @pytest.mark.asyncio
    async def test_upload_from_file_object(self) -> None:
        client = AsyncHttpClient(api_key="sk-key")

        file_obj = io.BytesIO(b"fake data")
        file_obj.name = "/some/path/test.wav"

        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}}
        client._client.request = AsyncMock(return_value=_make_httpx_response(success_body))

        result = await client.upload("/v1/files/upload", file_obj, purpose="voice_clone")
        assert result == success_body
        await client.close()

    @pytest.mark.asyncio
    async def test_upload_from_file_object_without_name(self) -> None:
        client = AsyncHttpClient(api_key="sk-key")

        file_obj = io.BytesIO(b"fake data")

        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}}
        client._client.request = AsyncMock(return_value=_make_httpx_response(success_body))

        result = await client.upload("/v1/files/upload", file_obj, purpose="voice_clone")
        assert result == success_body
        await client.close()

    @pytest.mark.asyncio
    async def test_upload_from_file_object_with_path_name(self) -> None:
        client = AsyncHttpClient(api_key="sk-key")

        file_obj = io.BytesIO(b"fake data")
        file_obj.name = Path("/dir/rec.mp3")

        success_body = {"base_resp": {"status_code": 0, "status_msg": ""}}
        client._client.request = AsyncMock(return_value=_make_httpx_response(success_body))

        result = await client.upload("/v1/files/upload", file_obj, purpose="voice_clone")
        assert result == success_body
        await client.close()


# ── AsyncHttpClient context manager ──────────────────────────────────────────


class TestAsyncHttpClientContextManager:
    @pytest.mark.asyncio
    async def test_aenter_aexit(self) -> None:
        client = AsyncHttpClient(api_key="sk-key")
        async with client as c:
            assert c is client

    @pytest.mark.asyncio
    async def test_async_with_statement(self) -> None:
        async with AsyncHttpClient(api_key="sk-key") as client:
            assert isinstance(client, AsyncHttpClient)
            assert client._api_key == "sk-key"


# ── Edge cases: unreachable fallback paths ────────────────────────────────────


class TestHttpClientFallbackPaths:
    """Cover the final fallback raises at the end of request() loops."""

    @patch("minimax_sdk._http.time.sleep", return_value=None)
    def test_last_exc_fallback_after_transport_errors(self, mock_sleep: MagicMock) -> None:
        """When all retries are transport errors, the final MiniMaxError is raised from last_exc."""
        client = HttpClient(api_key="sk-key", max_retries=1)
        client._client.request = MagicMock(
            side_effect=httpx.ConnectError("fail")
        )
        with pytest.raises(MiniMaxError, match="HTTP transport error"):
            client.request("GET", "/v1/test")
        client.close()

    def test_zero_iterations_unknown_error_fallback(self) -> None:
        """When max_retries=-1, the loop body never executes and the final fallback raises."""
        client = HttpClient(api_key="sk-key", max_retries=-1)
        with pytest.raises(MiniMaxError, match="Request failed with unknown error"):
            client.request("GET", "/v1/test")
        client.close()

    @patch("minimax_sdk._http.time.sleep", return_value=None)
    def test_post_loop_unknown_error_fallback(self, mock_sleep: MagicMock) -> None:
        """Cover the post-loop 'unknown error' path by patching _raise_for_status to no-op."""
        client = HttpClient(api_key="sk-key", max_retries=0)
        retryable_body = {
            "base_resp": {"status_code": 1000, "status_msg": "Server error"},
            "trace_id": "",
        }
        client._client.request = MagicMock(
            return_value=_make_httpx_response(retryable_body)
        )
        # Patch _raise_for_status to be a no-op, letting the loop exit without raising.
        # last_exc is None, so we hit the "Request failed with unknown error" line.
        with patch("minimax_sdk._http._raise_for_status", return_value=None):
            with pytest.raises(MiniMaxError, match="Request failed with unknown error"):
                client.request("GET", "/v1/test")
        client.close()

    @patch("minimax_sdk._http.time.sleep", return_value=None)
    def test_post_loop_last_exc_fallback(self, mock_sleep: MagicMock) -> None:
        """Cover the post-loop 'last_exc is not None' path.

        First attempt: transport error -> sets last_exc, continues (attempt 0 < max_retries 1).
        Second attempt: API error with _raise_for_status patched to no-op -> loop exits normally.
        Post-loop: last_exc is not None -> raises MiniMaxError with 'Request failed after'.
        """
        client = HttpClient(api_key="sk-key", max_retries=1)
        retryable_body = {
            "base_resp": {"status_code": 1000, "status_msg": "Server error"},
            "trace_id": "",
        }
        client._client.request = MagicMock(
            side_effect=[
                httpx.ConnectError("Connection refused"),
                _make_httpx_response(retryable_body),
            ]
        )
        with patch("minimax_sdk._http._raise_for_status", return_value=None):
            with pytest.raises(MiniMaxError, match="Request failed after"):
                client.request("GET", "/v1/test")
        client.close()


class TestAsyncHttpClientFallbackPaths:
    @pytest.mark.asyncio
    @patch("minimax_sdk._http.asyncio.sleep", new_callable=AsyncMock)
    async def test_last_exc_fallback(self, mock_sleep: AsyncMock) -> None:
        client = AsyncHttpClient(api_key="sk-key", max_retries=1)
        client._client.request = AsyncMock(
            side_effect=httpx.ConnectError("fail")
        )
        with pytest.raises(MiniMaxError, match="HTTP transport error"):
            await client.request("GET", "/v1/test")
        await client.close()

    @pytest.mark.asyncio
    async def test_zero_iterations_unknown_error_fallback(self) -> None:
        """When max_retries=-1, the loop body never executes and the final fallback raises."""
        client = AsyncHttpClient(api_key="sk-key", max_retries=-1)
        with pytest.raises(MiniMaxError, match="Request failed with unknown error"):
            await client.request("GET", "/v1/test")
        await client.close()

    @pytest.mark.asyncio
    @patch("minimax_sdk._http.asyncio.sleep", new_callable=AsyncMock)
    async def test_post_loop_unknown_error_fallback(self, mock_sleep: AsyncMock) -> None:
        """Cover the post-loop 'unknown error' path by patching _raise_for_status to no-op."""
        client = AsyncHttpClient(api_key="sk-key", max_retries=0)
        retryable_body = {
            "base_resp": {"status_code": 1000, "status_msg": "Server error"},
            "trace_id": "",
        }
        client._client.request = AsyncMock(
            return_value=_make_httpx_response(retryable_body)
        )
        with patch("minimax_sdk._http._raise_for_status", return_value=None):
            with pytest.raises(MiniMaxError, match="Request failed with unknown error"):
                await client.request("GET", "/v1/test")
        await client.close()

    @pytest.mark.asyncio
    @patch("minimax_sdk._http.asyncio.sleep", new_callable=AsyncMock)
    async def test_post_loop_last_exc_fallback(self, mock_sleep: AsyncMock) -> None:
        """Cover the post-loop 'last_exc is not None' path in async.

        First attempt: transport error -> sets last_exc, continues.
        Second attempt: API error with _raise_for_status patched to no-op -> loop exits.
        Post-loop: last_exc is not None -> raises MiniMaxError with 'Request failed after'.
        """
        client = AsyncHttpClient(api_key="sk-key", max_retries=1)
        retryable_body = {
            "base_resp": {"status_code": 1000, "status_msg": "Server error"},
            "trace_id": "",
        }
        client._client.request = AsyncMock(
            side_effect=[
                httpx.ConnectError("Connection refused"),
                _make_httpx_response(retryable_body),
            ]
        )
        with patch("minimax_sdk._http._raise_for_status", return_value=None):
            with pytest.raises(MiniMaxError, match="Request failed after"):
                await client.request("GET", "/v1/test")
        await client.close()


# ── Sync request_bytes tests ─────────────────────────────────────────────────


class TestRequestBytes:
    """Tests for HttpClient.request_bytes()."""

    def test_returns_binary_content(self):
        """request_bytes returns raw bytes for non-JSON response."""
        client = HttpClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.content = b"\xff\xfb\x90\x04" * 100
        mock_response.headers = {"content-type": "audio/mpeg"}
        mock_response.raise_for_status = MagicMock()
        client._client = MagicMock()
        client._client.request.return_value = mock_response

        result = client.request_bytes("GET", "/v1/files/retrieve_content")
        assert result == b"\xff\xfb\x90\x04" * 100

    def test_raises_on_json_error(self):
        """request_bytes raises MiniMaxError when response is JSON with error."""
        client = HttpClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "base_resp": {"status_code": 2013, "status_msg": "invalid param"},
        }
        mock_response.raise_for_status = MagicMock()
        client._client = MagicMock()
        client._client.request.return_value = mock_response

        from minimax_sdk.exceptions import InvalidParameterError

        with pytest.raises(InvalidParameterError):
            client.request_bytes("GET", "/v1/files/retrieve_content")


# ── Sync stream_request tests ────────────────────────────────────────────────


class TestStreamRequest:
    """Tests for HttpClient.stream_request()."""

    def test_yields_lines(self):
        """stream_request yields response lines."""
        client = HttpClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "text/event-stream"}
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_lines.return_value = iter(["line1", "line2", "line3"])

        from contextlib import contextmanager

        @contextmanager
        def mock_stream(*args, **kwargs):
            yield mock_response

        client._client = MagicMock()
        client._client.stream = mock_stream

        lines = list(client.stream_request("POST", "/v1/t2a_v2"))
        assert lines == ["line1", "line2", "line3"]

    def test_raises_on_json_error(self):
        """stream_request raises MiniMaxError when response is JSON error."""
        client = HttpClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "base_resp": {"status_code": 1002, "status_msg": "rate limit"},
        }

        from contextlib import contextmanager

        @contextmanager
        def mock_stream(*args, **kwargs):
            yield mock_response

        client._client = MagicMock()
        client._client.stream = mock_stream

        with pytest.raises(RateLimitError):
            list(client.stream_request("POST", "/v1/t2a_v2"))


# ── Async request_bytes tests ────────────────────────────────────────────────


class TestAsyncRequestBytes:
    """Tests for AsyncHttpClient.request_bytes()."""

    @pytest.mark.asyncio
    async def test_returns_binary_content(self):
        """async request_bytes returns raw bytes."""
        client = AsyncHttpClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.content = b"audio data"
        mock_response.headers = {"content-type": "audio/mpeg"}
        mock_response.raise_for_status = MagicMock()
        client._client = AsyncMock()
        client._client.request.return_value = mock_response

        result = await client.request_bytes("GET", "/v1/files/retrieve_content")
        assert result == b"audio data"

    @pytest.mark.asyncio
    async def test_raises_on_json_error(self):
        """async request_bytes raises on JSON error response."""
        client = AsyncHttpClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "base_resp": {"status_code": 1004, "status_msg": "auth failed"},
        }
        mock_response.raise_for_status = MagicMock()
        client._client = AsyncMock()
        client._client.request.return_value = mock_response

        with pytest.raises(AuthError):
            await client.request_bytes("GET", "/v1/files/retrieve_content")


# ── Async stream_request tests ───────────────────────────────────────────────


class TestAsyncStreamRequest:
    """Tests for AsyncHttpClient.stream_request()."""

    @pytest.mark.asyncio
    async def test_yields_lines(self):
        """async stream_request yields response lines."""
        client = AsyncHttpClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "text/event-stream"}
        mock_response.raise_for_status = MagicMock()

        async def mock_aiter_lines():
            for line in ["line1", "line2"]:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        class AsyncStreamCM:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *args):
                pass

        client._client = MagicMock()
        client._client.stream.return_value = AsyncStreamCM()

        lines = []
        async for line in client.stream_request("POST", "/v1/t2a_v2"):
            lines.append(line)
        assert lines == ["line1", "line2"]

    @pytest.mark.asyncio
    async def test_raises_on_json_error(self):
        """async stream_request raises on JSON error response."""
        client = AsyncHttpClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "base_resp": {"status_code": 1008, "status_msg": "insufficient balance"},
        }

        class AsyncStreamCM:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *args):
                pass

        client._client = MagicMock()
        client._client.stream.return_value = AsyncStreamCM()

        from minimax_sdk.exceptions import InsufficientBalanceError

        with pytest.raises(InsufficientBalanceError):
            async for _ in client.stream_request("POST", "/v1/t2a_v2"):
                pass


# ── _raise_anthropic_error helper ────────────────────────────────────────────


class TestRaiseAnthropicError:
    def test_authentication_error(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 401
        body = {
            "type": "error",
            "error": {"type": "authentication_error", "message": "Invalid API key"},
            "request_id": "req_123",
        }
        with pytest.raises(AuthError) as exc_info:
            _raise_anthropic_error(response, body)
        assert exc_info.value.code == 401
        assert "Invalid API key" in exc_info.value.message
        assert exc_info.value.trace_id == "req_123"

    def test_rate_limit_error(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 429
        body = {
            "type": "error",
            "error": {"type": "rate_limit_error", "message": "Rate limited"},
        }
        with pytest.raises(RateLimitError) as exc_info:
            _raise_anthropic_error(response, body)
        assert exc_info.value.code == 429

    def test_invalid_request_error(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 400
        body = {
            "type": "error",
            "error": {"type": "invalid_request_error", "message": "Bad param"},
        }
        with pytest.raises(InvalidParameterError):
            _raise_anthropic_error(response, body)

    def test_billing_error(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 402
        body = {
            "type": "error",
            "error": {"type": "billing_error", "message": "No payment"},
        }
        with pytest.raises(InsufficientBalanceError):
            _raise_anthropic_error(response, body)

    def test_server_error(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 500
        body = {
            "type": "error",
            "error": {"type": "api_error", "message": "Internal error"},
        }
        with pytest.raises(ServerError):
            _raise_anthropic_error(response, body)

    def test_overloaded_error(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 529
        body = {
            "type": "error",
            "error": {"type": "overloaded_error", "message": "Overloaded"},
        }
        with pytest.raises(ServerError):
            _raise_anthropic_error(response, body)

    def test_unknown_error_type_falls_back(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 418
        body = {
            "type": "error",
            "error": {"type": "unknown_future_error", "message": "New error"},
        }
        with pytest.raises(MiniMaxError):
            _raise_anthropic_error(response, body)

    def test_missing_request_id(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 400
        body = {
            "type": "error",
            "error": {"type": "invalid_request_error", "message": "Bad"},
        }
        with pytest.raises(InvalidParameterError) as exc_info:
            _raise_anthropic_error(response, body)
        assert exc_info.value.trace_id == ""


# ── HttpClient.request_anthropic() ──────────────────────────────────────────


class TestHttpClientRequestAnthropic:
    def test_success_returns_body(self) -> None:
        client = HttpClient(api_key="sk-key")
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "msg_001",
            "type": "message",
            "content": [{"type": "text", "text": "Hello"}],
        }
        client._client = MagicMock()
        client._client.request.return_value = mock_response

        result = client.request_anthropic("POST", "/anthropic/v1/messages", json={})

        assert result["id"] == "msg_001"
        assert result["content"][0]["text"] == "Hello"

    def test_auth_error_raises(self) -> None:
        client = HttpClient(api_key="sk-key")
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_response.json.return_value = {
            "type": "error",
            "error": {"type": "authentication_error", "message": "Invalid key"},
            "request_id": "req_001",
        }
        client._client = MagicMock()
        client._client.request.return_value = mock_response

        with pytest.raises(AuthError) as exc_info:
            client.request_anthropic("POST", "/anthropic/v1/messages", json={})
        assert exc_info.value.code == 401

    def test_rate_limit_retries(self) -> None:
        client = HttpClient(api_key="sk-key", max_retries=1)

        rate_limit_resp = MagicMock(spec=httpx.Response)
        rate_limit_resp.status_code = 429
        rate_limit_resp.headers = {"retry-after": "0.01"}
        rate_limit_resp.json.return_value = {
            "type": "error",
            "error": {"type": "rate_limit_error", "message": "Rate limited"},
        }

        success_resp = MagicMock(spec=httpx.Response)
        success_resp.status_code = 200
        success_resp.json.return_value = {"id": "msg_002", "type": "message", "content": []}

        client._client = MagicMock()
        client._client.request.side_effect = [rate_limit_resp, success_resp]

        result = client.request_anthropic("POST", "/anthropic/v1/messages", json={})
        assert result["id"] == "msg_002"
        assert client._client.request.call_count == 2

    def test_server_error_retries(self) -> None:
        client = HttpClient(api_key="sk-key", max_retries=1)

        error_resp = MagicMock(spec=httpx.Response)
        error_resp.status_code = 500
        error_resp.headers = {}
        error_resp.json.return_value = {
            "type": "error",
            "error": {"type": "api_error", "message": "Internal"},
        }

        success_resp = MagicMock(spec=httpx.Response)
        success_resp.status_code = 200
        success_resp.json.return_value = {"id": "msg_003", "type": "message", "content": []}

        client._client = MagicMock()
        client._client.request.side_effect = [error_resp, success_resp]

        result = client.request_anthropic("POST", "/anthropic/v1/messages", json={})
        assert result["id"] == "msg_003"

    def test_retries_exhausted_raises(self) -> None:
        client = HttpClient(api_key="sk-key", max_retries=1)

        error_resp = MagicMock(spec=httpx.Response)
        error_resp.status_code = 500
        error_resp.headers = {}
        error_resp.json.return_value = {
            "type": "error",
            "error": {"type": "api_error", "message": "Still broken"},
        }

        client._client = MagicMock()
        client._client.request.return_value = error_resp

        with pytest.raises(ServerError):
            client.request_anthropic("POST", "/anthropic/v1/messages", json={})

    def test_non_retryable_error_raises_immediately(self) -> None:
        client = HttpClient(api_key="sk-key", max_retries=2)

        error_resp = MagicMock(spec=httpx.Response)
        error_resp.status_code = 400
        error_resp.json.return_value = {
            "type": "error",
            "error": {"type": "invalid_request_error", "message": "Bad request"},
        }

        client._client = MagicMock()
        client._client.request.return_value = error_resp

        with pytest.raises(InvalidParameterError):
            client.request_anthropic("POST", "/anthropic/v1/messages", json={})
        # Should not retry 400 errors
        assert client._client.request.call_count == 1

    def test_transport_error_retries(self) -> None:
        client = HttpClient(api_key="sk-key", max_retries=1)

        success_resp = MagicMock(spec=httpx.Response)
        success_resp.status_code = 200
        success_resp.json.return_value = {"id": "msg_004", "type": "message", "content": []}

        client._client = MagicMock()
        client._client.request.side_effect = [
            httpx.ConnectError("Connection refused"),
            success_resp,
        ]

        result = client.request_anthropic("POST", "/anthropic/v1/messages", json={})
        assert result["id"] == "msg_004"

    def test_transport_error_exhausted(self) -> None:
        client = HttpClient(api_key="sk-key", max_retries=0)

        client._client = MagicMock()
        client._client.request.side_effect = httpx.ConnectError("Connection refused")

        with pytest.raises(MiniMaxError, match="HTTP transport error"):
            client.request_anthropic("POST", "/anthropic/v1/messages", json={})

    def test_non_json_error_response(self) -> None:
        client = HttpClient(api_key="sk-key", max_retries=0)

        error_resp = MagicMock(spec=httpx.Response)
        error_resp.status_code = 502
        error_resp.text = "Bad Gateway"
        error_resp.json.side_effect = ValueError("No JSON")

        client._client = MagicMock()
        client._client.request.return_value = error_resp

        with pytest.raises(MiniMaxError, match="HTTP 502"):
            client.request_anthropic("POST", "/anthropic/v1/messages", json={})


# ── AsyncHttpClient.request_anthropic() ─────────────────────────────────────


class TestAsyncHttpClientRequestAnthropic:
    @pytest.mark.asyncio
    async def test_success_returns_body(self) -> None:
        client = AsyncHttpClient(api_key="sk-key")
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "msg_async_001",
            "type": "message",
            "content": [{"type": "text", "text": "Hi"}],
        }
        client._client = AsyncMock()
        client._client.request.return_value = mock_response

        result = await client.request_anthropic("POST", "/anthropic/v1/messages", json={})
        assert result["id"] == "msg_async_001"

    @pytest.mark.asyncio
    async def test_auth_error_raises(self) -> None:
        client = AsyncHttpClient(api_key="sk-key")
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_response.json.return_value = {
            "type": "error",
            "error": {"type": "authentication_error", "message": "Invalid key"},
        }
        client._client = AsyncMock()
        client._client.request.return_value = mock_response

        with pytest.raises(AuthError):
            await client.request_anthropic("POST", "/anthropic/v1/messages", json={})

    @pytest.mark.asyncio
    async def test_rate_limit_retries_then_succeeds(self) -> None:
        client = AsyncHttpClient(api_key="sk-key", max_retries=1)

        rate_resp = MagicMock(spec=httpx.Response)
        rate_resp.status_code = 429
        rate_resp.headers = {}

        ok_resp = MagicMock(spec=httpx.Response)
        ok_resp.status_code = 200
        ok_resp.json.return_value = {"id": "msg_async_002", "type": "message", "content": []}

        client._client = AsyncMock()
        client._client.request.side_effect = [rate_resp, ok_resp]

        result = await client.request_anthropic("POST", "/anthropic/v1/messages", json={})
        assert result["id"] == "msg_async_002"

    @pytest.mark.asyncio
    async def test_transport_error_exhausted(self) -> None:
        client = AsyncHttpClient(api_key="sk-key", max_retries=0)
        client._client = AsyncMock()
        client._client.request.side_effect = httpx.ConnectError("fail")

        with pytest.raises(MiniMaxError, match="HTTP transport error"):
            await client.request_anthropic("POST", "/anthropic/v1/messages", json={})

    @pytest.mark.asyncio
    async def test_non_json_error(self) -> None:
        client = AsyncHttpClient(api_key="sk-key", max_retries=0)

        error_resp = MagicMock(spec=httpx.Response)
        error_resp.status_code = 502
        error_resp.text = "Bad Gateway"
        error_resp.json.side_effect = ValueError("No JSON")

        client._client = AsyncMock()
        client._client.request.return_value = error_resp

        with pytest.raises(MiniMaxError, match="HTTP 502"):
            await client.request_anthropic("POST", "/anthropic/v1/messages", json={})
