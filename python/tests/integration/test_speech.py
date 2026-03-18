"""Integration tests for MiniMax SDK -- Speech module.

These tests hit the real MiniMax API and require MINIMAX_API_KEY in .env.
Run with: cd python && uv run pytest tests/integration/test_speech.py -v --timeout=120
"""

import pytest

from minimax_sdk import MiniMax
from minimax_sdk._audio import AudioResponse
from minimax_sdk.types.speech import TaskResult

MODEL = "speech-2.8-hd"
VOICE_SETTING = {"voice_id": "English_expressive_narrator"}
SHORT_TEXT = "Hello, this is a quick test."


@pytest.fixture(scope="module")
def client():
    """Create a real MiniMax client from .env."""
    return MiniMax()


class TestTTSBasic:
    """Test basic synchronous TTS."""

    def test_tts_basic(self, client):
        """Generate short TTS, verify AudioResponse fields."""
        audio = client.speech.tts(
            text=SHORT_TEXT,
            model=MODEL,
            voice_setting=VOICE_SETTING,
        )

        # Verify it returns an AudioResponse with expected fields
        assert isinstance(audio, AudioResponse), f"expected AudioResponse, got {type(audio)}"
        assert audio.data is not None, "audio.data should not be None"
        assert len(audio.data) > 0, "audio.data should contain bytes"
        assert audio.duration > 0, f"duration should be > 0, got: {audio.duration}"
        assert audio.sample_rate > 0, f"sample_rate should be > 0, got: {audio.sample_rate}"
        assert audio.size > 0, f"size should be > 0, got: {audio.size}"
        assert audio.format == "mp3", f"expected format 'mp3', got: {audio.format!r}"


class TestTTSWithOptions:
    """Test TTS with voice_setting and audio_setting options."""

    def test_tts_with_options(self, client):
        """TTS with voice_setting (speed, pitch) and audio_setting (format, sample_rate)."""
        audio = client.speech.tts(
            text=SHORT_TEXT,
            model=MODEL,
            voice_setting={
                "voice_id": "English_expressive_narrator",
                "speed": 1.2,
                "pitch": 0,
            },
            audio_setting={
                "format": "mp3",
                "sample_rate": 24000,
            },
        )

        assert isinstance(audio, AudioResponse), f"expected AudioResponse, got {type(audio)}"
        assert len(audio.data) > 0, "audio.data should contain bytes"
        assert audio.duration > 0, f"duration should be > 0, got: {audio.duration}"
        assert audio.sample_rate > 0, f"sample_rate should be > 0, got: {audio.sample_rate}"
        assert audio.format == "mp3", f"expected format 'mp3', got: {audio.format!r}"


class TestTTSStream:
    """Test streaming TTS."""

    def test_tts_stream(self, client):
        """Stream TTS, collect all chunks, verify total bytes > 0."""
        chunks = []
        for chunk in client.speech.tts_stream(
            text=SHORT_TEXT,
            model=MODEL,
            voice_setting=VOICE_SETTING,
        ):
            assert isinstance(chunk, bytes), f"expected bytes chunk, got {type(chunk)}"
            chunks.append(chunk)

        assert len(chunks) > 0, "should have received at least one chunk"

        all_bytes = b"".join(chunks)
        assert len(all_bytes) > 0, "total streamed bytes should be > 0"


class TestWebSocket:
    """Test WebSocket TTS."""

    def test_websocket_connect_send(self, client):
        """Connect via WebSocket, send text, verify AudioResponse."""
        try:
            with client.speech.connect(
                model=MODEL,
                voice_setting=VOICE_SETTING,
            ) as conn:
                audio = conn.send(SHORT_TEXT)

                assert isinstance(audio, AudioResponse), f"expected AudioResponse, got {type(audio)}"
                assert audio.data is not None, "audio.data should not be None"
                assert len(audio.data) > 0, "audio.data should contain bytes"
                assert audio.duration > 0, f"duration should be > 0, got: {audio.duration}"

        except (ConnectionError, OSError) as exc:
            pytest.skip(f"WebSocket not available: {exc}")


class TestAsyncCreateAndQuery:
    """Test async task creation and query."""

    def test_async_create_and_query(self, client):
        """Create async task, query status, verify task_id and status fields exist."""
        # Step 1: Create the async task
        create_resp = client.speech.async_create(
            text=SHORT_TEXT,
            model=MODEL,
            voice_setting=VOICE_SETTING,
        )

        assert "task_id" in create_resp, f"response should contain 'task_id', got keys: {list(create_resp.keys())}"
        task_id = create_resp["task_id"]
        assert task_id, "task_id should be non-empty"

        # Step 2: Query the task status
        query_resp = client.speech.async_query(task_id)

        assert "task_id" in query_resp, f"query response should contain 'task_id', got keys: {list(query_resp.keys())}"
        assert "status" in query_resp, f"query response should contain 'status', got keys: {list(query_resp.keys())}"
        assert query_resp["task_id"] == task_id, (
            f"task_id mismatch: expected {task_id!r}, got {query_resp['task_id']!r}"
        )


class TestAsyncGenerate:
    """Test full async pipeline (create + auto-poll)."""

    def test_async_generate(self, client):
        """Full async pipeline (create + auto-poll), verify TaskResult fields."""
        try:
            result = client.speech.async_generate(
                text=SHORT_TEXT,
                model=MODEL,
                voice_setting=VOICE_SETTING,
                poll_interval=2.0,
                poll_timeout=120.0,
            )

            assert isinstance(result, TaskResult), f"expected TaskResult, got {type(result)}"
            assert result.task_id, f"task_id should be non-empty, got: {result.task_id!r}"
            assert result.status, f"status should be non-empty, got: {result.status!r}"
            assert result.file_id, f"file_id should be non-empty, got: {result.file_id!r}"
            assert result.download_url, f"download_url should be non-empty, got: {result.download_url!r}"
            assert result.download_url.startswith("http"), (
                f"download_url should start with 'http', got: {result.download_url[:80]!r}"
            )

        except AttributeError as exc:
            pytest.fail(f"async_generate raised AttributeError (likely missing resource attributes): {exc}")
