from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.core.config import settings
from app.core.errors import (
    ExternalServiceError,
    InvalidRequestError,
    InvalidYouTubeURLError,
    MediaLimitError,
    SearchError,
)


ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "music.youtube.com",
}

logger = logging.getLogger(__name__)


def validate_youtube_url(url: str) -> None:
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise InvalidYouTubeURLError("Only http/https URLs are allowed")

    host = parsed.netloc.lower().split(":")[0]

    if host not in ALLOWED_HOSTS:
        raise InvalidYouTubeURLError("Only YouTube URLs are allowed")


def extract_info(url: str, options: dict[str, Any]) -> dict[str, Any]:
    validate_youtube_url(url)

    try:
        with YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=False)
    except DownloadError as exc:
        logger.exception("yt-dlp metadata extraction failed for %s", url)
        raise ExternalServiceError(f"yt-dlp metadata extraction failed: {exc}") from exc


def check_media_limits(info: dict[str, Any]) -> None:
    duration = info.get("duration")

    if duration and duration > settings.max_duration_seconds:
        raise MediaLimitError(
            f"Video too long. Max allowed duration is {settings.max_duration_seconds} seconds."
        )

    filesize = info.get("filesize") or info.get("filesize_approx")

    if filesize and filesize > settings.max_filesize_bytes:
        raise MediaLimitError(
            f"File too large. Max allowed size is {settings.max_filesize_bytes} bytes."
        )


def get_analyze_payload(url: str) -> dict[str, Any]:
    info = extract_info(
        url,
        {
            "quiet": True,
            "skip_download": True,
            "noplaylist": True,
        },
    )

    return {
        "success": True,
        "id": info.get("id"),
        "title": info.get("title"),
        "channel": info.get("channel"),
        "uploader": info.get("uploader"),
        "duration": info.get("duration"),
        "webpage_url": info.get("webpage_url"),
        "thumbnail": info.get("thumbnail"),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "description": info.get("description"),
    }


def get_formats_payload(url: str) -> dict[str, Any]:
    info = extract_info(
        url,
        {
            "quiet": True,
            "skip_download": True,
            "noplaylist": True,
        },
    )

    formats = []

    for fmt in info.get("formats", []):
        formats.append(
            {
                "format_id": fmt.get("format_id"),
                "ext": fmt.get("ext"),
                "resolution": fmt.get("resolution"),
                "fps": fmt.get("fps"),
                "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
                "vcodec": fmt.get("vcodec"),
                "acodec": fmt.get("acodec"),
                "format_note": fmt.get("format_note"),
            }
        )

    return {
        "success": True,
        "title": info.get("title"),
        "formats": formats,
    }


def get_thumbnail_payload(url: str) -> dict[str, Any]:
    info = extract_info(
        url,
        {
            "quiet": True,
            "skip_download": True,
            "noplaylist": True,
        },
    )

    return {
        "success": True,
        "title": info.get("title"),
        "thumbnail": info.get("thumbnail"),
        "thumbnails": info.get("thumbnails", []),
    }


def get_playlist_payload(url: str) -> dict[str, Any]:
    info = extract_info(
        url,
        {
            "quiet": True,
            "extract_flat": True,
            "skip_download": True,
        },
    )

    entries = []

    for entry in info.get("entries", []):
        entries.append(
            {
                "id": entry.get("id"),
                "title": entry.get("title"),
                "url": entry.get("url"),
                "duration": entry.get("duration"),
            }
        )

    return {
        "success": True,
        "title": info.get("title"),
        "count": len(entries),
        "entries": entries,
    }


def search_youtube(query: str) -> dict[str, Any]:
    normalized_query = query.strip()

    if not normalized_query:
        raise InvalidRequestError("Search query cannot be empty")

    try:
        with YoutubeDL(
            {
                "quiet": True,
                "extract_flat": True,
                "skip_download": True,
            }
        ) as ydl:
            info = ydl.extract_info(f"ytsearch10:{normalized_query}", download=False)
    except DownloadError as exc:
        logger.exception("yt-dlp search failed for query %s", normalized_query)
        raise SearchError(f"Search failed: {exc}") from exc

    results = []

    for entry in info.get("entries", []):
        results.append(
            {
                "id": entry.get("id"),
                "title": entry.get("title"),
                "url": entry.get("url"),
                "channel": entry.get("channel"),
                "duration": entry.get("duration"),
            }
        )

    return {
        "success": True,
        "results": results,
    }
