"""Supabase client factories for trusted backend processes."""

from __future__ import annotations

import inspect
from pathlib import Path

import structlog
from supabase import Client, create_client

from infra.settings import get_settings

logger = structlog.get_logger(__name__)


def get_anon_client() -> Client:
    """Return a Supabase anon client.

    The anon key is safe for browser contexts. When a user JWT is attached by request-layer code,
    Supabase applies RLS policies for that user.
    """

    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def get_service_client() -> Client:
    """Return a Supabase service-role client for trusted server-only operations."""

    if _called_from_request_handler():
        logger.warning(
            "supabase_service_client_from_request_handler",
            detail="service-role client bypasses RLS and must not be used in request handlers",
        )
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _called_from_request_handler() -> bool:
    """Best-effort guard for accidental service-role use inside API route modules."""

    for frame in inspect.stack(context=0):
        path = Path(frame.filename)
        if "api" in path.parts and frame.function not in {
            "get_service_client",
            "_called_from_request_handler",
        }:
            return True
    return False
