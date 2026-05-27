"""Profile endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api.deps import AuthenticatedUser, get_current_user

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("/me", response_model=AuthenticatedUser)
def get_profile(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    """Return the authenticated user profile."""

    return current_user
