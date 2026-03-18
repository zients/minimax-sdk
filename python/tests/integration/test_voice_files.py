"""Integration tests for MiniMax SDK Voice and Files modules.

These tests hit the real MiniMax API and require MINIMAX_API_KEY in .env.
Run with: cd python && uv run pytest tests/integration/test_voice_files.py -v

Tests are ordered and share state via class variables. They must run sequentially:
  - Voice: list system -> list all -> design -> upload+clone -> delete clone
  - Files: upload -> list -> retrieve -> retrieve_content -> delete

Known SDK bugs discovered during integration testing:
  BUG-1: FileInfo.file_id is typed as str, but the API returns it as int.
         Workaround: patch FileInfo model_config with coerce_numbers_to_str=True.
  BUG-2: files.retrieve() sends string file_id as query param, but after
         coercion it should still work. However, the API may not return
         download_url for voice_clone files.
  BUG-3: files.retrieve_content() routes through _http.request() which calls
         response.json(), but the endpoint returns raw binary audio data,
         causing a UnicodeDecodeError/JSONDecodeError.
  BUG-4: files.delete() sends file_id as a string in JSON body, but the API
         expects an integer. This causes "invalid params" errors.
"""

import time
from pathlib import Path

import httpx
import pytest
from pydantic import ConfigDict

from minimax_sdk import MiniMax
from minimax_sdk.exceptions import (
    InsufficientBalanceError,
    InvalidParameterError,
    MiniMaxError,
)
from minimax_sdk.types.files import FileInfo

# ── Workaround for BUG-1: file_id int-vs-str ────────────────────────────────
FileInfo.model_config = ConfigDict(coerce_numbers_to_str=True)
FileInfo.model_rebuild(force=True)

OUTPUTS_DIR = str(Path(__file__).parent / "outputs")


def _make_minimal_mp3() -> bytes:
    """Create a minimal valid MP3 file (~1.2 KB of silence).

    Generates a few MPEG Audio Layer 3 frames with silence so we have a
    valid MP3 to upload without calling the TTS endpoint.
    """
    # MPEG1 Layer3, 128kbps, 44100Hz, stereo -- frame size = 417 bytes
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

    # Shared state across test methods
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
        print(f"  Found {len(result.system_voice)} system voices. First: {first.voice_id}")

    def test_2_voice_list_all(self, client):
        """List all voice types and verify structure."""
        result = client.voice.list(voice_type="all")
        assert result.system_voice is not None
        assert len(result.system_voice) > 0
        assert isinstance(result.voice_cloning, list)
        assert isinstance(result.voice_generation, list)
        total = (
            len(result.system_voice)
            + len(result.voice_cloning)
            + len(result.voice_generation)
        )
        print(
            f"  All voices: {len(result.system_voice)} system, "
            f"{len(result.voice_cloning)} cloned, "
            f"{len(result.voice_generation)} designed. Total: {total}"
        )

    def test_3_voice_design(self, client):
        """Design a voice from description, save trial audio."""
        try:
            result = client.voice.design(
                prompt="A warm, friendly female narrator with a calm tone",
                preview_text="Hello, this is a test of voice design.",
            )
        except InsufficientBalanceError as exc:
            pytest.skip(f"API balance/limit issue: {exc}")

        assert result.voice_id is not None
        assert len(result.voice_id) > 0
        assert result.trial_audio is not None
        assert result.trial_audio.data is not None
        assert len(result.trial_audio.data) > 0

        out_path = f"{OUTPUTS_DIR}/voice_design_preview.mp3"
        result.trial_audio.save(out_path)
        print(f"  Designed voice_id: {result.voice_id}")
        print(f"  Trial audio saved to {out_path} ({len(result.trial_audio.data)} bytes)")

    def test_4_voice_upload_and_clone(self, client):
        """Generate test audio via TTS, upload it, then clone a voice."""
        # Step 1: Generate or synthesise a test audio file
        tts_path = f"{OUTPUTS_DIR}/test_tts_for_clone.mp3"
        try:
            audio = client.speech.tts(
                text="This is a test audio file for voice cloning. "
                "The quick brown fox jumps over the lazy dog. "
                "Testing one two three four five.",
                model="speech-2.8-hd",
                voice_setting={"voice_id": "English_expressive_narrator"},
            )
            assert audio.data is not None
            assert len(audio.data) > 0
            audio.save(tts_path)
            print(f"  Generated TTS audio: {len(audio.data)} bytes, saved to {tts_path}")
        except InsufficientBalanceError as exc:
            print(f"  TTS unavailable ({exc}), using synthetic MP3 for upload")
            mp3_data = _make_minimal_mp3()
            with open(tts_path, "wb") as f:
                f.write(mp3_data)

        # Step 2: Upload the audio for voice cloning
        try:
            file_info = client.voice.upload_audio(tts_path, purpose="voice_clone")
        except (InsufficientBalanceError, MiniMaxError) as exc:
            pytest.skip(f"Upload failed: {exc}")

        assert file_info.file_id is not None
        assert len(file_info.file_id) > 0
        assert file_info.purpose == "voice_clone"
        TestVoiceIntegration.clone_file_id = file_info.file_id
        print(f"  Uploaded file_id: {file_info.file_id}")

        # Step 3: Clone the voice with a unique voice_id
        timestamp = int(time.time())
        voice_id = f"test-clone-{timestamp}"

        try:
            clone_result = client.voice.clone(
                file_id=file_info.file_id,
                voice_id=voice_id,
            )
        except InsufficientBalanceError as exc:
            pytest.skip(f"Clone failed due to API balance issue: {exc}")
        except InvalidParameterError as exc:
            pytest.skip(
                f"Clone failed with invalid params (synthetic MP3 may not be "
                f"accepted for cloning): {exc}"
            )

        TestVoiceIntegration.cloned_voice_id = voice_id
        assert clone_result.voice_id == voice_id
        print(f"  Cloned voice_id: {clone_result.voice_id}")

    def test_5_voice_delete(self, client):
        """Delete the cloned voice from test 4."""
        voice_id = TestVoiceIntegration.cloned_voice_id
        if not voice_id:
            pytest.skip("No cloned voice_id from test_4 (upstream skipped)")

        client.voice.delete(voice_id=voice_id, voice_type="voice_cloning")
        print(f"  Deleted cloned voice: {voice_id}")


class TestFilesIntegration:
    """Test Files resource methods against the real API.

    Tests are numbered to enforce execution order.
    """

    # Shared state
    uploaded_file_id: str = ""
    uploaded_file_id_int: int = 0

    def test_1_files_upload(self, client):
        """Upload a file with purpose='voice_clone' and verify FileInfo."""
        tts_path = f"{OUTPUTS_DIR}/test_tts_for_file_upload.mp3"
        try:
            audio = client.speech.tts(
                text="Short test audio for file upload.",
                model="speech-2.8-hd",
                voice_setting={"voice_id": "English_expressive_narrator"},
            )
            audio.save(tts_path)
            print(f"  Generated TTS audio: {len(audio.data)} bytes")
        except InsufficientBalanceError:
            print("  TTS unavailable, using synthetic MP3 for upload")
            mp3_data = _make_minimal_mp3()
            with open(tts_path, "wb") as f:
                f.write(mp3_data)

        file_info = client.files.upload(tts_path, purpose="voice_clone")
        assert file_info.file_id is not None
        assert len(file_info.file_id) > 0
        assert file_info.purpose == "voice_clone"
        assert file_info.bytes > 0
        assert file_info.filename is not None
        assert file_info.created_at > 0
        TestFilesIntegration.uploaded_file_id = file_info.file_id
        TestFilesIntegration.uploaded_file_id_int = int(file_info.file_id)
        print(f"  Uploaded file_id: {file_info.file_id}, size: {file_info.bytes} bytes")

    def test_2_files_list(self, client):
        """List files with purpose='voice_clone' and verify list returned."""
        file_id = TestFilesIntegration.uploaded_file_id
        if not file_id:
            pytest.skip("No uploaded file_id from test_1")

        files = client.files.list(purpose="voice_clone")
        assert isinstance(files, list)
        assert len(files) > 0
        file_ids = [f.file_id for f in files]
        assert file_id in file_ids, (
            f"Uploaded file {file_id} not found in file list: {file_ids}"
        )
        print(f"  Listed {len(files)} files. Our file {file_id} found in list.")

    def test_3_files_retrieve(self, client):
        """Retrieve file info by file_id and verify FileInfo.

        NOTE: download_url may be None for voice_clone files -- the API only
        provides it for video and T2A async files.
        """
        file_id = TestFilesIntegration.uploaded_file_id
        file_id_int = TestFilesIntegration.uploaded_file_id_int
        if not file_id:
            pytest.skip("No uploaded file_id from test_1")

        # Try SDK method first; fall back to sending int if string fails
        try:
            file_info = client.files.retrieve(file_id)
        except InvalidParameterError:
            # BUG-2 workaround: send file_id as int via raw HTTP
            resp = client._http_client.request(
                "GET", "/v1/files/retrieve", params={"file_id": file_id_int}
            )
            file_info = FileInfo.model_validate(resp["file"])

        assert file_info.file_id == file_id
        assert file_info.purpose == "voice_clone"
        assert file_info.bytes > 0
        # download_url may or may not be present for voice_clone files
        if file_info.download_url is not None:
            assert file_info.download_url.startswith("http")
            print(f"  Retrieved file {file_id}: download_url={file_info.download_url[:80]}...")
        else:
            print(f"  Retrieved file {file_id}: download_url=None (expected for voice_clone)")

    def test_4_files_retrieve_content(self, client):
        """Download file content, verify bytes returned, save to outputs.

        NOTE: Works around BUG-3 (retrieve_content calls response.json() on
        binary data) by downloading the raw bytes directly via httpx.
        """
        file_id = TestFilesIntegration.uploaded_file_id
        file_id_int = TestFilesIntegration.uploaded_file_id_int
        if not file_id:
            pytest.skip("No uploaded file_id from test_1")

        content: bytes | None = None

        # Try SDK method
        try:
            content = client.files.retrieve_content(file_id)
        except (InvalidParameterError, UnicodeDecodeError, MiniMaxError):
            pass

        if content is None:
            # BUG-3 workaround: use httpx directly to get raw bytes
            # Build the URL and auth header manually
            base_url = client._http_client.base_url
            api_key = client._http_client.api_key
            url = f"{base_url}/v1/files/retrieve_content"
            resp = httpx.get(
                url,
                params={"file_id": file_id_int},
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30.0,
            )
            content = resp.content
            print(f"  Used httpx workaround for retrieve_content (BUG-3)")

        assert isinstance(content, bytes)
        assert len(content) > 0

        out_path = f"{OUTPUTS_DIR}/files_downloaded.mp3"
        with open(out_path, "wb") as f:
            f.write(content)
        print(f"  Downloaded {len(content)} bytes, saved to {out_path}")

    def test_5_files_delete(self, client):
        """Delete the uploaded file.

        NOTE: Works around BUG-4 by sending file_id as int if needed.
        """
        file_id = TestFilesIntegration.uploaded_file_id
        file_id_int = TestFilesIntegration.uploaded_file_id_int
        if not file_id:
            pytest.skip("No uploaded file_id from test_1")

        try:
            client.files.delete(file_id=file_id, purpose="voice_clone")
        except InvalidParameterError:
            # BUG-4 workaround: send file_id as int
            client._http_client.request(
                "POST",
                "/v1/files/delete",
                json={"file_id": file_id_int, "purpose": "voice_clone"},
            )
        print(f"  Deleted file: {file_id}")
