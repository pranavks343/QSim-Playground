"""Explicitly gated debug routes for production observability smoke tests."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from starlette import status

router = APIRouter(prefix="/api/debug", tags=["debug"])


@router.get("/boom", include_in_schema=False)
def boom(request: Request) -> None:
    """Raise a deliberate error only when ``ENABLE_DEBUG_ROUTES=true``."""

    if request.app.state.enable_debug_routes is not True:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    raise RuntimeError("Deliberate backend Sentry smoke-test error")
