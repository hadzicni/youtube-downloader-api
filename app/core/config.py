from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    try:
        return float(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    api_key: str = os.getenv("API_KEY", "").strip()
    download_dir: Path = Path(os.getenv("DOWNLOAD_DIR", "/downloads")).resolve()
    database_path: Path = Path(os.getenv("DATABASE_PATH", "/downloads/jobs.db")).resolve()
    base_url: str = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
    max_duration_seconds: int = _env_int("MAX_DURATION_SECONDS", 7200)
    max_filesize_bytes: int = _env_int("MAX_FILESIZE_BYTES", 2 * 1024 * 1024 * 1024)
    file_ttl_seconds: int = _env_int("FILE_TTL_SECONDS", 24 * 60 * 60)
    sqlite_timeout_seconds: float = _env_float("SQLITE_TIMEOUT_SECONDS", 15.0)
    rate_limit_per_api_key_per_minute: int = _env_int("RATE_LIMIT_API_KEY_PER_MINUTE", 0)
    rate_limit_per_ip_per_minute: int = _env_int("RATE_LIMIT_IP_PER_MINUTE", 0)
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()


settings = Settings()
