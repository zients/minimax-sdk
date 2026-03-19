"""Integration tests for MiniMax SDK -- Video module.

These tests hit the real MiniMax API and require MINIMAX_API_KEY in .env.
Run with: cd python && uv run pytest tests/integration/test_video.py -v

Uses MiniMax-Hailuo-02 with resolution="768P" and duration=6
(4500 requests per video).
"""

import pytest

from minimax_sdk import MiniMax
from minimax_sdk.exceptions import InsufficientBalanceError
from minimax_sdk.types.video import VideoResult

MODEL = "MiniMax-Hailuo-02"
PROMPT = "A simple red ball bouncing on a white background"


@pytest.fixture(scope="module")
def client():
    """Create a real MiniMax client from .env."""
    return MiniMax()


class TestVideoCreateAndQuery:
    """Test low-level create + query (shares one task to save cost)."""

    def test_create_and_query(self, client):
        """Create a video task, then query its status."""
        try:
            create_resp = client.video.create(
                model=MODEL,
                prompt=PROMPT,
                resolution="768P",
                duration=6,
            )
        except InsufficientBalanceError as exc:
            pytest.skip(f"API balance/limit issue: {exc}")

        assert "task_id" in create_resp, f"expected 'task_id', got keys: {list(create_resp.keys())}"
        task_id = create_resp["task_id"]
        assert task_id, "task_id should be non-empty"

        # Query the same task
        query_resp = client.video.query(task_id)

        assert "task_id" in query_resp
        assert "status" in query_resp
        assert query_resp["status"] in (
            "Preparing", "Queueing", "Processing", "Success", "Fail",
        ), f"unexpected status: {query_resp['status']!r}"


class TestVideoTextToVideo:
    """Test high-level text-to-video pipeline (create + auto-poll + retrieve)."""

    def test_text_to_video(self, client):
        """Full text-to-video pipeline, verify VideoResult fields."""
        try:
            result = client.video.text_to_video(
                prompt=PROMPT,
                model=MODEL,
                resolution="768P",
                duration=6,
                poll_interval=5.0,
                poll_timeout=300.0,
            )
        except InsufficientBalanceError as exc:
            pytest.skip(f"API balance/limit issue: {exc}")

        assert isinstance(result, VideoResult), f"expected VideoResult, got {type(result)}"
        assert result.task_id, f"task_id should be non-empty, got: {result.task_id!r}"
        assert result.status, f"status should be non-empty, got: {result.status!r}"
        assert result.file_id, f"file_id should be non-empty, got: {result.file_id!r}"
        assert result.download_url, f"download_url should be non-empty, got: {result.download_url!r}"
        assert result.download_url.startswith("http"), (
            f"download_url should start with 'http', got: {result.download_url[:80]!r}"
        )
