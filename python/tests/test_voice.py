"""Tests for the Voice resource."""

from __future__ import annotations

from unittest.mock import MagicMock

from minimax_sdk._audio import AudioResponse
from minimax_sdk.resources.voice import Voice
from minimax_sdk.types.voice import VoiceCloneResult, VoiceDesignResult, VoiceList


# ── Helpers ──────────────────────────────────────────────────────────────────


def _ok_resp(payload: dict) -> dict:
    """Wrap a payload in a successful API response envelope."""
    return {"base_resp": {"status_code": 0, "status_msg": "success"}, **payload}


def _make_voice_resource() -> tuple[Voice, MagicMock]:
    """Create a Voice resource with a mocked HttpClient."""
    mock_http = MagicMock()
    voice = Voice(mock_http, client=None)
    return voice, mock_http


# Some sample hex-encoded audio (b"hello" -> hex "68656c6c6f")
_SAMPLE_HEX = "68656c6c6f"
_SAMPLE_BYTES = bytes.fromhex(_SAMPLE_HEX)


# ── Tests ────────────────────────────────────────────────────────────────────


class TestVoiceClone:
    """Tests for voice.clone()."""

    def test_clone_returns_voice_clone_result_with_voice_id(self):
        """voice.clone() returns a VoiceCloneResult with the correct voice_id."""
        voice, mock_http = _make_voice_resource()
        mock_http.request.return_value = _ok_resp({
            "input_sensitive": {"is_sensitive": False},
        })

        result = voice.clone(file_id="123456", voice_id="my_voice")

        assert isinstance(result, VoiceCloneResult)
        assert result.voice_id == "my_voice"
        assert result.demo_audio is None
        assert result.input_sensitive == {"is_sensitive": False}

        # Verify the request body
        mock_http.request.assert_called_once()
        call_kwargs = mock_http.request.call_args
        assert call_kwargs[0] == ("POST", "/v1/voice_clone")
        body = call_kwargs[1]["json"]
        assert body["file_id"] == 123456
        assert body["voice_id"] == "my_voice"

    def test_clone_with_demo_audio_url(self):
        """voice.clone() with demo_audio URL in the response."""
        voice, mock_http = _make_voice_resource()
        mock_http.request.return_value = _ok_resp({
            "demo_audio": "https://cdn.minimax.io/demo/preview.mp3",
            "input_sensitive": False,
        })

        result = voice.clone(
            file_id="123456",
            voice_id="my_voice",
            text="Hello world",
            model="speech-2.8-hd",
        )

        assert isinstance(result, VoiceCloneResult)
        assert result.voice_id == "my_voice"
        assert result.demo_audio == "https://cdn.minimax.io/demo/preview.mp3"

    def test_clone_without_demo_audio(self):
        """voice.clone() with empty demo_audio returns None."""
        voice, mock_http = _make_voice_resource()
        mock_http.request.return_value = _ok_resp({
            "demo_audio": "",
            "input_sensitive": False,
        })

        result = voice.clone(file_id="123456", voice_id="my_voice")

        assert result.demo_audio is None


class TestVoiceDesign:
    """Tests for voice.design()."""

    def test_design_returns_voice_design_result_with_trial_audio(self):
        """voice.design() returns VoiceDesignResult with trial_audio AudioResponse."""
        voice, mock_http = _make_voice_resource()
        mock_http.request.return_value = _ok_resp({
            "voice_id": "generated_voice_42",
            "trial_audio": {
                "data": {"audio": _SAMPLE_HEX},
                "extra_info": {
                    "audio_length": 2000.0,
                    "audio_sample_rate": 24000,
                    "audio_size": len(_SAMPLE_BYTES),
                    "audio_format": "mp3",
                },
            },
        })

        result = voice.design(
            prompt="warm female narrator with a British accent",
            preview_text="Hello, this is a test.",
        )

        assert isinstance(result, VoiceDesignResult)
        assert result.voice_id == "generated_voice_42"
        assert isinstance(result.trial_audio, AudioResponse)
        assert result.trial_audio.data == _SAMPLE_BYTES
        assert result.trial_audio.duration == 2000.0
        assert result.trial_audio.sample_rate == 24000

        # Verify request body
        call_kwargs = mock_http.request.call_args
        assert call_kwargs[0] == ("POST", "/v1/voice_design")
        body = call_kwargs[1]["json"]
        assert body["prompt"] == "warm female narrator with a British accent"
        assert body["preview_text"] == "Hello, this is a test."


class TestVoiceList:
    """Tests for voice.list()."""

    def test_list_returns_voice_list_with_all_categories(self):
        """voice.list() returns VoiceList with system, cloned, and generated voices."""
        voice, mock_http = _make_voice_resource()
        mock_http.request.return_value = _ok_resp({
            "system_voice": [
                {"voice_id": "sys_1", "voice_name": "Narrator", "description": ["male"]},
            ],
            "voice_cloning": [
                {"voice_id": "clone_1", "description": ["custom"], "created_time": "2026-01-01"},
            ],
            "voice_generation": [
                {"voice_id": "gen_1", "description": ["designed"], "created_time": "2026-02-01"},
            ],
        })

        result = voice.list(voice_type="all")

        assert isinstance(result, VoiceList)
        assert len(result.system_voice) == 1
        assert result.system_voice[0].voice_id == "sys_1"
        assert result.system_voice[0].voice_name == "Narrator"
        assert len(result.voice_cloning) == 1
        assert result.voice_cloning[0].voice_id == "clone_1"
        assert len(result.voice_generation) == 1
        assert result.voice_generation[0].voice_id == "gen_1"

        mock_http.request.assert_called_once_with(
            "POST", "/v1/get_voice", json={"voice_type": "all"}
        )


class TestVoiceDelete:
    """Tests for voice.delete()."""

    def test_delete_returns_none(self):
        """voice.delete() returns None on success."""
        voice, mock_http = _make_voice_resource()
        mock_http.request.return_value = _ok_resp({})

        result = voice.delete(voice_id="my_voice", voice_type="voice_cloning")

        assert result is None
        mock_http.request.assert_called_once_with(
            "POST",
            "/v1/delete_voice",
            json={"voice_id": "my_voice", "voice_type": "voice_cloning"},
        )


# ── Additional sync coverage ────────────────────────────────────────────────


class TestVoiceCloneAllOptions:
    """Test voice.clone() with all optional parameters to cover helper branches."""

    def test_clone_with_all_optional_params(self):
        """voice.clone() with clone_prompt, language_boost, and noise/volume flags."""
        voice, mock_http = _make_voice_resource()
        mock_http.request.return_value = _ok_resp({
            "input_sensitive": None,
        })

        result = voice.clone(
            file_id="123456",
            voice_id="my_voice",
            clone_prompt={"prompt_audio": "file_456", "prompt_text": "Hello"},
            text="Hello world",
            model="speech-2.8-hd",
            language_boost="en",
            need_noise_reduction=True,
            need_volume_normalization=True,
        )

        assert isinstance(result, VoiceCloneResult)
        body = mock_http.request.call_args[1]["json"]
        assert body["clone_prompt"] == {"prompt_audio": "file_456", "prompt_text": "Hello"}
        assert body["text"] == "Hello world"
        assert body["model"] == "speech-2.8-hd"
        assert body["language_boost"] == "en"
        assert body["need_noise_reduction"] is True
        assert body["need_volume_normalization"] is True


class TestVoiceDesignWithId:
    """Test voice.design() with an explicit voice_id."""

    def test_design_with_voice_id(self):
        """voice.design() passes voice_id when provided."""
        voice, mock_http = _make_voice_resource()
        mock_http.request.return_value = _ok_resp({
            "voice_id": "custom_id",
            "trial_audio": {
                "data": {"audio": _SAMPLE_HEX},
                "extra_info": {
                    "audio_length": 1000.0,
                    "audio_sample_rate": 24000,
                    "audio_size": len(_SAMPLE_BYTES),
                    "audio_format": "mp3",
                },
            },
        })

        result = voice.design(
            prompt="deep male voice",
            preview_text="Testing",
            voice_id="custom_id",
        )

        assert result.voice_id == "custom_id"
        body = mock_http.request.call_args[1]["json"]
        assert body["voice_id"] == "custom_id"


class TestVoiceUploadAudio:
    """Test voice.upload_audio() delegates to client.files.upload."""

    def test_upload_audio_delegates_to_files(self):
        """voice.upload_audio() calls self._client.files.upload."""
        mock_http = MagicMock()
        mock_client = MagicMock()
        voice = Voice(mock_http, client=mock_client)

        from minimax_sdk.types.files import FileInfo

        mock_client.files.upload.return_value = FileInfo(
            file_id="uploaded_file",
            bytes=1024,
            created_at=1710000000,
            filename="audio.wav",
            purpose="voice_clone",
        )

        import io
        bio = io.BytesIO(b"audio data")
        result = voice.upload_audio(bio, purpose="voice_clone")

        assert result.file_id == "uploaded_file"
        mock_client.files.upload.assert_called_once_with(bio, "voice_clone")


# ── Async Tests ─────────────────────────────────────────────────────────────

from unittest.mock import AsyncMock

import pytest

from minimax_sdk.resources.voice import AsyncVoice


def _make_async_voice_resource() -> tuple[AsyncVoice, AsyncMock]:
    """Create an AsyncVoice resource with a mocked AsyncHttpClient."""
    mock_http = AsyncMock()
    mock_client = MagicMock()
    # Set up async files.upload on the mock client
    mock_client.files = MagicMock()
    mock_client.files.upload = AsyncMock()
    voice = AsyncVoice(mock_http, client=mock_client)
    return voice, mock_http


class TestAsyncVoiceClone:
    """Tests for async voice.clone()."""

    @pytest.mark.asyncio
    async def test_clone_returns_voice_clone_result(self):
        """Async voice.clone() returns VoiceCloneResult."""
        voice, mock_http = _make_async_voice_resource()
        mock_http.request.return_value = _ok_resp({
            "input_sensitive": {"is_sensitive": False},
        })

        result = await voice.clone(file_id="123456", voice_id="my_voice")

        assert isinstance(result, VoiceCloneResult)
        assert result.voice_id == "my_voice"
        assert result.demo_audio is None

    @pytest.mark.asyncio
    async def test_clone_with_all_params(self):
        """Async voice.clone() with all optional params."""
        voice, mock_http = _make_async_voice_resource()
        mock_http.request.return_value = _ok_resp({
            "demo_audio": "https://cdn.minimax.io/demo/preview.mp3",
            "input_sensitive": False,
        })

        result = await voice.clone(
            file_id="123456",
            voice_id="my_voice",
            clone_prompt={"prompt_audio": "f1", "prompt_text": "Hi"},
            text="Hello world",
            model="speech-2.8-hd",
            language_boost="zh",
            need_noise_reduction=True,
            need_volume_normalization=True,
        )

        assert isinstance(result, VoiceCloneResult)
        assert result.demo_audio == "https://cdn.minimax.io/demo/preview.mp3"
        body = mock_http.request.call_args[1]["json"]
        assert body["language_boost"] == "zh"


class TestAsyncVoiceDesign:
    """Tests for async voice.design()."""

    @pytest.mark.asyncio
    async def test_design_returns_voice_design_result(self):
        """Async voice.design() returns VoiceDesignResult."""
        voice, mock_http = _make_async_voice_resource()
        mock_http.request.return_value = _ok_resp({
            "voice_id": "gen_42",
            "trial_audio": {
                "data": {"audio": _SAMPLE_HEX},
                "extra_info": {
                    "audio_length": 2000.0,
                    "audio_sample_rate": 24000,
                    "audio_size": len(_SAMPLE_BYTES),
                    "audio_format": "mp3",
                },
            },
        })

        result = await voice.design(
            prompt="warm narrator",
            preview_text="Hello test",
            voice_id="gen_42",
        )

        assert isinstance(result, VoiceDesignResult)
        assert result.voice_id == "gen_42"
        assert result.trial_audio.data == _SAMPLE_BYTES


class TestAsyncVoiceList:
    """Tests for async voice.list()."""

    @pytest.mark.asyncio
    async def test_list_returns_voice_list(self):
        """Async voice.list() returns VoiceList."""
        voice, mock_http = _make_async_voice_resource()
        mock_http.request.return_value = _ok_resp({
            "system_voice": [
                {"voice_id": "sys_1", "voice_name": "Narrator", "description": ["male"]},
            ],
            "voice_cloning": [],
            "voice_generation": [],
        })

        result = await voice.list(voice_type="system")

        assert isinstance(result, VoiceList)
        assert len(result.system_voice) == 1
        assert result.system_voice[0].voice_id == "sys_1"
        mock_http.request.assert_awaited_once_with(
            "POST", "/v1/get_voice", json={"voice_type": "system"}
        )


class TestAsyncVoiceDelete:
    """Tests for async voice.delete()."""

    @pytest.mark.asyncio
    async def test_delete_returns_none(self):
        """Async voice.delete() returns None."""
        voice, mock_http = _make_async_voice_resource()
        mock_http.request.return_value = _ok_resp({})

        result = await voice.delete(voice_id="v1", voice_type="voice_cloning")

        assert result is None
        mock_http.request.assert_awaited_once_with(
            "POST",
            "/v1/delete_voice",
            json={"voice_id": "v1", "voice_type": "voice_cloning"},
        )


class TestAsyncVoiceUploadAudio:
    """Tests for async voice.upload_audio()."""

    @pytest.mark.asyncio
    async def test_upload_audio_delegates_to_files(self):
        """Async voice.upload_audio() calls self._client.files.upload."""
        voice, mock_http = _make_async_voice_resource()

        from minimax_sdk.types.files import FileInfo
        import io

        voice._client.files.upload.return_value = FileInfo(
            file_id="uploaded_file",
            bytes=1024,
            created_at=1710000000,
            filename="audio.wav",
            purpose="voice_clone",
        )

        bio = io.BytesIO(b"audio data")
        result = await voice.upload_audio(bio, purpose="voice_clone")

        assert result.file_id == "uploaded_file"
        voice._client.files.upload.assert_awaited_once_with(bio, "voice_clone")
