from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Header, HTTPException, status

from app.core.config import settings


def require_api_key(x_api_key: Optional[str] = Header(default=None, alias="x-api-key")) -> None:
    if not settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key is not configured",
        )

    if x_api_key is None or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
