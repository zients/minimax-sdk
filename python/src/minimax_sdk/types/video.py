"""Type definitions for the Video resource."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SubjectReference(BaseModel):
    """Subject reference for subject-driven video generation."""

    type: str
    image: str


class VideoGenerationRequest(BaseModel):
    """Request body for video generation (POST /v1/video_generation)."""

    model: str
    prompt: Optional[str] = None
    prompt_optimizer: Optional[bool] = None
    fast_pretreatment: Optional[bool] = None
    duration: Optional[int] = None
    resolution: Optional[str] = None
    callback_url: Optional[str] = None
    first_frame_image: Optional[str] = None
    last_frame_image: Optional[str] = None
    subject_reference: Optional[list[SubjectReference]] = None


class VideoCreateResult(BaseModel):
    """Result of creating a video generation task."""

    task_id: str


class VideoQueryResult(BaseModel):
    """Result of querying a video generation task status."""

    task_id: str
    status: str
    file_id: Optional[str] = None
    video_width: Optional[int] = None
    video_height: Optional[int] = None


class VideoResult(BaseModel):
    """Final result of a completed video generation (extends TaskResult pattern).

    Returned by high-level methods that auto-poll until completion.
    """

    task_id: str
    status: str
    file_id: str
    download_url: Optional[str] = None
    video_width: int
    video_height: int
