"""Tests for minimax_sdk._audio."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from minimax_sdk._audio import AudioResponse, build_audio_response, decode_hex_audio


# ── decode_hex_audio ─────────────────────────────────────────────────────────


class TestDecodeHexAudio:
    def test_valid_hex_string(self) -> None:
        hex_str = "48656c6c6f"  # "Hello"
        assert decode_hex_audio(hex_str) == b"Hello"

    def test_empty_hex_string(self) -> None:
        assert decode_hex_audio("") == b""

    def test_invalid_hex_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            decode_hex_audio("not-valid-hex!")

    def test_odd_length_hex_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            decode_hex_audio("abc")  # odd number of hex chars

    def test_round_trip(self) -> None:
        original = b"\x00\xff\x10\x20"
        hex_str = original.hex()
        assert decode_hex_audio(hex_str) == original


# ── AudioResponse ────────────────────────────────────────────────────────────


class TestAudioResponse:
    @pytest.fixture()
    def sample_audio(self) -> AudioResponse:
        return AudioResponse(
            data=b"\x00\x01\x02\x03",
            duration=1234.5,
            sample_rate=32000,
            format="mp3",
            size=4,
        )

    def test_save_writes_correct_bytes(
        self, sample_audio: AudioResponse, tmp_path: Path
    ) -> None:
        dest = tmp_path / "output.mp3"
        sample_audio.save(dest)
        assert dest.read_bytes() == b"\x00\x01\x02\x03"

    def test_save_creates_parent_dirs(
        self, sample_audio: AudioResponse, tmp_path: Path
    ) -> None:
        dest = tmp_path / "sub" / "dir" / "output.mp3"
        sample_audio.save(dest)
        assert dest.exists()
        assert dest.read_bytes() == b"\x00\x01\x02\x03"

    def test_to_base64_returns_correct_encoding(
        self, sample_audio: AudioResponse
    ) -> None:
        result = sample_audio.to_base64()
        expected = base64.b64encode(b"\x00\x01\x02\x03").decode("ascii")
        assert result == expected
        # Verify round-trip
        assert base64.b64decode(result) == b"\x00\x01\x02\x03"

    def test_repr_truncates_data(self, sample_audio: AudioResponse) -> None:
        r = repr(sample_audio)
        assert "<4 bytes>" in r
        assert "duration=1234.5" in r
        assert "sample_rate=32000" in r
        assert "format='mp3'" in r
        assert "size=4" in r
        # The raw bytes must NOT appear in the repr
        assert "\\x00\\x01\\x02\\x03" not in r

    def test_repr_with_large_data(self) -> None:
        big = AudioResponse(
            data=b"\xff" * 100_000,
            duration=5000.0,
            sample_rate=44100,
            format="wav",
            size=100_000,
        )
        r = repr(big)
        assert "<100000 bytes>" in r


# ── build_audio_response ─────────────────────────────────────────────────────


class TestBuildAudioResponse:
    def test_speech_style_response(self) -> None:
        """Nested structure: data.audio + extra_info (T2A v2 style)."""
        raw_bytes = b"Hello audio"
        hex_str = raw_bytes.hex()

        api_response = {
            "data": {"audio": hex_str},
            "extra_info": {
                "audio_length": 2500,
                "audio_sample_rate": 24000,
                "audio_size": len(raw_bytes),
                "audio_format": "mp3",
            },
            "base_resp": {"status_code": 0, "status_msg": ""},
        }

        result = build_audio_response(api_response)

        assert result.data == raw_bytes
        assert result.duration == 2500.0
        assert result.sample_rate == 24000
        assert result.format == "mp3"
        assert result.size == len(raw_bytes)

    def test_flat_style_response(self) -> None:
        """Flattened structure: audio_hex, audio_length, etc. at top level."""
        raw_bytes = b"\xaa\xbb\xcc"
        hex_str = raw_bytes.hex()

        api_response = {
            "audio_hex": hex_str,
            "audio_length": 3000,
            "audio_sample_rate": 16000,
            "audio_size": len(raw_bytes),
            "audio_format": "pcm",
        }

        result = build_audio_response(api_response)

        assert result.data == raw_bytes
        assert result.duration == 3000.0
        assert result.sample_rate == 16000
        assert result.format == "pcm"
        assert result.size == len(raw_bytes)

    def test_empty_audio_returns_empty_bytes(self) -> None:
        """When no audio hex is present, data should be empty bytes."""
        api_response: dict = {}
        result = build_audio_response(api_response)
        assert result.data == b""
        assert result.size == 0

    def test_size_falls_back_to_len_of_decoded_bytes(self) -> None:
        """When audio_size is not provided, size should equal len(data)."""
        raw_bytes = b"some audio data here"
        hex_str = raw_bytes.hex()

        api_response = {
            "data": {"audio": hex_str},
            "extra_info": {
                "audio_length": 1000,
                "audio_sample_rate": 22050,
                "audio_format": "flac",
                # audio_size intentionally omitted
            },
        }

        result = build_audio_response(api_response)
        assert result.size == len(raw_bytes)
