"""Integration tests for MiniMax SDK.

These tests hit the real MiniMax API and require MINIMAX_API_KEY in .env.
Run with: cd python && uv run pytest tests/integration/ -v
"""

import os
import tempfile

import pytest

from minimax_sdk import MiniMax


@pytest.fixture(scope="module")
def client():
    """Create a real MiniMax client from .env."""
    c = MiniMax()
    yield c


class TestSpeechIntegration:
    """Test Speech TTS with real API."""

    def test_tts_basic(self, client, tmp_path):
        audio = client.speech.tts(
            text="Hello, this is a test.",
            model="speech-2.8-hd",
            voice_setting={"voice_id": "English_expressive_narrator"},
        )
        assert audio.data is not None
        assert len(audio.data) > 0
        assert audio.duration > 0
        assert audio.format == "mp3"

        # Test save
        out = tmp_path / "test_tts.mp3"
        audio.save(str(out))
        assert out.exists()
        assert out.stat().st_size > 0


class TestVoiceIntegration:
    """Test Voice list with real API."""

    def test_list_system_voices(self, client):
        result = client.voice.list(voice_type="system")
        assert result.system_voice is not None
        assert len(result.system_voice) > 0
        assert result.system_voice[0].voice_id is not None


class TestImageIntegration:
    """Test Image generation with real API."""

    def test_generate_image(self, client):
        result = client.image.generate(
            prompt="A simple red circle on white background",
            model="image-01",
            n=1,
            response_format="url",
        )
        assert result.image_urls is not None
        assert len(result.image_urls) == 1
        assert result.image_urls[0].startswith("http")
        assert result.success_count == 1


class TestMusicIntegration:
    """Test Music lyrics generation with real API (cheapest operation)."""

    def test_generate_lyrics(self, client):
        result = client.music.generate_lyrics(
            mode="write_full_song",
            prompt="A short happy song about sunshine",
        )
        assert result.song_title is not None
        assert result.lyrics is not None
        assert len(result.lyrics) > 0


class TestFilesIntegration:
    """Test Files list with real API."""

    def test_list_files(self, client):
        files = client.files.list(purpose="voice_clone")
        assert isinstance(files, list)
