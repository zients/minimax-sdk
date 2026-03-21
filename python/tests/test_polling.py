"""Tests for minimax_sdk._polling."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from minimax_sdk._polling import async_poll_task, poll_task
from minimax_sdk.exceptions import MiniMaxError, PollTimeoutError


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_http_client_with_responses(responses: list[dict]) -> MagicMock:
    """Create a mock HttpClient whose ``.request()`` returns *responses* in order."""
    client = MagicMock()
    client.request = MagicMock(side_effect=responses)
    return client


def _make_async_http_client_with_responses(responses: list[dict]) -> AsyncMock:
    """Create a mock AsyncHttpClient whose ``.request()`` returns *responses* in order."""
    client = AsyncMock()
    client.request = AsyncMock(side_effect=responses)
    return client


# ── Tests ────────────────────────────────────────────────────────────────────


class TestPollTaskSuccess:
    def test_returns_immediately_on_success(self) -> None:
        success_body = {
            "status": "Success",
            "file_id": "file-123",
            "base_resp": {"status_code": 0, "status_msg": ""},
        }
        client = _make_http_client_with_responses([success_body])

        result = poll_task(
            client,
            "/v1/query/video_generation",
            "task-abc",
            poll_interval=0.01,
            poll_timeout=5.0,
        )

        assert result["status"] == "Success"
        assert result["file_id"] == "file-123"
        client.request.assert_called_once()

    @patch("minimax_sdk._polling.time.sleep", return_value=None)
    def test_returns_after_processing_then_success(
        self, mock_sleep: MagicMock
    ) -> None:
        responses = [
            {
                "status": "Processing",
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
            {
                "status": "Processing",
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
            {
                "status": "Success",
                "file_id": "file-456",
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
        ]
        client = _make_http_client_with_responses(responses)

        result = poll_task(
            client,
            "/v1/query/video_generation",
            "task-def",
            poll_interval=0.01,
            poll_timeout=600.0,
        )

        assert result["status"] == "Success"
        assert result["file_id"] == "file-456"
        assert client.request.call_count == 3
        # Sleep should have been called between polls
        assert mock_sleep.call_count == 2


class TestPollTaskFailure:
    def test_raises_minimax_error_on_fail_status(self) -> None:
        fail_body = {
            "status": "Fail",
            "base_resp": {"status_code": 1026, "status_msg": "Content unsafe"},
            "trace_id": "tr-fail",
        }
        client = _make_http_client_with_responses([fail_body])

        with pytest.raises(MiniMaxError) as exc_info:
            poll_task(
                client,
                "/v1/query/video_generation",
                "task-fail",
                poll_interval=0.01,
                poll_timeout=5.0,
            )

        assert exc_info.value.code == 1026
        assert exc_info.value.message == "Content unsafe"
        assert exc_info.value.trace_id == "tr-fail"


class TestPollTaskTimeout:
    @patch("minimax_sdk._polling.time.sleep", return_value=None)
    @patch("minimax_sdk._polling.time.monotonic")
    def test_raises_poll_timeout_when_exceeded(
        self, mock_monotonic: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """Simulate time passing so poll_timeout is exceeded."""
        # monotonic() is called:
        #   1) once at the start to compute deadline = start + poll_timeout
        #   2) after sleep to check if monotonic() > deadline
        #
        # With poll_timeout=10 and poll_interval=5:
        #   deadline = 0 + 10 = 10
        #   After 1st query + sleep: monotonic() returns 11 > 10 => timeout
        mock_monotonic.side_effect = [0.0, 11.0]

        processing_body = {
            "status": "Processing",
            "base_resp": {"status_code": 0, "status_msg": ""},
        }
        # Provide enough responses; only one will be consumed before timeout.
        client = _make_http_client_with_responses(
            [processing_body, processing_body, processing_body]
        )

        with pytest.raises(PollTimeoutError) as exc_info:
            poll_task(
                client,
                "/v1/query/video_generation",
                "task-timeout",
                poll_interval=5.0,
                poll_timeout=10.0,
            )

        assert "task-timeout" in str(exc_info.value)
        assert "10.0" in str(exc_info.value)


class TestPollTaskUnknownStatus:
    @patch("minimax_sdk._polling.time.sleep", return_value=None)
    def test_unknown_status_treated_as_pending(self, mock_sleep: MagicMock) -> None:
        """An unknown status should be treated as still pending and continue polling."""
        responses = [
            {
                "status": "WeirdStatus",
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
            {
                "status": "Success",
                "file_id": "file-unknown",
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
        ]
        client = _make_http_client_with_responses(responses)

        result = poll_task(
            client,
            "/v1/query/video_generation",
            "task-unknown",
            poll_interval=0.01,
            poll_timeout=600.0,
        )

        assert result["status"] == "Success"
        assert result["file_id"] == "file-unknown"
        assert client.request.call_count == 2


class TestPollTaskStatusProgression:
    @patch("minimax_sdk._polling.time.sleep", return_value=None)
    def test_preparing_to_queueing_to_processing_to_success(
        self, mock_sleep: MagicMock
    ) -> None:
        """Test the full lifecycle: Preparing -> Queueing -> Processing -> Success."""
        responses = [
            {
                "status": "Preparing",
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
            {
                "status": "Queueing",
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
            {
                "status": "Processing",
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
            {
                "status": "Success",
                "file_id": "file-789",
                "video_width": 1280,
                "video_height": 720,
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
        ]
        client = _make_http_client_with_responses(responses)

        result = poll_task(
            client,
            "/v1/query/video_generation",
            "task-lifecycle",
            poll_interval=0.01,
            poll_timeout=600.0,
        )

        assert result["status"] == "Success"
        assert result["file_id"] == "file-789"
        assert client.request.call_count == 4
        assert mock_sleep.call_count == 3


# ── Async Poll Tests ─────────────────────────────────────────────────────────


class TestAsyncPollTaskSuccess:
    @pytest.mark.asyncio
    async def test_returns_immediately_on_success(self) -> None:
        success_body = {
            "status": "Success",
            "file_id": "file-async-123",
            "base_resp": {"status_code": 0, "status_msg": ""},
        }
        client = _make_async_http_client_with_responses([success_body])

        result = await async_poll_task(
            client,
            "/v1/query/video_generation",
            "task-async-abc",
            poll_interval=0.01,
            poll_timeout=5.0,
        )

        assert result["status"] == "Success"
        assert result["file_id"] == "file-async-123"
        client.request.assert_called_once()

    @pytest.mark.asyncio
    @patch("minimax_sdk._polling.asyncio.sleep", new_callable=AsyncMock)
    async def test_returns_after_processing_then_success(
        self, mock_sleep: AsyncMock
    ) -> None:
        responses = [
            {
                "status": "Processing",
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
            {
                "status": "Success",
                "file_id": "file-async-456",
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
        ]
        client = _make_async_http_client_with_responses(responses)

        # We need to mock the event loop time so the deadline check doesn't timeout
        mock_loop = MagicMock()
        mock_loop.time.side_effect = [1000000.0, 1000000.0]  # large values

        with patch("minimax_sdk._polling.asyncio.get_running_loop", return_value=mock_loop):
            result = await async_poll_task(
                client,
                "/v1/query/video_generation",
                "task-async-def",
                poll_interval=0.01,
                poll_timeout=600.0,
            )

        assert result["status"] == "Success"
        assert result["file_id"] == "file-async-456"
        assert client.request.call_count == 2


class TestAsyncPollTaskFailure:
    @pytest.mark.asyncio
    async def test_raises_minimax_error_on_fail_status(self) -> None:
        fail_body = {
            "status": "Fail",
            "base_resp": {"status_code": 1026, "status_msg": "Content unsafe"},
            "trace_id": "tr-async-fail",
        }
        client = _make_async_http_client_with_responses([fail_body])

        # Mock event loop time for deadline calculation
        mock_loop = MagicMock()
        mock_loop.time.return_value = 0.0

        with patch("minimax_sdk._polling.asyncio.get_running_loop", return_value=mock_loop):
            with pytest.raises(MiniMaxError) as exc_info:
                await async_poll_task(
                    client,
                    "/v1/query/video_generation",
                    "task-async-fail",
                    poll_interval=0.01,
                    poll_timeout=5.0,
                )

        assert exc_info.value.code == 1026
        assert exc_info.value.message == "Content unsafe"
        assert exc_info.value.trace_id == "tr-async-fail"


class TestAsyncPollTaskTimeout:
    @pytest.mark.asyncio
    @patch("minimax_sdk._polling.asyncio.sleep", new_callable=AsyncMock)
    async def test_raises_poll_timeout_when_exceeded(self, mock_sleep: AsyncMock) -> None:
        """Simulate time passing so poll_timeout is exceeded in async context."""
        processing_body = {
            "status": "Processing",
            "base_resp": {"status_code": 0, "status_msg": ""},
        }
        client = _make_async_http_client_with_responses(
            [processing_body, processing_body, processing_body]
        )

        # Mock get_running_loop().time():
        #   1) deadline = 0 + 10 = 10
        #   2) after sleep: 11 > 10 => timeout
        mock_loop = MagicMock()
        mock_loop.time.side_effect = [0.0, 11.0]

        with patch("minimax_sdk._polling.asyncio.get_running_loop", return_value=mock_loop):
            with pytest.raises(PollTimeoutError) as exc_info:
                await async_poll_task(
                    client,
                    "/v1/query/video_generation",
                    "task-async-timeout",
                    poll_interval=5.0,
                    poll_timeout=10.0,
                )

        assert "task-async-timeout" in str(exc_info.value)
        assert "10.0" in str(exc_info.value)


class TestAsyncPollTaskStatusProgression:
    @pytest.mark.asyncio
    @patch("minimax_sdk._polling.asyncio.sleep", new_callable=AsyncMock)
    async def test_preparing_to_queueing_to_processing_to_success(
        self, mock_sleep: AsyncMock
    ) -> None:
        """Test the full async lifecycle: Preparing -> Queueing -> Processing -> Success."""
        responses = [
            {
                "status": "Preparing",
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
            {
                "status": "Queueing",
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
            {
                "status": "Processing",
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
            {
                "status": "Success",
                "file_id": "file-async-789",
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
        ]
        client = _make_async_http_client_with_responses(responses)

        # Mock event loop time — returns large deadline so it never times out
        mock_loop = MagicMock()
        mock_loop.time.side_effect = [0.0, 0.0, 0.0, 0.0]  # never exceeds deadline

        with patch("minimax_sdk._polling.asyncio.get_running_loop", return_value=mock_loop):
            result = await async_poll_task(
                client,
                "/v1/query/video_generation",
                "task-async-lifecycle",
                poll_interval=0.01,
                poll_timeout=600.0,
            )

        assert result["status"] == "Success"
        assert result["file_id"] == "file-async-789"
        assert client.request.call_count == 4


class TestAsyncPollTaskUnknownStatus:
    @pytest.mark.asyncio
    @patch("minimax_sdk._polling.asyncio.sleep", new_callable=AsyncMock)
    async def test_unknown_status_treated_as_pending(self, mock_sleep: AsyncMock) -> None:
        """An unknown status should be treated as still pending and continue polling."""
        responses = [
            {
                "status": "WeirdStatus",
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
            {
                "status": "Success",
                "file_id": "file-unknown",
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
        ]
        client = _make_async_http_client_with_responses(responses)

        mock_loop = MagicMock()
        mock_loop.time.side_effect = [0.0, 0.0]

        with patch("minimax_sdk._polling.asyncio.get_running_loop", return_value=mock_loop):
            result = await async_poll_task(
                client,
                "/v1/query/video_generation",
                "task-unknown",
                poll_interval=0.01,
                poll_timeout=600.0,
            )

        assert result["status"] == "Success"
