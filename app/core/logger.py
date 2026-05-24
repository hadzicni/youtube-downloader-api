from __future__ import annotations

import logging

from app.core.config import settings


def configure_logging() -> logging.Logger:
    level = getattr(logging, settings.log_level, logging.INFO)
    root_logger = logging.getLogger()

    if not root_logger.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    else:
        root_logger.setLevel(level)

    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(level)

    return logging.getLogger("youtube-downloader-api")
