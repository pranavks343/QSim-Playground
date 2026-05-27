"""Health and dependency smoke endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from infra.gemini import GeminiClient
from infra.settings import Settings
from infra.supabase import get_service_client

router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    """Health response separating app liveness from dependency reachability."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    db_reachable: bool
    gemini_reachable: bool
    version: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return app liveness and best-effort dependency status."""

    return HealthResponse(
        status="ok",
        db_reachable=_db_reachable(),
        gemini_reachable=await _gemini_reachable(),
        version="0.1.0",
    )


def _db_reachable() -> bool:
    try:
        Settings()
        get_service_client().table("users_profile").select("id").limit(1).execute()
    except Exception:
        return False
    return True


async def _gemini_reachable() -> bool:
    try:
        settings = Settings()
        await GeminiClient(settings.gemini_api_keys).generate_text(
            "Reply with ok.", temperature=0.0
        )
    except Exception:
        return False
    return True
