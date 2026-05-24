from __future__ import annotations


class AppError(Exception):
    status_code = 500
    default_detail = "Internal server error"

    def __init__(self, detail: str | None = None):
        super().__init__(detail or self.default_detail)
        self.detail = detail or self.default_detail


class InvalidRequestError(AppError):
    status_code = 400
    default_detail = "Invalid request"


class InvalidYouTubeURLError(InvalidRequestError):
    default_detail = "Only YouTube URLs are allowed"


class MediaLimitError(InvalidRequestError):
    default_detail = "Requested media exceeds configured limits"


class ExternalServiceError(AppError):
    status_code = 502
    default_detail = "Upstream service failed"


class SearchError(ExternalServiceError):
    default_detail = "Search failed"


class DownloadProcessingError(ExternalServiceError):
    default_detail = "Download failed"


class FileStorageError(AppError):
    status_code = 500
    default_detail = "File storage error"


class CleanupError(AppError):
    status_code = 500
    default_detail = "Cleanup failed"


class DatabaseError(AppError):
    status_code = 500
    default_detail = "Database error"
