from __future__ import annotations

import logging
import time

from app.core.config import settings
from app.core.db import list_expired_jobs, set_job_expired
from app.core.errors import CleanupError
from app.services.downloader import resolve_download_path


logger = logging.getLogger(__name__)


def cleanup_expired_jobs() -> int:
    cutoff = int(time.time()) - settings.file_ttl_seconds
    deleted_files = 0

    rows = list_expired_jobs(cutoff)

    for row in rows:
        filename = row["filename"]

        if filename:
            file_path = resolve_download_path(filename)

            try:
                if file_path.exists() and file_path.is_file():
                    file_path.unlink()
                    deleted_files += 1
                    logger.info("Deleted expired file %s for job %s", filename, row["job_id"])
                else:
                    deleted_files += 1
            except FileNotFoundError:
                deleted_files += 1
            except OSError as exc:
                logger.warning("Skipping cleanup for job %s: %s", row["job_id"], exc)
                raise CleanupError(f"Failed to delete {filename}: {exc}") from exc

        set_job_expired(row["job_id"])

    return deleted_files
