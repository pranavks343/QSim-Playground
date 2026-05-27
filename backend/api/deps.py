"""FastAPI dependencies for settings, request context, and Supabase auth."""

from __future__ import annotations

import time
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Header, HTTPException, Request, status
from jwt import ExpiredSignatureError, InvalidTokenError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from infra.settings import Settings
from infra.settings import get_settings as get_infra_settings
from infra.supabase import get_user_client

AUTH_HEADER = {"WWW-Authenticate": "Bearer"}
PROFILE_CACHE_TTL_SECONDS = 60.0
_PROFILE_CACHE: dict[UUID, tuple[float, UserProfile]] = {}


class AuthenticatedUser(BaseModel):
    """Authenticated user plus quota state loaded from Supabase."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str
    tier: str = Field(pattern="^(free|pro|enterprise)$")
    monthly_runs_used: int = Field(ge=0)
    quota_remaining: int = Field(ge=0)


class UserProfile(BaseModel):
    """Subset of users_profile needed for request auth."""

    model_config = ConfigDict(extra="ignore")

    tier: str = Field(pattern="^(free|pro|enterprise)$")
    monthly_runs_used: int = Field(ge=0)


def get_settings() -> Settings:
    """Return cached application settings."""

    return get_infra_settings()


def get_request_id(request: Request) -> str:
    """Return the request ID assigned by middleware."""

    return str(getattr(request.state, "request_id", "unknown"))


def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    """Validate a Supabase JWT and return the current user profile."""

    bearer_jwt = _extract_bearer_token(authorization)
    settings = _settings_or_401()
    try:
        payload = jwt.decode(
            bearer_jwt,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except (ExpiredSignatureError, InvalidTokenError):
        raise _invalid_token_error() from None

    try:
        user_id = UUID(str(payload["sub"]))
        email = str(payload.get("email", ""))
    except (KeyError, TypeError, ValueError):
        raise _invalid_token_error() from None

    if not email:
        raise _invalid_token_error()

    request.state.user_id = str(user_id)
    request.state.bearer_jwt = bearer_jwt
    profile = _get_user_profile(user_id, bearer_jwt)
    return AuthenticatedUser(
        id=user_id,
        email=email,
        tier=profile.tier,
        monthly_runs_used=profile.monthly_runs_used,
        quota_remaining=_quota_limit(profile.tier) - profile.monthly_runs_used,
    )


def _extract_bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise _invalid_token_error()
    scheme, _, credential = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credential.strip():
        raise _invalid_token_error()
    return credential.strip()


def _settings_or_401() -> Settings:
    try:
        return get_settings()
    except ValidationError:
        raise _invalid_token_error() from None


def _get_user_profile(user_id: UUID, token: str) -> UserProfile:
    cached = _PROFILE_CACHE.get(user_id)
    now = time.monotonic()
    if cached is not None and now - cached[0] < PROFILE_CACHE_TTL_SECONDS:
        return cached[1]

    try:
        response = (
            get_user_client(token)
            .table("users_profile")
            .select("tier, monthly_runs_used")
            .eq("id", str(user_id))
            .single()
            .execute()
        )
        profile = UserProfile.model_validate(response.data)
    except Exception:
        raise _invalid_token_error() from None

    _PROFILE_CACHE[user_id] = (now, profile)
    return profile


def _quota_limit(tier: str) -> int:
    return {"free": 50, "pro": 500, "enterprise": 5000}.get(tier, 50)


def _invalid_token_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers=AUTH_HEADER,
    )
