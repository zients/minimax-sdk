"""Type definitions for the Files resource."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class FileInfo(BaseModel):
    """Information about an uploaded file."""

    model_config = ConfigDict(coerce_numbers_to_str=True)

    file_id: str
    bytes: int
    created_at: int
    filename: str
    purpose: str
    download_url: Optional[str] = None


class FileList(BaseModel):
    """Result of listing files."""

    files: list[FileInfo] = []
