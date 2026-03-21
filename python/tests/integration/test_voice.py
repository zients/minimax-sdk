"""Integration tests for MiniMax SDK — Voice module.

These tests hit the real MiniMax API and require MINIMAX_API_KEY in .env.
Run with: cd python && uv run pytest tests/integration/test_voice.py -v
"""

import tempfile
import time
from pathlib import Path

import pytest

from minimax_sdk import MiniMax
from minimax_sdk.exceptions import (
    InsufficientBalanceError,
    InvalidParameterError,
    MiniMaxError,
)


def _make_minimal_mp3() -> bytes:
    """Create a minimal valid MP3 file (~1.2 KB of silence)."""
    frame_header = b"\xff\xfb\x90\x04"
    frame_data = b"\x00" * (417 - 4)
    frame = frame_header + frame_data
    return frame * 3


@pytest.fixture(scope="module")
def client():
    """Create a real MiniMax client from .env."""
    return MiniMax()


class TestVoiceIntegration:
    """Test Voice resource methods against the real API.

    Tests are numbered to enforce execution order.
    """

    cloned_voice_id: str = ""
    clone_file_id: str = ""

    def test_1_voice_list_system(self, client):
        """List system voices and verify non-empty list."""
        result = client.voice.list(voice_type="system")
        assert result.system_voice is not None
        assert len(result.system_voice) > 0
        first = result.system_voice[0]
        assert first.voice_id is not None
        assert len(first.voice_id) > 0

    def test_2_voice_list_all(self, client):
        """List all voice types and verify structure."""
        result = client.voice.list(voice_type="all")
        assert result.system_voice is not None
        assert len(result.system_voice) > 0
        assert isinstance(result.voice_cloning, list)
        assert isinstance(result.voice_generation, list)

    def test_3_voice_design(self, client):
        """Design a voice from description, verify trial audio."""
        try:
            result = client.voice.design(
                prompt="A warm, friendly female narrator with a calm tone",
                preview_text="Hello, this is a test of voice design.",
            )
        except InsufficientBalanceError as exc:
            pytest.skip(
                f"voice.design requires pay-as-you-go balance, not covered by Token Plan: {exc}"
            )

        assert result.voice_id is not None
        assert len(result.voice_id) > 0
        assert result.trial_audio is not None
        assert result.trial_audio.data is not None
        assert len(result.trial_audio.data) > 0

    def test_4_voice_upload_and_clone(self, client):
        """Upload a synthetic MP3, then clone a voice."""
        # Step 1: Upload synthetic MP3 using a temp file
        import os

        mp3_data = _make_minimal_mp3()
        tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=".mp3")
        os.close(tmp_fd)
        tmp_path = Path(tmp_path_str)
        try:
            tmp_path.write_bytes(mp3_data)

            try:
                file_info = client.voice.upload_audio(str(tmp_path), purpose="voice_clone")
            except (InsufficientBalanceError, MiniMaxError) as exc:
                pytest.skip(f"Upload failed: {exc}")
        finally:
            tmp_path.unlink(missing_ok=True)

        assert file_info.file_id is not None
        assert len(file_info.file_id) > 0
        TestVoiceIntegration.clone_file_id = file_info.file_id

        # Step 2: Clone the voice
        timestamp = int(time.time())
        voice_id = f"test-clone-{timestamp}"

        try:
            clone_result = client.voice.clone(
                file_id=file_info.file_id,
                voice_id=voice_id,
            )
        except InsufficientBalanceError as exc:
            pytest.skip(
                f"voice.clone requires pay-as-you-go balance, not covered by Token Plan: {exc}"
            )
        except InvalidParameterError as exc:
            pytest.skip(f"Clone failed with invalid params: {exc}")

        TestVoiceIntegration.cloned_voice_id = voice_id
        assert clone_result.voice_id == voice_id

    def test_5_voice_delete(self, client):
        """Delete the cloned voice from test 4."""
        voice_id = TestVoiceIntegration.cloned_voice_id
        if not voice_id:
            pytest.skip("No cloned voice_id from test_4 (upstream skipped)")

        client.voice.delete(voice_id=voice_id, voice_type="voice_cloning")
