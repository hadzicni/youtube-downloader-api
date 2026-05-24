from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, HttpUrl, validator


DownloadMode = Literal["video", "audio", "best"]
VideoQuality = Literal["best", "1080p", "720p", "480p", "360p"]
AudioFormat = Literal["mp3", "m4a", "opus", "wav", "flac"]


class UrlRequest(BaseModel):
    url: HttpUrl


class SearchRequest(BaseModel):
    query: str

    @validator("query")
    def normalize_query(cls, value: str) -> str:
        cleaned = value.strip()

        if not cleaned:
            raise ValueError("query must not be empty")

        return cleaned


class DownloadRequest(BaseModel):
    url: HttpUrl
    quality: str = "best"
    audio_format: AudioFormat = "mp3"

    @validator("quality")
    def normalize_quality(cls, value: str) -> str:
        cleaned = value.strip().lower()
        return cleaned or "best"
