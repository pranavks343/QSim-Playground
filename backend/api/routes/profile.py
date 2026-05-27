"""Profile endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from api.deps import AuthenticatedUser, get_current_user
from api.schemas import ProfileResponse
from infra.supabase import get_user_client

router = APIRouter(prefix="/api", tags=["profile"])


@router.get("/profile", response_model=ProfileResponse)
def get_profile(
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ProfileResponse:
    """Return the authenticated user profile."""

    quota_resets_at = _quota_resets_at(request, current_user)
    monthly_limit = current_user.monthly_runs_used + current_user.quota_remaining
    return ProfileResponse(
        id=current_user.id,
        email=current_user.email,
        tier=current_user.tier,
        monthly_runs_used=current_user.monthly_runs_used,
        monthly_runs_limit=monthly_limit,
        quota_remaining=current_user.quota_remaining,
        quota_resets_at=quota_resets_at,
    )


@router.get("/profile/me", response_model=ProfileResponse)
def get_profile_alias(
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ProfileResponse:
    """Backward-compatible profile alias."""

    return get_profile(request, current_user)


def _quota_resets_at(request: Request, current_user: AuthenticatedUser) -> str | None:
    bearer_jwt = getattr(request.state, "bearer_jwt", None)
    if not isinstance(bearer_jwt, str) or not bearer_jwt:
        return None
    try:
        response = (
            get_user_client(bearer_jwt)
            .table("users_profile")
            .select("quota_reset_at")
            .eq("id", str(current_user.id))
            .single()
            .execute()
        )
    except Exception:
        return None
    value = response.data.get("quota_reset_at")
    return str(value) if value is not None else None
