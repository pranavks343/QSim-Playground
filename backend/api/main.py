"""FastAPI application factory for QSim Playground."""

from __future__ import annotations

import traceback
from collections.abc import Sequence

import sentry_sdk
import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette import status

from api.middleware import AuthContextMiddleware, LoggingMiddleware, RequestIDMiddleware
from api.routes import auth, health, parse, profile, runs, share, templates
from infra.settings import Settings

logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI app."""

    settings = _load_settings()
    _init_sentry(settings)
    app = FastAPI(
        title="QSim Playground API",
        version="0.1.0",
        contact={"name": "QSim Playground"},
        license_info={"name": "MIT"},
        servers=[
            {"url": "http://localhost:8000", "description": "Local development"},
            {"url": "https://api.qsim-playground.com", "description": "Production"},
        ],
    )
    _register_exception_handlers(app)
    _register_routers(app)
    _register_middleware(app, _allowed_origins(settings))
    return app


def _load_settings() -> Settings | None:
    try:
        return Settings()
    except ValidationError:
        return None


def _init_sentry(settings: Settings | None) -> None:
    if settings is not None and settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.0)


def _allowed_origins(settings: Settings | None) -> list[str]:
    if settings is None:
        return ["http://localhost:3000"]
    return settings.allowed_origins or ["http://localhost:3000"]


def _register_middleware(app: FastAPI, allowed_origins: Sequence[str]) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AuthContextMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)


def _register_routers(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(profile.router)
    app.include_router(runs.router)
    app.include_router(parse.router)
    app.include_router(share.router)
    app.include_router(templates.router)


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        request_id = _request_id(request)
        if exc.status_code >= 500:
            logger.error(
                "http_exception",
                status_code=exc.status_code,
                detail=exc.detail,
                request_id=request_id,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = _request_id(request)
        logger.error(
            "unhandled_exception",
            request_id=request_id,
            error_type=type(exc).__name__,
            traceback="".join(traceback.format_exception(exc)),
        )
        sentry_sdk.capture_exception(exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error", "request_id": request_id},
        )


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


app = create_app()
