from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.auth import require_api_key
from app.core.db import get_job_row
from app.models.schemas import DownloadRequest, SearchRequest, UrlRequest
from app.services.cleanup import cleanup_expired_jobs
from app.services.downloader import resolve_download_path, start_download_job
from app.services.youtube import (
    get_analyze_payload,
    get_formats_payload,
    get_playlist_payload,
    get_thumbnail_payload,
    search_youtube,
)


public_router = APIRouter()
secure_router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])


@public_router.get("/health")
def health() -> dict[str, object]:
    from datetime import datetime, timezone

    return {
        "success": True,
        "status": "online",
        "time": datetime.now(timezone.utc).isoformat(),
    }


@secure_router.post("/analyze")
def analyze(req: UrlRequest):
    return get_analyze_payload(str(req.url))


@secure_router.post("/formats")
def formats(req: UrlRequest):
    return get_formats_payload(str(req.url))


@secure_router.post("/download/video")
def download_video(req: DownloadRequest, background_tasks: BackgroundTasks):
    return start_download_job(
        url=str(req.url),
        mode="video",
        background_tasks=background_tasks,
        quality=req.quality,
        audio_format=req.audio_format,
    )


@secure_router.post("/download/audio")
def download_audio(req: DownloadRequest, background_tasks: BackgroundTasks):
    return start_download_job(
        url=str(req.url),
        mode="audio",
        background_tasks=background_tasks,
        quality=req.quality,
        audio_format=req.audio_format,
    )


@secure_router.post("/download/best")
def download_best(req: DownloadRequest, background_tasks: BackgroundTasks):
    return start_download_job(
        url=str(req.url),
        mode="best",
        background_tasks=background_tasks,
        quality=req.quality,
        audio_format=req.audio_format,
    )


@secure_router.get("/jobs/{job_id}")
def get_job(job_id: str):
    row = get_job_row(job_id)

    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "success": True,
        "job_id": row["job_id"],
        "status": row["status"],
        "mode": row["mode"],
        "filename": row["filename"],
        "file_url": row["file_url"],
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "finished_at": row["finished_at"],
    }


@secure_router.get("/file/{filename}")
def get_file(filename: str):
    file_path = resolve_download_path(filename)

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/octet-stream",
    )


@secure_router.post("/thumbnail")
def thumbnail(req: UrlRequest):
    return get_thumbnail_payload(str(req.url))


@secure_router.post("/playlist")
def playlist(req: UrlRequest):
    return get_playlist_payload(str(req.url))


@secure_router.post("/search")
def search(req: SearchRequest):
    return search_youtube(req.query)


@secure_router.delete("/cleanup")
def cleanup():
    deleted = cleanup_expired_jobs()

    return {
        "success": True,
        "deleted_files": deleted,
    }
