"""Type definitions for the Music resource."""

from __future__ import annotations

from pydantic import BaseModel


class LyricsResult(BaseModel):
    """Result of a lyrics generation request."""

    song_title: str
    style_tags: str
    lyrics: str
