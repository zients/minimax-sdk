"""Type definitions for the Image resource."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ImageSubjectReference(BaseModel):
    """Subject reference for image-to-image generation."""

    type: str  # Currently only "character"
    image_file: str  # Public URL or base64 data URL


class ImageResult(BaseModel):
    """Result of an image generation request."""

    id: str
    image_urls: Optional[list[str]] = None
    image_base64: Optional[list[str]] = None
    success_count: int = 0
    failed_count: int = 0
