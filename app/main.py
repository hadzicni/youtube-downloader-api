import os
import uuid
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from yt_dlp import YoutubeDL

load_dotenv()

API_KEY = os.getenv("API_KEY", "dev-key")
# default to the mounted downloads folder used by docker-compose
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "/downloads"))
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# ensure the directory exists (create parents if needed)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Private YouTube Downloader API")

jobs = {}


class UrlRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    quality: Optional[str] = "best"
    audio_format: Optional[str] = "mp3"


def require_api_key(x_api_key: Optional[str]):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


def ydl_extract(url: str, opts: dict):
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


@app.get("/health")
def health():
    return {"success": True, "status": "online"}


@app.post("/api/analyze")
def analyze(req: UrlRequest, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)

    opts = {
        "quiet": True,
        "skip_download": True,
    }

    info = ydl_extract(req.url, opts)

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

    opts = {
        "quiet": True,
        "skip_download": True,
    }

    info = ydl_extract(req.url, opts)

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


def run_download(job_id: str, url: str, mode: str, quality: str = "best", audio_format: str = "mp3"):
    jobs[job_id] = {
        "status": "running",
        "file_url": None,
        "error": None,
    }

    try:
        output_template = str(DOWNLOAD_DIR / f"{job_id}.%(ext)s")

        if mode == "audio":
            opts = {
                "format": "bestaudio/best",
                "outtmpl": output_template,
                "quiet": True,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": audio_format,
                    "preferredquality": "192",
                }],
            }

        elif mode == "video":
            if quality == "best":
                fmt = "bestvideo+bestaudio/best"
            elif quality == "1080p":
                fmt = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
            elif quality == "720p":
                fmt = "bestvideo[height<=720]+bestaudio/best[height<=720]"
            elif quality == "480p":
                fmt = "bestvideo[height<=480]+bestaudio/best[height<=480]"
            elif quality == "360p":
                fmt = "best[height<=360]"
            else:
                fmt = quality

            opts = {
                "format": fmt,
                "outtmpl": output_template,
                "merge_output_format": "mp4",
                "quiet": True,
            }

        else:
            opts = {
                "format": "best",
                "outtmpl": output_template,
                "quiet": True,
            }

        with YoutubeDL(opts) as ydl:
            ydl.download([url])

        files = list(DOWNLOAD_DIR.glob(f"{job_id}.*"))

        if not files:
            raise Exception("Download finished, but no file was created.")

        file = files[0]

        jobs[job_id] = {
            "status": "finished",
            "file_url": f"{BASE_URL}/api/file/{file.name}",
            "filename": file.name,
            "error": None,
        }

    except Exception as e:
        jobs[job_id] = {
            "status": "failed",
            "file_url": None,
            "error": str(e),
        }


@app.post("/api/download/video")
def download_video(
    req: DownloadRequest,
    background_tasks: BackgroundTasks,
    x_api_key: Optional[str] = Header(None)
):
    require_api_key(x_api_key)

    job_id = str(uuid.uuid4())
    background_tasks.add_task(run_download, job_id, req.url, "video", req.quality, req.audio_format)

    return {
        "success": True,
        "job_id": job_id,
        "status_url": f"{BASE_URL}/api/jobs/{job_id}",
    }


@app.post("/api/download/audio")
def download_audio(
    req: DownloadRequest,
    background_tasks: BackgroundTasks,
    x_api_key: Optional[str] = Header(None)
):
    require_api_key(x_api_key)

    job_id = str(uuid.uuid4())
    background_tasks.add_task(run_download, job_id, req.url, "audio", req.quality, req.audio_format)

    return {
        "success": True,
        "job_id": job_id,
        "status_url": f"{BASE_URL}/api/jobs/{job_id}",
    }


@app.post("/api/download/best")
def download_best(
    req: DownloadRequest,
    background_tasks: BackgroundTasks,
    x_api_key: Optional[str] = Header(None)
):
    require_api_key(x_api_key)

    job_id = str(uuid.uuid4())
    background_tasks.add_task(run_download, job_id, req.url, "best", req.quality, req.audio_format)

    return {
        "success": True,
        "job_id": job_id,
        "status_url": f"{BASE_URL}/api/jobs/{job_id}",
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)

    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "success": True,
        "job_id": job_id,
        **jobs[job_id],
    }


@app.get("/api/file/{filename}")
def get_file(filename: str, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)

    file_path = DOWNLOAD_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path=file_path, filename=filename)


@app.post("/api/thumbnail")
def thumbnail(req: UrlRequest, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)

    info = ydl_extract(req.url, {
        "quiet": True,
        "skip_download": True,
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

    opts = {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
    }

    info = ydl_extract(req.url, opts)

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

    opts = {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
    }

    info = ydl_extract(query, opts)

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

    deleted = 0

    for file in DOWNLOAD_DIR.glob("*"):
        if file.is_file():
            file.unlink()
            deleted += 1

    jobs.clear()

    return {
        "success": True,
        "deleted_files": deleted,
    }
