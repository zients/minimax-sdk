"""Integration tests for MiniMax SDK — Image module.

These tests hit the real MiniMax API and require MINIMAX_API_KEY in .env.
Run with: cd python && uv run pytest tests/integration/test_image.py -v
"""

import pytest

from minimax_sdk import MiniMax


@pytest.fixture(scope="module")
def client():
    """Create a real MiniMax client from .env."""
    c = MiniMax()
    yield c


class TestImageIntegration:
    """Test Image generation with real MiniMax API."""

    def test_generate_url_format(self, client: MiniMax):
        """Generate 1 image with response_format='url', verify URL returned."""
        result = client.image.generate(
            prompt="A red circle on white background",
            model="image-01",
            n=1,
            response_format="url",
        )

        assert result.image_urls is not None, "image_urls should not be None"
        assert len(result.image_urls) == 1, f"Expected 1 URL, got {len(result.image_urls)}"
        assert result.image_urls[0].startswith("http"), "URL should start with http"
        assert result.success_count >= 1

    def test_generate_multiple(self, client: MiniMax):
        """Generate 2 images with n=2, verify success_count=2."""
        result = client.image.generate(
            prompt="A blue square",
            model="image-01",
            n=2,
            response_format="url",
        )

        assert result.success_count == 2, f"Expected success_count=2, got {result.success_count}"
        assert result.image_urls is not None, "image_urls should not be None"
        assert len(result.image_urls) == 2, f"Expected 2 URLs, got {len(result.image_urls)}"

    def test_generate_aspect_ratio(self, client: MiniMax):
        """Generate with aspect_ratio='16:9', verify success."""
        result = client.image.generate(
            prompt="A red circle on white background",
            model="image-01",
            n=1,
            aspect_ratio="16:9",
            response_format="url",
        )

        assert result.success_count >= 1, f"Expected success_count>=1, got {result.success_count}"
        assert result.image_urls is not None, "image_urls should not be None"
        assert len(result.image_urls) >= 1

    def test_generate_base64(self, client: MiniMax):
        """Generate with response_format='base64', verify base64 data returned."""
        result = client.image.generate(
            prompt="A red circle on white background",
            model="image-01",
            n=1,
            response_format="base64",
        )

        assert result.image_base64 is not None, "image_base64 should not be None"
        assert len(result.image_base64) == 1, f"Expected 1 base64 entry, got {len(result.image_base64)}"
        assert len(result.image_base64[0]) > 0, "base64 data should not be empty"
        assert result.success_count >= 1

    def test_generate_with_prompt_optimizer(self, client: MiniMax):
        """Generate with prompt_optimizer=True."""
        result = client.image.generate(
            prompt="A blue square",
            model="image-01",
            n=1,
            prompt_optimizer=True,
            response_format="url",
        )

        assert result.success_count >= 1, f"Expected success_count>=1, got {result.success_count}"
        assert result.image_urls is not None, "image_urls should not be None"
        assert len(result.image_urls) >= 1
