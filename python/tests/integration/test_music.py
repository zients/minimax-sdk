"""Integration tests for MiniMax SDK -- Music module.

These tests hit the real MiniMax API and require MINIMAX_API_KEY in .env.
Run with: cd python && uv run pytest tests/integration/test_music.py -v --timeout=180
"""

from pathlib import Path

import httpx
import pytest

from minimax_sdk import MiniMax

OUTPUTS_DIR = Path(__file__).parent / "outputs"

SHORT_LYRICS = """\
[Verse]
Hello sunshine
[Chorus]
La la la"""


@pytest.fixture(scope="module")
def client():
    """Create a real MiniMax client from .env."""
    return MiniMax()


class TestMusicLyrics:
    """Test lyrics generation endpoints."""

    def test_generate_lyrics_full_song(self, client):
        """Generate lyrics with mode='write_full_song' and verify fields."""
        result = client.music.generate_lyrics(
            mode="write_full_song",
            prompt="A short happy pop song about sunshine and summer",
        )

        assert result.song_title, f"song_title should be non-empty, got: {result.song_title!r}"
        assert result.style_tags, f"style_tags should be non-empty, got: {result.style_tags!r}"
        assert result.lyrics, f"lyrics should be non-empty, got: {result.lyrics!r}"
        assert len(result.lyrics) > 10, "lyrics should contain meaningful content"

    def test_generate_lyrics_edit(self, client):
        """Generate lyrics, then edit them, verify modified lyrics returned."""
        # Step 1: generate original lyrics
        original = client.music.generate_lyrics(
            mode="write_full_song",
            prompt="A short happy song about sunshine",
        )
        assert original.lyrics, "original lyrics should be non-empty"

        # Step 2: edit the lyrics
        edited = client.music.generate_lyrics(
            mode="edit",
            prompt="Make it more energetic and add a bridge section",
            lyrics=original.lyrics,
        )

        assert edited.lyrics, f"edited lyrics should be non-empty, got: {edited.lyrics!r}"
        assert len(edited.lyrics) > 10, "edited lyrics should contain meaningful content"


class TestMusicGeneration:
    """Test music generation endpoints (these take 30-60+ seconds)."""

    def test_generate_music(self, client):
        """Generate music with output_format='url', download and save to mp3."""
        audio = client.music.generate(
            model="music-2.5+",
            lyrics=SHORT_LYRICS,
            prompt="happy pop",
            output_format="url",
        )

        assert audio.duration > 0, f"duration should be > 0, got: {audio.duration}"

        # For URL output format, audio.data contains the URL encoded as bytes
        url = audio.data.decode("utf-8")
        assert url.startswith("http"), f"expected a URL, got: {url[:100]}"

        # Download the audio from the URL and save it
        out_path = OUTPUTS_DIR / "music_generated.mp3"
        response = httpx.get(url, follow_redirects=True, timeout=60.0)
        response.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(response.content)

        assert out_path.exists(), "output file should exist"
        assert out_path.stat().st_size > 0, "output file should not be empty"
        print(f"Saved music to {out_path} ({out_path.stat().st_size} bytes)")

    def test_generate_music_instrumental(self, client):
        """Generate instrumental music with is_instrumental=True."""
        audio = client.music.generate(
            model="music-2.5+",
            prompt="calm ambient instrumental",
            is_instrumental=True,
            output_format="url",
        )

        assert audio.duration > 0, f"duration should be > 0, got: {audio.duration}"

        # For URL output format, audio.data contains the URL encoded as bytes
        url = audio.data.decode("utf-8")
        assert url.startswith("http"), f"expected a URL, got: {url[:100]}"

        # Download the audio from the URL and save it
        out_path = OUTPUTS_DIR / "music_instrumental.mp3"
        response = httpx.get(url, follow_redirects=True, timeout=60.0)
        response.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(response.content)

        assert out_path.exists(), "output file should exist"
        assert out_path.stat().st_size > 0, "output file should not be empty"
        print(f"Saved instrumental to {out_path} ({out_path.stat().st_size} bytes)")
