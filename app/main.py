from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import public_router, secure_router
from app.core.config import settings
from app.core.db import init_db
from app.core.errors import AppError
from app.core.logger import configure_logging
from app.core.rate_limit import RateLimitMiddleware


logger = configure_logging()


def create_app() -> FastAPI:
    if not settings.api_key:
        raise RuntimeError("API_KEY is missing. Set it in your environment.")

    settings.download_dir.mkdir(parents=True, exist_ok=True)
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    init_db()

    app = FastAPI(
        title="Private YouTube Downloader API v2",
        description="Private FastAPI wrapper around yt-dlp for video analysis, search, and downloads.",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        swagger_ui_parameters={"persistAuthorization": True},
    )

    app.add_middleware(
        RateLimitMiddleware,
        api_key_limit=settings.rate_limit_per_api_key_per_minute,
        ip_limit=settings.rate_limit_per_ip_per_minute,
    )
    app.include_router(public_router)
    app.include_router(secure_router)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "detail": exc.detail},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "detail": exc.detail},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"success": False, "detail": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled application error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": "Internal server error"},
        )

    return app


app = create_app()
