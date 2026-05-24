# Private YouTube Downloader API v2

Secure self-hosted YouTube download API built with FastAPI and yt-dlp.

Supports:

- Video downloads
- Audio extraction
- Best quality direct downloads
- Metadata analysis
- Available format listing
- Thumbnail fetching
- Playlist inspection
- YouTube search
- Persistent job tracking via SQLite
- Automatic file cleanup
- API key protection

Designed for:

- Docker / Homelab
- Private automation
- Internal tools
- Discord bots
- Telegram bots
- Web dashboards

---

# Features

## Download Modes

- `/api/download/video` → download video with selected quality
- `/api/download/audio` → extract audio only
- `/api/download/best` → best available media

## Metadata Tools

- `/api/analyze`
- `/api/formats`
- `/api/thumbnail`
- `/api/playlist`
- `/api/search`

## Job System

Downloads run asynchronously in the background.

Each download returns:

- `job_id`
- `status_url`

Status values:

- `queued`
- `running`
- `finished`
- `failed`
- `expired`

## Security Improvements

- API key required on all protected endpoints
- No insecure fallback API key
- Path traversal protected file serving
- URL validation (YouTube only)
- Download duration limits
- Download filesize limits

## Persistence

Jobs are stored in SQLite:

- survives API restart
- survives container restart

## Cleanup

Old files and expired jobs can be removed automatically using:

- `/api/cleanup`

---

# Quickstart

## 1. Clone Project

```bash
git clone <your-repository>
cd youtube-downloader-api
```

---

## 2. Configure Environment

Copy example environment:

```bash
cp .env.example .env
```

Edit `.env`:

```env
API_KEY=super-secret-key-change-me
DOWNLOAD_DIR=/downloads
DATABASE_PATH=/downloads/jobs.db
BASE_URL=http://localhost:8000

MAX_DURATION_SECONDS=7200
MAX_FILESIZE_BYTES=2147483648
FILE_TTL_SECONDS=86400
```

---

## 3. Run with Docker Compose

```bash
docker compose up --build -d
```

API will be available at:

```bash
http://localhost:8000
```

Swagger docs:

```bash
http://localhost:8000/docs
```

---

# Authentication

All protected endpoints require:

```http
x-api-key: YOUR_API_KEY
```

---

# API Endpoints

## Health Check

```http
GET /health
```

---

## Analyze Video Metadata

```http
POST /api/analyze
```

Body:

```json
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID"
}
```

---

## List Available Formats

```http
POST /api/formats
```

---

## Download Video

```http
POST /api/download/video
```

Body:

```json
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "quality": "1080p"
}
```

Available qualities:

- best
- 1080p
- 720p
- 480p
- 360p

---

## Download Audio

```http
POST /api/download/audio
```

Body:

```json
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "audio_format": "mp3"
}
```

Supported formats:

- mp3
- m4a
- opus
- wav
- flac

---

## Download Best Available

```http
POST /api/download/best
```

---

## Check Download Job Status

```http
GET /api/jobs/{job_id}
```

---

## Download Finished File

```http
GET /api/file/{filename}
```

---

## Get Thumbnail Information

```http
POST /api/thumbnail
```

---

## Inspect Playlist

```http
POST /api/playlist
```

---

## Search YouTube

```http
POST /api/search
```

Body:

```json
{
  "query": "lofi hip hop"
}
```

---

## Cleanup Expired Files

```http
DELETE /api/cleanup
```

---

# Example Workflow

## Start Download

```http
POST /api/download/video
```

Response:

```json
{
  "success": true,
  "job_id": "6d1b5baf-xxxx-xxxx-xxxx",
  "status_url": "http://localhost:8000/api/jobs/6d1b5baf-xxxx"
}
```

## Poll Job Status

```http
GET /api/jobs/6d1b5baf-xxxx
```

When finished:

```json
{
  "success": true,
  "status": "finished",
  "file_url": "http://localhost:8000/api/file/6d1b5baf.mp4"
}
```

---

# Recommended Production Setup

For stable long-term usage it is recommended to run behind:

- Nginx or Traefik reverse proxy
- HTTPS
- Fail2ban / IP restriction
- Docker volume for persistent downloads

Optional future upgrades:

- Redis job queue
- Multi-worker downloader
- Rate limiting
- User accounts
- Automatic scheduled cleanup

Optional rate-limit env vars:

- `RATE_LIMIT_API_KEY_PER_MINUTE`
- `RATE_LIMIT_IP_PER_MINUTE`

---

# Legal Notice

This software is intended for private self-hosted usage only.

You are responsible for ensuring that all downloaded media complies with:

- local law
- platform terms of service
- copyright restrictions

---

# Tech Stack

- FastAPI
- yt-dlp
- FFmpeg
- SQLite
- Docker
