"""Integration tests for MiniMax SDK — Files module.

Self-contained: uploads a synthetic MP3, tests all operations, then deletes it.
No token/credit consumption.

Run with: cd python && uv run pytest tests/integration/test_files.py -v
"""

import os
import tempfile
from pathlib import Path

import pytest

from minimax_sdk import MiniMax


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


class TestFilesIntegration:
    """Test Files resource methods against the real API.

    Self-contained: uploads a synthetic MP3, tests all operations, then deletes it.
    Tests are numbered to enforce execution order.
    """

    uploaded_file_id: str = ""

    def test_1_files_upload(self, client):
        """Upload a synthetic MP3 with purpose='voice_clone'."""
        mp3_data = _make_minimal_mp3()
        tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=".mp3")
        os.close(tmp_fd)
        tmp_path = Path(tmp_path_str)
        try:
            tmp_path.write_bytes(mp3_data)
            file_info = client.files.upload(str(tmp_path), purpose="voice_clone")
        finally:
            tmp_path.unlink(missing_ok=True)

        assert file_info.file_id is not None
        assert len(file_info.file_id) > 0
        assert file_info.purpose == "voice_clone"
        assert file_info.bytes > 0
        assert file_info.filename is not None
        assert file_info.created_at > 0
        TestFilesIntegration.uploaded_file_id = file_info.file_id

    def test_2_files_list(self, client):
        """Verify uploaded file appears in list."""
        file_id = TestFilesIntegration.uploaded_file_id
        if not file_id:
            pytest.skip("No file_id from test_1")

        files = client.files.list(purpose="voice_clone")
        assert isinstance(files, list)
        assert len(files) > 0
        file_ids = [f.file_id for f in files]
        assert file_id in file_ids, f"Uploaded file {file_id} not found in list"

    def test_3_files_retrieve(self, client):
        """Retrieve uploaded file info by file_id."""
        file_id = TestFilesIntegration.uploaded_file_id
        if not file_id:
            pytest.skip("No file_id from test_1")

        file_info = client.files.retrieve(file_id)

        assert file_info.file_id == file_id
        assert file_info.purpose == "voice_clone"
        assert file_info.bytes > 0

    def test_4_files_retrieve_content(self, client):
        """Download uploaded file content, verify it matches what we uploaded."""
        file_id = TestFilesIntegration.uploaded_file_id
        if not file_id:
            pytest.skip("No file_id from test_1")

        content = client.files.retrieve_content(file_id)

        assert isinstance(content, bytes)
        assert len(content) > 0
        expected = _make_minimal_mp3()
        assert content == expected, f"Downloaded {len(content)} bytes != uploaded {len(expected)} bytes"

    def test_5_files_delete(self, client):
        """Delete the uploaded file."""
        file_id = TestFilesIntegration.uploaded_file_id
        if not file_id:
            pytest.skip("No file_id from test_1")

        client.files.delete(file_id=file_id, purpose="voice_clone")
