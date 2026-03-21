"""Type definitions for the Speech resource."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class T2AAsyncResult(BaseModel):
    """Result of an async TTS task query."""

    model_config = ConfigDict(coerce_numbers_to_str=True)

    task_id: str
    status: str
    file_id: Optional[str] = None


class TaskResult(BaseModel):
    """Final result of a completed async task (create + poll + retrieve).

    Returned by high-level methods that auto-poll until completion,
    such as ``Speech.async_generate``.
    """

    model_config = ConfigDict(coerce_numbers_to_str=True)

    task_id: str
    status: str
    file_id: str
    download_url: str
