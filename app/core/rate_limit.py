from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


@dataclass(frozen=True)
class RateLimitConfig:
    api_key_per_minute: int = 0
    ip_per_minute: int = 0


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        if limit <= 0:
            return True

        now = monotonic()

        with self._lock:
            bucket = self._buckets[key]
            cutoff = now - window_seconds

            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                return False

            bucket.append(now)
            return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        api_key_limit: int = 0,
        ip_limit: int = 0,
    ) -> None:
        super().__init__(app)
        self._api_key_limit = api_key_limit
        self._ip_limit = ip_limit
        self._limiter = SlidingWindowRateLimiter()

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in {"/health", "/docs", "/redoc", "/openapi.json"}:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        api_key = request.headers.get("x-api-key", "anonymous")

        if self._ip_limit > 0 and not self._limiter.allow(f"ip:{client_ip}", self._ip_limit):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded for client IP."},
            )

        if self._api_key_limit > 0 and api_key and not self._limiter.allow(
            f"key:{api_key}",
            self._api_key_limit,
        ):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded for API key."},
            )

        return await call_next(request)
