"""FastAPI middleware for request tracing, logging, and auth context."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)
Handler = Callable[[Request], Awaitable[Response]]


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a stable request ID to request state and response headers."""

    async def dispatch(self, request: Request, call_next: Handler) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Emit one structured log record per request."""

    async def dispatch(self, request: Request, call_next: Handler) -> Response:
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
                user_id=getattr(request.state, "user_id", None),
                request_id=getattr(request.state, "request_id", None),
            )


class AuthContextMiddleware(BaseHTTPMiddleware):
    """Initialize auth-related request state without requiring auth globally."""

    async def dispatch(self, request: Request, call_next: Handler) -> Response:
        request.state.user_id = None
        return await call_next(request)
