"""Tests for the Image resource."""

from __future__ import annotations

from unittest.mock import MagicMock

from minimax_sdk.resources.image import Image
from minimax_sdk.types.image import ImageResult


# ── Helpers ──────────────────────────────────────────────────────────────────


def _ok_resp(payload: dict) -> dict:
    """Wrap a payload in a successful API response envelope."""
    return {"base_resp": {"status_code": 0, "status_msg": "success"}, **payload}


def _make_image_resource() -> tuple[Image, MagicMock]:
    """Create an Image resource with mocked _http.

    Image.generate() calls self._http.request().
    """
    mock_http = MagicMock()
    mock_client = MagicMock()
    image = Image(mock_http, client=mock_client)
    return image, mock_http


# ── Tests ────────────────────────────────────────────────────────────────────


class TestImageGenerateT2I:
    """Tests for image.generate() in text-to-image mode."""

    def test_generate_t2i_returns_image_result_with_urls(self):
        """T2I generates images and returns ImageResult with image_urls."""
        image, mock_client = _make_image_resource()
        mock_client.request.return_value = _ok_resp({
            "id": "img_001",
            "data": {
                "image_urls": [
                    "https://cdn.minimax.io/images/img_001_0.png",
                    "https://cdn.minimax.io/images/img_001_1.png",
                ],
            },
            "metadata": {
                "success_count": 2,
                "failed_count": 0,
            },
        })

        result = image.generate(
            prompt="A beautiful sunset over the ocean",
            model="image-01",
            n=2,
        )

        assert isinstance(result, ImageResult)
        assert result.id == "img_001"
        assert result.image_urls is not None
        assert len(result.image_urls) == 2
        assert result.image_base64 is None
        assert result.success_count == 2
        assert result.failed_count == 0

        # Verify request
        mock_client.request.assert_called_once()
        call_args = mock_client.request.call_args
        assert call_args[0] == ("POST", "/v1/image_generation")
        body = call_args[1]["json"]
        assert body["prompt"] == "A beautiful sunset over the ocean"
        assert body["model"] == "image-01"
        assert body["n"] == 2
        assert body["response_format"] == "url"


class TestImageGenerateI2I:
    """Tests for image.generate() in image-to-image mode (with subject_reference)."""

    def test_generate_i2i_with_subject_reference(self):
        """I2I mode includes subject_reference in the request body."""
        image, mock_client = _make_image_resource()
        mock_client.request.return_value = _ok_resp({
            "id": "img_002",
            "data": {
                "image_urls": ["https://cdn.minimax.io/images/img_002_0.png"],
            },
            "metadata": {
                "success_count": 1,
                "failed_count": 0,
            },
        })

        subject_ref = [
            {"type": "character", "image_file": "https://example.com/person.jpg"},
        ]

        result = image.generate(
            prompt="A person at a beach",
            model="image-01",
            subject_reference=subject_ref,
        )

        assert isinstance(result, ImageResult)
        assert result.id == "img_002"

        # Verify subject_reference was included in the body
        body = mock_client.request.call_args[1]["json"]
        assert body["subject_reference"] == subject_ref


class TestImageGenerateBase64:
    """Tests for image.generate() with response_format='base64'."""

    def test_generate_with_base64_format_returns_image_base64(self):
        """response_format='base64' returns ImageResult with image_base64."""
        image, mock_client = _make_image_resource()
        mock_client.request.return_value = _ok_resp({
            "id": "img_003",
            "data": {
                "image_base64": ["iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAA..."],
            },
            "metadata": {
                "success_count": 1,
                "failed_count": 0,
            },
        })

        result = image.generate(
            prompt="A red circle",
            model="image-01",
            response_format="base64",
        )

        assert isinstance(result, ImageResult)
        assert result.id == "img_003"
        assert result.image_base64 is not None
        assert len(result.image_base64) == 1
        assert result.image_urls is None

        # Verify response_format was sent in the body
        body = mock_client.request.call_args[1]["json"]
        assert body["response_format"] == "base64"


# ── _build_image_body coverage ──────────────────────────────────────────────

from minimax_sdk.resources.image import _build_image_body


class TestBuildImageBody:
    """Cover all optional branches of _build_image_body."""

    def test_all_optional_params(self):
        body = _build_image_body(
            "test prompt",
            "image-01",
            aspect_ratio="16:9",
            width=1280,
            height=720,
            response_format="url",
            seed=42,
            n=2,
            prompt_optimizer=True,
            subject_reference=[{"type": "character", "image_file": "img.jpg"}],
        )
        assert body["aspect_ratio"] == "16:9"
        assert body["width"] == 1280
        assert body["height"] == 720
        assert body["seed"] == 42
        assert body["subject_reference"] == [{"type": "character", "image_file": "img.jpg"}]


class TestImageGenerateAllParams:
    """Test image.generate() with all optional params to cover body-building branches."""

    def test_generate_with_aspect_ratio_width_height_seed(self):
        """Cover aspect_ratio, width, height, seed branches."""
        image, mock_client = _make_image_resource()
        mock_client.request.return_value = _ok_resp({
            "id": "img_004",
            "data": {"image_urls": ["https://cdn.minimax.io/images/img_004_0.png"]},
            "metadata": {"success_count": 1, "failed_count": 0},
        })

        result = image.generate(
            prompt="A landscape",
            model="image-01",
            aspect_ratio="16:9",
            width=1920,
            height=1080,
            seed=12345,
            n=1,
            prompt_optimizer=True,
        )

        assert isinstance(result, ImageResult)
        body = mock_client.request.call_args[1]["json"]
        assert body["aspect_ratio"] == "16:9"
        assert body["width"] == 1920
        assert body["height"] == 1080
        assert body["seed"] == 12345
        assert body["prompt_optimizer"] is True


# ── Async Tests ─────────────────────────────────────────────────────────────

from unittest.mock import AsyncMock

import pytest

from minimax_sdk.resources.image import AsyncImage


def _make_async_image_resource() -> tuple[AsyncImage, MagicMock]:
    """Create an AsyncImage resource with mocked _http."""
    mock_http = AsyncMock()
    mock_client = AsyncMock()
    image = AsyncImage(mock_http, client=mock_client)
    return image, mock_http


class TestAsyncImageGenerate:
    """Tests for async image.generate()."""

    @pytest.mark.asyncio
    async def test_generate_returns_image_result(self):
        """Async image.generate() returns ImageResult with image_urls."""
        image, mock_client = _make_async_image_resource()
        mock_client.request.return_value = _ok_resp({
            "id": "img_async_001",
            "data": {
                "image_urls": ["https://cdn.minimax.io/images/async_001.png"],
            },
            "metadata": {"success_count": 1, "failed_count": 0},
        })

        result = await image.generate(
            prompt="A sunset",
            model="image-01",
            n=1,
        )

        assert isinstance(result, ImageResult)
        assert result.id == "img_async_001"
        assert result.image_urls is not None
        assert len(result.image_urls) == 1

        mock_client.request.assert_awaited_once()
        call_args = mock_client.request.call_args
        assert call_args[0] == ("POST", "/v1/image_generation")
        body = call_args[1]["json"]
        assert body["prompt"] == "A sunset"

    @pytest.mark.asyncio
    async def test_generate_with_all_options(self):
        """Async image.generate() with all optional parameters."""
        image, mock_client = _make_async_image_resource()
        mock_client.request.return_value = _ok_resp({
            "id": "img_async_002",
            "data": {"image_base64": ["base64data"]},
            "metadata": {"success_count": 1, "failed_count": 0},
        })

        result = await image.generate(
            prompt="A red circle",
            model="image-01",
            aspect_ratio="1:1",
            width=512,
            height=512,
            response_format="base64",
            seed=99,
            n=1,
            prompt_optimizer=True,
            subject_reference=[{"type": "character", "image_file": "test.jpg"}],
        )

        assert isinstance(result, ImageResult)
        body = mock_client.request.call_args[1]["json"]
        assert body["aspect_ratio"] == "1:1"
        assert body["width"] == 512
        assert body["height"] == 512
        assert body["seed"] == 99
        assert body["subject_reference"] == [{"type": "character", "image_file": "test.jpg"}]
