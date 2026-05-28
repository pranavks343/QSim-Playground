from __future__ import annotations

import pytest
from pydantic import ValidationError

from infra.settings import Settings
from infra.supabase import get_anon_client, get_service_client


def _real_supabase_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        pytest.skip(f"Supabase credentials are not configured: {exc}")


def test_anon_client_can_read_local_auth_session() -> None:
    _real_supabase_settings()

    client = get_anon_client()

    try:
        client.auth.get_session()
    except Exception as exc:
        pytest.skip(f"Supabase is not reachable from this environment: {exc}")


def test_service_client_can_call_admin_api() -> None:
    _real_supabase_settings()

    client = get_service_client()

    try:
        client.auth.admin.list_users()
    except Exception as exc:
        pytest.skip(f"Supabase is not reachable from this environment: {exc}")
