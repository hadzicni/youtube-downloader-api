from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import BackgroundTasks
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.core.config import settings
from app.core.db import create_job, set_job_failed, set_job_finished, set_job_running
from app.core.errors import DownloadProcessingError, FileStorageError, InvalidRequestError
from app.services.youtube import check_media_limits, extract_info, validate_youtube_url


DEFAULT_VIDEO_FORMAT = "bestvideo+bestaudio/best"
logger = logging.getLogger(__name__)


def format_selector(mode: str, quality: str) -> str:
    normalized_mode = mode.lower()
    normalized_quality = (quality or "best").lower()

    if normalized_mode == "audio":
        return "bestaudio/best"

    if normalized_mode == "best":
        return DEFAULT_VIDEO_FORMAT

    video_quality_map = {
        "best": DEFAULT_VIDEO_FORMAT,
        "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
    }

    return video_quality_map.get(normalized_quality, DEFAULT_VIDEO_FORMAT)


def resolve_download_path(filename: str) -> Path:
    clean_name = Path(filename).name
    path = (settings.download_dir / clean_name).resolve()

    if not path.is_relative_to(settings.download_dir):
        raise FileStorageError("Invalid filename")

    return path


def _build_file_url(filename: str) -> str:
    return f"{settings.base_url}/api/file/{filename}"


def _find_downloaded_file(job_id: str) -> Path:
    candidates = []

    for path in settings.download_dir.glob(f"{job_id}.*"):
        if not path.is_file():
            continue

        if path.name.endswith(".info.json"):
            continue

        candidates.append(path)

    if not candidates:
        raise FileStorageError("Download finished, but no file was created")

    return max(candidates, key=lambda file_path: file_path.stat().st_size)


def _cleanup_job_artifacts(job_id: str) -> None:
    for path in settings.download_dir.glob(f"{job_id}.*"):
        try:
            if path.is_file():
                path.unlink()
        except FileNotFoundError:
            continue
        except OSError:
            continue


def run_download_job(
    job_id: str,
    url: str,
    mode: str,
    quality: str = "best",
    audio_format: str = "mp3",
) -> None:
    normalized_mode = mode.lower()

    if normalized_mode not in {"video", "audio", "best"}:
        raise InvalidRequestError(f"Unsupported download mode: {mode}")

    set_job_running(job_id)
    logger.info("Starting download job %s in %s mode", job_id, normalized_mode)

    try:
        validate_youtube_url(url)
        info = extract_info(
            url,
            {
                "quiet": True,
                "skip_download": True,
                "noplaylist": True,
            },
        )
        check_media_limits(info)

        output_template = str(settings.download_dir / f"{job_id}.%(ext)s")

        options = {
            "format": format_selector(normalized_mode, quality),
            "outtmpl": output_template,
            "quiet": True,
            "noplaylist": True,
            "merge_output_format": "mp4",
            "retries": 3,
            "fragment_retries": 3,
        }

        if normalized_mode == "audio":
            options["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": audio_format,
                    "preferredquality": "192",
                }
            ]

        with YoutubeDL(options) as ydl:
            ydl.download([url])

        file_path = _find_downloaded_file(job_id)

        if file_path.stat().st_size > settings.max_filesize_bytes:
            file_path.unlink(missing_ok=True)
            raise FileStorageError("Downloaded file exceeded size limit")

        set_job_finished(job_id, file_path.name, _build_file_url(file_path.name))
        logger.info("Finished download job %s", job_id)

    except DownloadError as exc:
        logger.exception("Download job %s failed in yt-dlp", job_id)
        _cleanup_job_artifacts(job_id)
        set_job_failed(job_id, f"Download error: {exc}")
    except FileNotFoundError as exc:
        logger.exception("Download job %s failed because a binary or file was missing", job_id)
        _cleanup_job_artifacts(job_id)
        set_job_failed(job_id, f"Required binary or file not found: {exc}")
    except (OSError, InvalidRequestError, FileStorageError, DownloadProcessingError) as exc:
        logger.exception("Download job %s failed", job_id)
        _cleanup_job_artifacts(job_id)
        set_job_failed(job_id, str(exc))
    except Exception as exc:
        logger.exception("Unexpected failure in download job %s", job_id)
        _cleanup_job_artifacts(job_id)
        set_job_failed(job_id, f"Unexpected download failure: {exc}")


def start_download_job(
    url: str,
    mode: str,
    background_tasks: BackgroundTasks,
    quality: str = "best",
    audio_format: str = "mp3",
) -> dict[str, str]:
    validate_youtube_url(url)

    job_id = str(uuid.uuid4())
    create_job(job_id, url, mode)

    background_tasks.add_task(
        run_download_job,
        job_id,
        url,
        mode,
        quality,
        audio_format,
    )

    return {
        "success": True,
        "job_id": job_id,
        "status_url": f"{settings.base_url}/api/jobs/{job_id}",
    }
