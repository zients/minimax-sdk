"""Tests for the Video resource."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from minimax_sdk.resources.video import Video
from minimax_sdk.types.files import FileInfo
from minimax_sdk.types.video import VideoResult


# ── Helpers ──────────────────────────────────────────────────────────────────


def _ok_resp(payload: dict) -> dict:
    """Wrap a payload in a successful API response envelope."""
    return {"base_resp": {"status_code": 0, "status_msg": "success"}, **payload}


def _make_video_resource() -> tuple[Video, MagicMock, MagicMock]:
    """Create a Video resource with a mocked HttpClient and client.

    Returns (video, mock_http, mock_client).
    """
    mock_http = MagicMock()
    mock_client = MagicMock()
    mock_client.poll_interval = 5.0
    mock_client.poll_timeout = 600.0
    video = Video(mock_http, client=mock_client)
    return video, mock_http, mock_client


# ── Tests ────────────────────────────────────────────────────────────────────


class TestVideoCreate:
    """Tests for video.create()."""

    def test_create_returns_dict_with_task_id(self):
        """video.create() returns the raw API response containing task_id."""
        video, mock_http, _ = _make_video_resource()
        mock_http.request.return_value = _ok_resp({"task_id": "task_abc123"})

        result = video.create(model="MiniMax-Hailuo-2.3", prompt="A cat running")

        assert isinstance(result, dict)
        assert result["task_id"] == "task_abc123"
        mock_http.request.assert_called_once_with(
            "POST",
            "/v1/video_generation",
            json={"model": "MiniMax-Hailuo-2.3", "prompt": "A cat running"},
        )


class TestVideoQuery:
    """Tests for video.query()."""

    def test_query_returns_dict_with_status(self):
        """video.query() returns the raw API response containing status."""
        video, mock_http, _ = _make_video_resource()
        mock_http.request.return_value = _ok_resp({
            "task_id": "task_abc123",
            "status": "Processing",
        })

        result = video.query("task_abc123")

        assert isinstance(result, dict)
        assert result["status"] == "Processing"
        mock_http.request.assert_called_once_with(
            "GET",
            "/v1/query/video_generation",
            params={"task_id": "task_abc123"},
        )


class TestVideoTextToVideo:
    """Tests for video.text_to_video() -- the high-level auto-polling method."""

    @patch("minimax_sdk.resources.video.poll_task")
    def test_text_to_video_auto_polls_and_returns_video_result(self, mock_poll_task):
        """text_to_video() creates a task, polls, retrieves file, returns VideoResult."""
        video, mock_http, mock_client = _make_video_resource()

        # Step 1: create() returns task_id
        mock_http.request.return_value = _ok_resp({"task_id": "task_t2v_001"})

        # Step 2: poll_task returns a successful poll response
        mock_poll_task.return_value = {
            "status": "Success",
            "file_id": "file_vid_001",
            "video_width": 1280,
            "video_height": 720,
        }

        # Step 3: files.retrieve returns FileInfo with download_url
        mock_client.files.retrieve.return_value = FileInfo(
            file_id="file_vid_001",
            bytes=5000000,
            created_at=1710000000,
            filename="output.mp4",
            purpose="video_generation",
            download_url="https://cdn.minimax.io/video/file_vid_001.mp4",
        )

        result = video.text_to_video(
            prompt="A cat running in a meadow",
            model="MiniMax-Hailuo-2.3",
            poll_interval=0.1,
            poll_timeout=10.0,
        )

        assert isinstance(result, VideoResult)
        assert result.task_id == "task_t2v_001"
        assert result.status == "Success"
        assert result.file_id == "file_vid_001"
        assert result.download_url == "https://cdn.minimax.io/video/file_vid_001.mp4"
        assert result.video_width == 1280
        assert result.video_height == 720

        # Verify poll_task was called
        mock_poll_task.assert_called_once()

        # Verify files.retrieve was called with the file_id
        mock_client.files.retrieve.assert_called_once_with("file_vid_001")


class TestVideoImageToVideo:
    """Tests for video.image_to_video()."""

    @patch("minimax_sdk.resources.video.poll_task")
    def test_image_to_video_includes_first_frame_image(self, mock_poll_task):
        """image_to_video() includes first_frame_image in the create request body."""
        video, mock_http, mock_client = _make_video_resource()

        # create() returns task_id
        mock_http.request.return_value = _ok_resp({"task_id": "task_i2v_001"})

        # poll_task returns success
        mock_poll_task.return_value = {
            "status": "Success",
            "file_id": "file_vid_002",
            "video_width": 1920,
            "video_height": 1080,
        }

        # files.retrieve returns FileInfo
        mock_client.files.retrieve.return_value = FileInfo(
            file_id="file_vid_002",
            bytes=8000000,
            created_at=1710000000,
            filename="i2v_output.mp4",
            purpose="video_generation",
            download_url="https://cdn.minimax.io/video/file_vid_002.mp4",
        )

        result = video.image_to_video(
            first_frame_image="https://example.com/cat.jpg",
            model="MiniMax-Hailuo-2.3",
            prompt="A cat waking up",
            poll_interval=0.1,
            poll_timeout=10.0,
        )

        assert isinstance(result, VideoResult)
        assert result.task_id == "task_i2v_001"
        assert result.video_width == 1920

        # Verify create was called with first_frame_image in the body
        create_call = mock_http.request.call_args
        body = create_call[1]["json"]
        assert body["first_frame_image"] == "https://example.com/cat.jpg"
        assert body["prompt"] == "A cat waking up"


# ── frames_to_video ─────────────────────────────────────────────────────────


class TestVideoFramesToVideo:
    """Tests for video.frames_to_video() (FL2V)."""

    @patch("minimax_sdk.resources.video.poll_task")
    def test_frames_to_video_with_both_frames(self, mock_poll_task):
        """frames_to_video() includes first_frame_image and last_frame_image."""
        video, mock_http, mock_client = _make_video_resource()

        mock_http.request.return_value = _ok_resp({"task_id": "task_fl2v_001"})

        mock_poll_task.return_value = {
            "status": "Success",
            "file_id": "file_vid_003",
            "video_width": 1280,
            "video_height": 720,
        }

        mock_client.files.retrieve.return_value = FileInfo(
            file_id="file_vid_003",
            bytes=6000000,
            created_at=1710000000,
            filename="fl2v_output.mp4",
            purpose="video_generation",
            download_url="https://cdn.minimax.io/video/file_vid_003.mp4",
        )

        result = video.frames_to_video(
            last_frame_image="https://example.com/last.jpg",
            first_frame_image="https://example.com/first.jpg",
            model="MiniMax-Hailuo-02",
            prompt="A transition between frames",
            poll_interval=0.1,
            poll_timeout=10.0,
        )

        assert isinstance(result, VideoResult)
        assert result.task_id == "task_fl2v_001"
        assert result.file_id == "file_vid_003"
        assert result.download_url == "https://cdn.minimax.io/video/file_vid_003.mp4"

        create_call = mock_http.request.call_args
        body = create_call[1]["json"]
        assert body["last_frame_image"] == "https://example.com/last.jpg"
        assert body["first_frame_image"] == "https://example.com/first.jpg"
        assert body["prompt"] == "A transition between frames"

    @patch("minimax_sdk.resources.video.poll_task")
    def test_frames_to_video_last_frame_only(self, mock_poll_task):
        """frames_to_video() works with only last_frame_image."""
        video, mock_http, mock_client = _make_video_resource()

        mock_http.request.return_value = _ok_resp({"task_id": "task_fl2v_002"})

        mock_poll_task.return_value = {
            "status": "Success",
            "file_id": "file_vid_004",
            "video_width": 1280,
            "video_height": 720,
        }

        mock_client.files.retrieve.return_value = FileInfo(
            file_id="file_vid_004",
            bytes=5000000,
            created_at=1710000000,
            filename="fl2v_output2.mp4",
            purpose="video_generation",
            download_url="https://cdn.minimax.io/video/file_vid_004.mp4",
        )

        result = video.frames_to_video(
            last_frame_image="https://example.com/last.jpg",
            poll_interval=0.1,
            poll_timeout=10.0,
        )

        assert isinstance(result, VideoResult)
        assert result.task_id == "task_fl2v_002"


# ── subject_to_video ────────────────────────────────────────────────────────


class TestVideoSubjectToVideo:
    """Tests for video.subject_to_video() (S2V)."""

    @patch("minimax_sdk.resources.video.poll_task")
    def test_subject_to_video_includes_subject_reference(self, mock_poll_task):
        """subject_to_video() includes subject_reference in the body."""
        video, mock_http, mock_client = _make_video_resource()

        mock_http.request.return_value = _ok_resp({"task_id": "task_s2v_001"})

        mock_poll_task.return_value = {
            "status": "Success",
            "file_id": "file_vid_005",
            "video_width": 1280,
            "video_height": 720,
        }

        mock_client.files.retrieve.return_value = FileInfo(
            file_id="file_vid_005",
            bytes=7000000,
            created_at=1710000000,
            filename="s2v_output.mp4",
            purpose="video_generation",
            download_url="https://cdn.minimax.io/video/file_vid_005.mp4",
        )

        subject_ref = [
            {"type": "character", "image": "https://example.com/person.jpg"},
        ]

        result = video.subject_to_video(
            subject_reference=subject_ref,
            prompt="A person walking",
            model="S2V-01",
            poll_interval=0.1,
            poll_timeout=10.0,
        )

        assert isinstance(result, VideoResult)
        assert result.task_id == "task_s2v_001"

        create_call = mock_http.request.call_args
        body = create_call[1]["json"]
        assert body["subject_reference"] == subject_ref
        assert body["prompt"] == "A person walking"
        assert body["model"] == "S2V-01"


# ── _build_request_body coverage ────────────────────────────────────────────

from minimax_sdk.resources.video import _build_request_body


class TestBuildRequestBody:
    """Cover all branches in _build_request_body."""

    def test_minimal_body(self):
        body = _build_request_body(model="test-model")
        assert body == {"model": "test-model"}

    def test_all_optional_params(self):
        body = _build_request_body(
            model="test-model",
            prompt="hello",
            prompt_optimizer=True,
            fast_pretreatment=False,
            duration=10,
            resolution="1280x720",
            callback_url="https://example.com/cb",
            first_frame_image="https://example.com/first.jpg",
            last_frame_image="https://example.com/last.jpg",
            subject_reference=[{"type": "character", "image": "img.jpg"}],
        )
        assert body["prompt"] == "hello"
        assert body["prompt_optimizer"] is True
        assert body["fast_pretreatment"] is False
        assert body["duration"] == 10
        assert body["resolution"] == "1280x720"
        assert body["callback_url"] == "https://example.com/cb"
        assert body["first_frame_image"] == "https://example.com/first.jpg"
        assert body["last_frame_image"] == "https://example.com/last.jpg"
        assert body["subject_reference"] == [{"type": "character", "image": "img.jpg"}]


# ── Async Tests ─────────────────────────────────────────────────────────────

from unittest.mock import AsyncMock

import pytest

from minimax_sdk.resources.video import AsyncVideo


def _make_async_video_resource() -> tuple[AsyncVideo, AsyncMock, MagicMock]:
    """Create an AsyncVideo resource with mocked AsyncHttpClient and client."""
    mock_http = AsyncMock()
    mock_client = MagicMock()
    mock_client.poll_interval = 5.0
    mock_client.poll_timeout = 600.0
    mock_client.files = MagicMock()
    mock_client.files.retrieve = AsyncMock()
    video = AsyncVideo(mock_http, client=mock_client)
    return video, mock_http, mock_client


class TestAsyncVideoCreate:
    """Tests for async video.create()."""

    @pytest.mark.asyncio
    async def test_create_returns_dict_with_task_id(self):
        """Async video.create() returns raw API response."""
        video, mock_http, _ = _make_async_video_resource()
        mock_http.request.return_value = _ok_resp({"task_id": "task_abc123"})

        result = await video.create(model="MiniMax-Hailuo-2.3", prompt="A cat")

        assert result["task_id"] == "task_abc123"
        mock_http.request.assert_awaited_once_with(
            "POST",
            "/v1/video_generation",
            json={"model": "MiniMax-Hailuo-2.3", "prompt": "A cat"},
        )


class TestAsyncVideoQuery:
    """Tests for async video.query()."""

    @pytest.mark.asyncio
    async def test_query_returns_dict_with_status(self):
        """Async video.query() returns raw API response."""
        video, mock_http, _ = _make_async_video_resource()
        mock_http.request.return_value = _ok_resp({
            "task_id": "task_abc123",
            "status": "Processing",
        })

        result = await video.query("task_abc123")

        assert result["status"] == "Processing"
        mock_http.request.assert_awaited_once_with(
            "GET",
            "/v1/query/video_generation",
            params={"task_id": "task_abc123"},
        )


class TestAsyncVideoTextToVideo:
    """Tests for async video.text_to_video()."""

    @patch("minimax_sdk.resources.video.async_poll_task")
    @pytest.mark.asyncio
    async def test_text_to_video_auto_polls(self, mock_async_poll_task):
        """Async text_to_video() creates, polls, retrieves, returns VideoResult."""
        video, mock_http, mock_client = _make_async_video_resource()

        mock_http.request.return_value = _ok_resp({"task_id": "task_t2v_async"})

        mock_async_poll_task.return_value = {
            "status": "Success",
            "file_id": "file_vid_async",
            "video_width": 1280,
            "video_height": 720,
        }

        mock_client.files.retrieve.return_value = FileInfo(
            file_id="file_vid_async",
            bytes=5000000,
            created_at=1710000000,
            filename="output.mp4",
            purpose="video_generation",
            download_url="https://cdn.minimax.io/video/async.mp4",
        )

        result = await video.text_to_video(
            prompt="A cat running",
            poll_interval=0.1,
            poll_timeout=10.0,
        )

        assert isinstance(result, VideoResult)
        assert result.task_id == "task_t2v_async"
        assert result.download_url == "https://cdn.minimax.io/video/async.mp4"


class TestAsyncVideoImageToVideo:
    """Tests for async video.image_to_video()."""

    @patch("minimax_sdk.resources.video.async_poll_task")
    @pytest.mark.asyncio
    async def test_image_to_video(self, mock_async_poll_task):
        """Async image_to_video() includes first_frame_image."""
        video, mock_http, mock_client = _make_async_video_resource()

        mock_http.request.return_value = _ok_resp({"task_id": "task_i2v_async"})

        mock_async_poll_task.return_value = {
            "status": "Success",
            "file_id": "file_vid_i2v_async",
            "video_width": 1920,
            "video_height": 1080,
        }

        mock_client.files.retrieve.return_value = FileInfo(
            file_id="file_vid_i2v_async",
            bytes=8000000,
            created_at=1710000000,
            filename="i2v_output.mp4",
            purpose="video_generation",
            download_url="https://cdn.minimax.io/video/i2v_async.mp4",
        )

        result = await video.image_to_video(
            first_frame_image="https://example.com/frame.jpg",
            prompt="Moving frame",
            poll_interval=0.1,
            poll_timeout=10.0,
        )

        assert isinstance(result, VideoResult)
        assert result.task_id == "task_i2v_async"


class TestAsyncVideoFramesToVideo:
    """Tests for async video.frames_to_video()."""

    @patch("minimax_sdk.resources.video.async_poll_task")
    @pytest.mark.asyncio
    async def test_frames_to_video(self, mock_async_poll_task):
        """Async frames_to_video() includes both frames."""
        video, mock_http, mock_client = _make_async_video_resource()

        mock_http.request.return_value = _ok_resp({"task_id": "task_fl2v_async"})

        mock_async_poll_task.return_value = {
            "status": "Success",
            "file_id": "file_vid_fl2v_async",
            "video_width": 1280,
            "video_height": 720,
        }

        mock_client.files.retrieve.return_value = FileInfo(
            file_id="file_vid_fl2v_async",
            bytes=6000000,
            created_at=1710000000,
            filename="fl2v_output.mp4",
            purpose="video_generation",
            download_url="https://cdn.minimax.io/video/fl2v_async.mp4",
        )

        result = await video.frames_to_video(
            last_frame_image="https://example.com/last.jpg",
            first_frame_image="https://example.com/first.jpg",
            poll_interval=0.1,
            poll_timeout=10.0,
        )

        assert isinstance(result, VideoResult)
        assert result.task_id == "task_fl2v_async"


class TestAsyncVideoSubjectToVideo:
    """Tests for async video.subject_to_video()."""

    @patch("minimax_sdk.resources.video.async_poll_task")
    @pytest.mark.asyncio
    async def test_subject_to_video(self, mock_async_poll_task):
        """Async subject_to_video() includes subject_reference."""
        video, mock_http, mock_client = _make_async_video_resource()

        mock_http.request.return_value = _ok_resp({"task_id": "task_s2v_async"})

        mock_async_poll_task.return_value = {
            "status": "Success",
            "file_id": "file_vid_s2v_async",
            "video_width": 1280,
            "video_height": 720,
        }

        mock_client.files.retrieve.return_value = FileInfo(
            file_id="file_vid_s2v_async",
            bytes=7000000,
            created_at=1710000000,
            filename="s2v_output.mp4",
            purpose="video_generation",
            download_url="https://cdn.minimax.io/video/s2v_async.mp4",
        )

        subject_ref = [{"type": "character", "image": "https://example.com/p.jpg"}]

        result = await video.subject_to_video(
            subject_reference=subject_ref,
            prompt="A person walking",
            poll_interval=0.1,
            poll_timeout=10.0,
        )

        assert isinstance(result, VideoResult)
        assert result.task_id == "task_s2v_async"
