"""Image resource -- synchronous and asynchronous image generation.

Provides both synchronous (:class:`Image`) and asynchronous (:class:`AsyncImage`)
clients for the MiniMax Image Generation API (``POST /v1/image_generation``).
"""

from __future__ import annotations

from typing import Any

from .._base import AsyncResource, SyncResource
from ..types.image import ImageResult


def _build_image_body(
    prompt: str,
    model: str,
    *,
    aspect_ratio: str | None,
    width: int | None,
    height: int | None,
    response_format: str,
    seed: int | None,
    n: int,
    prompt_optimizer: bool,
    subject_reference: list[dict] | None,
) -> dict[str, Any]:
    """Build the JSON request body for image generation, excluding None values."""
    body: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "response_format": response_format,
        "n": n,
        "prompt_optimizer": prompt_optimizer,
    }

    if aspect_ratio is not None:
        body["aspect_ratio"] = aspect_ratio
    if width is not None:
        body["width"] = width
    if height is not None:
        body["height"] = height
    if seed is not None:
        body["seed"] = seed
    if subject_reference is not None:
        body["subject_reference"] = subject_reference

    return body


def _parse_image_result(resp: dict[str, Any]) -> ImageResult:
    """Parse a raw API response dict into an :class:`ImageResult`."""
    data = resp.get("data", {})
    metadata = resp.get("metadata", {})

    return ImageResult(
        id=resp["id"],
        image_urls=data.get("image_urls"),
        image_base64=data.get("image_base64"),
        success_count=metadata.get("success_count", 0),
        failed_count=metadata.get("failed_count", 0),
    )


# -- Sync ---------------------------------------------------------------------


class Image(SyncResource):
    """Synchronous image generation resource.

    Supports text-to-image (T2I) and image-to-image (I2I) generation via the
    same ``generate`` method.  Pass ``subject_reference`` for I2I mode.
    """

    def generate(
        self,
        prompt: str,
        model: str = "image-01",
        *,
        aspect_ratio: str | None = None,
        width: int | None = None,
        height: int | None = None,
        response_format: str = "url",
        seed: int | None = None,
        n: int = 1,
        prompt_optimizer: bool = False,
        subject_reference: list[dict] | None = None,
    ) -> ImageResult:
        """Generate one or more images from a text prompt.

        Args:
            prompt: The text description of the desired image(s).
            model: The model identifier (default ``"image-01"``).
            aspect_ratio: Aspect ratio hint (e.g. ``"16:9"``).  Mutually
                exclusive with explicit *width*/*height*.
            width: Desired image width in pixels.
            height: Desired image height in pixels.
            response_format: ``"url"`` (default) returns temporary download
                URLs; ``"base64"`` returns base64-encoded image data.
            seed: Random seed for reproducibility.
            n: Number of images to generate (default ``1``).
            prompt_optimizer: Whether to let the API optimise the prompt.
            subject_reference: A list of subject-reference dicts for I2I mode.
                Each dict should contain ``"type"`` (e.g. ``"character"``) and
                ``"image_file"`` (a public URL or base64 data URL).

        Returns:
            An :class:`ImageResult` containing generated image URLs or base64
            data, plus success/failure counts.
        """
        body = _build_image_body(
            prompt,
            model,
            aspect_ratio=aspect_ratio,
            width=width,
            height=height,
            response_format=response_format,
            seed=seed,
            n=n,
            prompt_optimizer=prompt_optimizer,
            subject_reference=subject_reference,
        )

        resp = self._http.request("POST", "/v1/image_generation", json=body)
        return _parse_image_result(resp)


# -- Async --------------------------------------------------------------------


class AsyncImage(AsyncResource):
    """Asynchronous image generation resource.

    Supports text-to-image (T2I) and image-to-image (I2I) generation via the
    same ``generate`` method.  Pass ``subject_reference`` for I2I mode.
    """

    async def generate(
        self,
        prompt: str,
        model: str = "image-01",
        *,
        aspect_ratio: str | None = None,
        width: int | None = None,
        height: int | None = None,
        response_format: str = "url",
        seed: int | None = None,
        n: int = 1,
        prompt_optimizer: bool = False,
        subject_reference: list[dict] | None = None,
    ) -> ImageResult:
        """Generate one or more images from a text prompt.

        Args:
            prompt: The text description of the desired image(s).
            model: The model identifier (default ``"image-01"``).
            aspect_ratio: Aspect ratio hint (e.g. ``"16:9"``).  Mutually
                exclusive with explicit *width*/*height*.
            width: Desired image width in pixels.
            height: Desired image height in pixels.
            response_format: ``"url"`` (default) returns temporary download
                URLs; ``"base64"`` returns base64-encoded image data.
            seed: Random seed for reproducibility.
            n: Number of images to generate (default ``1``).
            prompt_optimizer: Whether to let the API optimise the prompt.
            subject_reference: A list of subject-reference dicts for I2I mode.
                Each dict should contain ``"type"`` (e.g. ``"character"``) and
                ``"image_file"`` (a public URL or base64 data URL).

        Returns:
            An :class:`ImageResult` containing generated image URLs or base64
            data, plus success/failure counts.
        """
        body = _build_image_body(
            prompt,
            model,
            aspect_ratio=aspect_ratio,
            width=width,
            height=height,
            response_format=response_format,
            seed=seed,
            n=n,
            prompt_optimizer=prompt_optimizer,
            subject_reference=subject_reference,
        )

        resp = await self._http.request("POST", "/v1/image_generation", json=body)
        return _parse_image_result(resp)
