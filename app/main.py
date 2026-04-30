import os
import uuid
import time
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Literal
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl
from yt_dlp import YoutubeDL

load_dotenv()

API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise RuntimeError("API_KEY is missing. Set it in your .env file.")

DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "/downloads")).resolve()
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "/downloads/jobs.db")).resolve()
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

MAX_DURATION_SECONDS = int(os.getenv("MAX_DURATION_SECONDS", "7200"))  # 2h
MAX_FILESIZE_BYTES = int(os.getenv("MAX_FILESIZE_BYTES", str(2 * 1024 * 1024 * 1024)))  # 2GB
FILE_TTL_SECONDS = int(os.getenv("FILE_TTL_SECONDS", str(24 * 60 * 60)))  # 24h

ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "music.youtube.com",
}

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("youtube-downloader-api")

app = FastAPI(title="Private YouTube Downloader API v2")


# ----------------------------
# Models
# ----------------------------

class UrlRequest(BaseModel):
    url: HttpUrl


class DownloadRequest(BaseModel):
    url: HttpUrl
    quality: Optional[str] = "best"
    audio_format: Optional[Literal["mp3", "m4a", "opus", "wav", "flac"]] = "mp3"


# ----------------------------
# Database
# ----------------------------

def db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                mode TEXT NOT NULL,
                url TEXT NOT NULL,
                filename TEXT,
                file_url TEXT,
                error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                finished_at INTEGER
            )
        """)


init_db()


def create_job(job_id: str, url: str, mode: str):
    now = int(time.time())
    with db() as conn:
        conn.execute("""
            INSERT INTO jobs (
                job_id, status, mode, url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (job_id, "queued", mode, url, now, now))


def update_job(
    job_id: str,
    status: str,
    filename: Optional[str] = None,
    file_url: Optional[str] = None,
    error: Optional[str] = None,
    finished: bool = False,
):
    now = int(time.time())
    finished_at = now if finished else None

    with db() as conn:
        conn.execute("""
            UPDATE jobs
            SET status = ?,
                filename = COALESCE(?, filename),
                file_url = COALESCE(?, file_url),
                error = ?,
                updated_at = ?,
                finished_at = COALESCE(?, finished_at)
            WHERE job_id = ?
        """, (status, filename, file_url, error, now, finished_at, job_id))


def get_job_row(job_id: str):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (job_id,)
        ).fetchone()


# ----------------------------
# Security helpers
# ----------------------------

def require_api_key(x_api_key: Optional[str]):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


def validate_youtube_url(url: str):
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Only http/https URLs are allowed")

    host = parsed.netloc.lower().split(":")[0]

    if host not in ALLOWED_HOSTS:
        raise HTTPException(status_code=400, detail="Only YouTube URLs are allowed")


def safe_file_path(filename: str) -> Path:
    clean_name = Path(filename).name
    path = (DOWNLOAD_DIR / clean_name).resolve()

    if not str(path).startswith(str(DOWNLOAD_DIR)):
        raise HTTPException(status_code=400, detail="Invalid filename")

    return path


# ----------------------------
# yt-dlp helpers
# ----------------------------

def ydl_extract(url: str, opts: dict):
    validate_youtube_url(url)

    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def check_media_limits(info: dict):
    duration = info.get("duration")

    if duration and duration > MAX_DURATION_SECONDS:
        raise Exception(f"Video too long. Max allowed duration is {MAX_DURATION_SECONDS} seconds.")

    filesize = info.get("filesize") or info.get("filesize_approx")

    if filesize and filesize > MAX_FILESIZE_BYTES:
        raise Exception(f"File too large. Max allowed size is {MAX_FILESIZE_BYTES} bytes.")


def format_selector(mode: str, quality: str):
    if mode == "audio":
        return "bestaudio/best"

    if mode == "best":
        return "bestvideo+bestaudio/best"

    quality_map = {
        "best": "bestvideo+bestaudio/best",
        "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "360p": "best[height<=360]",
    }

    return quality_map.get(quality, quality)


# ----------------------------
# Download worker
# ----------------------------

def run_download(
    job_id: str,
    url: str,
    mode: str,
    quality: str = "best",
    audio_format: str = "mp3",
):
    update_job(job_id, "running")

    try:
        logger.info("Starting job %s", job_id)

        info = ydl_extract(url, {
            "quiet": True,
            "skip_download": True,
            "noplaylist": True,
        })

        check_media_limits(info)

        output_template = str(DOWNLOAD_DIR / f"{job_id}.%(ext)s")

        opts = {
            "format": format_selector(mode, quality),
            "outtmpl": output_template,
            "quiet": True,
            "noplaylist": True,
            "merge_output_format": "mp4",
            "retries": 3,
            "fragment_retries": 3,
        }

        if mode == "audio":
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
                "preferredquality": "192",
            }]

        with YoutubeDL(opts) as ydl:
            ydl.download([url])

        files = [
            file for file in DOWNLOAD_DIR.glob(f"{job_id}.*")
            if file.is_file() and file.name != DATABASE_PATH.name
        ]

        if not files:
            raise Exception("Download finished, but no file was created.")

        file = max(files, key=lambda f: f.stat().st_size)

        if file.stat().st_size > MAX_FILESIZE_BYTES:
            file.unlink(missing_ok=True)
            raise Exception("Downloaded file exceeded size limit.")

        file_url = f"{BASE_URL}/api/file/{file.name}"

        update_job(
            job_id,
            status="finished",
            filename=file.name,
            file_url=file_url,
            finished=True,
        )

        logger.info("Finished job %s", job_id)

    except Exception as e:
        logger.exception("Job %s failed", job_id)

        for file in DOWNLOAD_DIR.glob(f"{job_id}.*"):
            if file.is_file():
                file.unlink(missing_ok=True)

        update_job(
            job_id,
            status="failed",
            error=str(e),
            finished=True,
        )


# ----------------------------
# Cleanup
# ----------------------------

def cleanup_old_files():
    now = int(time.time())
    deleted = 0

    with db() as conn:
        rows = conn.execute("""
            SELECT job_id, filename
            FROM jobs
            WHERE finished_at IS NOT NULL
            AND finished_at < ?
        """, (now - FILE_TTL_SECONDS,)).fetchall()

        for row in rows:
            if row["filename"]:
                path = safe_file_path(row["filename"])
                if path.exists() and path.is_file():
                    path.unlink()
                    deleted += 1

            conn.execute("DELETE FROM jobs WHERE job_id = ?", (row["job_id"],))

    return deleted


# ----------------------------
# Routes
# ----------------------------

@app.get("/health")
def health():
    return {
        "success": True,
        "status": "online",
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/analyze")
def analyze(req: UrlRequest, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)

    info = ydl_extract(str(req.url), {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
    })

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


@app.post("/api/formats")
def formats(req: UrlRequest, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)

    info = ydl_extract(str(req.url), {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
    })

    result = []

    for f in info.get("formats", []):
        result.append({
            "format_id": f.get("format_id"),
            "ext": f.get("ext"),
            "resolution": f.get("resolution"),
            "fps": f.get("fps"),
            "filesize": f.get("filesize") or f.get("filesize_approx"),
            "vcodec": f.get("vcodec"),
            "acodec": f.get("acodec"),
            "format_note": f.get("format_note"),
        })

    return {
        "success": True,
        "title": info.get("title"),
        "formats": result,
    }


def start_download_job(
    req: DownloadRequest,
    background_tasks: BackgroundTasks,
    mode: Literal["video", "audio", "best"],
):
    validate_youtube_url(str(req.url))

    job_id = str(uuid.uuid4())
    create_job(job_id, str(req.url), mode)

    background_tasks.add_task(
        run_download,
        job_id,
        str(req.url),
        mode,
        req.quality or "best",
        req.audio_format or "mp3",
    )

    return {
        "success": True,
        "job_id": job_id,
        "status_url": f"{BASE_URL}/api/jobs/{job_id}",
    }


@app.post("/api/download/video")
def download_video(
    req: DownloadRequest,
    background_tasks: BackgroundTasks,
    x_api_key: Optional[str] = Header(None),
):
    require_api_key(x_api_key)
    return start_download_job(req, background_tasks, "video")


@app.post("/api/download/audio")
def download_audio(
    req: DownloadRequest,
    background_tasks: BackgroundTasks,
    x_api_key: Optional[str] = Header(None),
):
    require_api_key(x_api_key)
    return start_download_job(req, background_tasks, "audio")


@app.post("/api/download/best")
def download_best(
    req: DownloadRequest,
    background_tasks: BackgroundTasks,
    x_api_key: Optional[str] = Header(None),
):
    require_api_key(x_api_key)
    return start_download_job(req, background_tasks, "best")


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)

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


@app.get("/api/file/{filename}")
def get_file(filename: str, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)

    file_path = safe_file_path(filename)

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/octet-stream",
    )


@app.post("/api/thumbnail")
def thumbnail(req: UrlRequest, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)

    info = ydl_extract(str(req.url), {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
    })

    return {
        "success": True,
        "title": info.get("title"),
        "thumbnail": info.get("thumbnail"),
        "thumbnails": info.get("thumbnails", []),
    }


@app.post("/api/playlist")
def playlist(req: UrlRequest, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)

    info = ydl_extract(str(req.url), {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
    })

    entries = []

    for entry in info.get("entries", []):
        entries.append({
            "id": entry.get("id"),
            "title": entry.get("title"),
            "url": entry.get("url"),
            "duration": entry.get("duration"),
        })

    return {
        "success": True,
        "title": info.get("title"),
        "count": len(entries),
        "entries": entries,
    }


@app.post("/api/search")
def search(req: UrlRequest, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)

    query = f"ytsearch10:{req.url}"

    with YoutubeDL({
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
    }) as ydl:
        info = ydl.extract_info(query, download=False)

    results = []

    for entry in info.get("entries", []):
        results.append({
            "id": entry.get("id"),
            "title": entry.get("title"),
            "url": entry.get("url"),
            "channel": entry.get("channel"),
            "duration": entry.get("duration"),
        })

    return {
        "success": True,
        "results": results,
    }


@app.delete("/api/cleanup")
def cleanup(x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)

    deleted = cleanup_old_files()

    return {
        "success": True,
        "deleted_files": deleted,
    }
