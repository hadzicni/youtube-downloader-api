# YouTube Downloader API

Simple private API for downloading YouTube videos and audio using `yt-dlp` and `FastAPI`.

Quickstart

1. Copy `.env.example` to `.env` and set `API_KEY`.
2. Run with Docker Compose:

```bash
docker compose up --build
```

API is available at `http://localhost:8000`.

Endpoints require header `x-api-key` with your `API_KEY`.
