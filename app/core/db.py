from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from typing import Iterator

from app.core.config import settings
from app.core.errors import DatabaseError


JOB_STATUSES = ("queued", "running", "finished", "failed", "expired")
DOWNLOAD_MODES = ("video", "audio", "best")


def connect() -> sqlite3.Connection:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        str(settings.database_path),
        timeout=settings.sqlite_timeout_seconds,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute(
        f"PRAGMA busy_timeout = {int(settings.sqlite_timeout_seconds * 1000)}"
    )
    return connection


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    connection = connect()

    try:
        yield connection
        connection.commit()
    except sqlite3.Error as exc:
        connection.rollback()
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def init_db() -> None:
    with session() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'finished', 'failed', 'expired')),
                mode TEXT NOT NULL CHECK (mode IN ('video', 'audio', 'best')),
                url TEXT NOT NULL,
                filename TEXT,
                file_url TEXT,
                error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                finished_at INTEGER
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_finished_at ON jobs(finished_at)"
        )


def create_job(job_id: str, url: str, mode: str) -> None:
    now = int(time.time())

    with session() as connection:
        connection.execute(
            """
            INSERT INTO jobs (
                job_id, status, mode, url, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_id, "queued", mode, url, now, now),
        )


def update_job(
    job_id: str,
    *,
    status: str,
    filename: str | None = None,
    file_url: str | None = None,
    error: str | None = None,
    finished_at: int | None = None,
) -> None:
    now = int(time.time())

    with session() as connection:
        connection.execute(
            """
            UPDATE jobs
            SET status = ?,
                filename = ?,
                file_url = ?,
                error = ?,
                updated_at = ?,
                finished_at = COALESCE(?, finished_at)
            WHERE job_id = ?
            """,
            (status, filename, file_url, error, now, finished_at, job_id),
        )


def set_job_running(job_id: str) -> None:
    update_job(job_id, status="running", error=None)


def set_job_finished(job_id: str, filename: str, file_url: str) -> None:
    update_job(
        job_id,
        status="finished",
        filename=filename,
        file_url=file_url,
        error=None,
        finished_at=int(time.time()),
    )


def set_job_failed(job_id: str, error: str) -> None:
    update_job(job_id, status="failed", filename=None, file_url=None, error=error)


def set_job_expired(job_id: str) -> None:
    update_job(job_id, status="expired", filename=None, file_url=None, error=None)


def get_job_row(job_id: str):
    with session() as connection:
        return connection.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()


def list_expired_jobs(cutoff_ts: int):
    with session() as connection:
        return connection.execute(
            """
            SELECT job_id, filename
            FROM jobs
            WHERE status = 'finished'
              AND finished_at IS NOT NULL
              AND finished_at < ?
            ORDER BY finished_at ASC
            """,
            (cutoff_ts,),
        ).fetchall()
